"""Pure-Python model of an HRDS+ controller as seen over Modbus.

The register image starts from a real-device dump (:mod:`tests.sim.seeds`).
On top of it the model implements the behaviour documented in
``doc/references/UNIT_BEHAVIOUR.md`` (registers:
``doc/references/MODBUS_REGISTERS.md``) that the integration depends on:

* writes to on/off, dehumidify and integration are acknowledged but ignored
  unless their "by BMS" enable (PH02/PH28/PH27) is set;
* PH01 = 1 without a display (or with the display switched off) keeps the unit
  ``off_by_display``; an OFF from any source wins;
* HB04 sets the season (4 = summer, 3 = winter), anything else raises AL25 and
  shuts everything off;
* the humidity setpoint is clamped to PH29/PH30;
* the unit's own room logic: DEU from the room humidity, INT from the room
  temperature (summer above SEtC + PF12, winter below SEtH - PF12);
* a request starts water valve, damper (R units), fan and compressor; winter
  integration heats (compressor off, pump on);
* the fan output follows PM20 under one of three hypotheses (``fan_model``),
  because the real behaviour is not confirmed yet (``plans/todo.md``);
* alarms, probe faults and a power cycle can be injected.

Outputs are recomputed after every write or injected change, so a poll that
follows a write sees the final state; ``sequence_delay`` holds the fan and
compressor in ``wait_on`` for that many seconds to mimic PS01.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from . import registers as R
from .seeds import DEFAULT_SEED, Seed, load_seed

FAN_MODELS = ("rescale", "clamp", "direct")
COMPRESSOR_ALARMS = ("AL11", "AL12")  # stop the compressor
SHUTDOWN_ALARMS = ("AL25",)  # stop everything


class IllegalAddress(Exception):
    """The device does not serve this address (Modbus exception 02)."""


@dataclass
class Write:
    """One write the device received, for test assertions."""

    address: int
    value: int
    accepted: bool
    stored: Optional[int]
    at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "address": self.address,
            "value": self.value,
            "accepted": self.accepted,
            "stored": self.stored,
            "at": self.at,
        }


class HrdsDevice:
    """State of one simulated HRDS+ (thread-safe)."""

    def __init__(
        self,
        seed: str = DEFAULT_SEED,
        overlays: tuple[str, ...] = (),
        fan_model: str = "rescale",
        sequence_delay: float = 0.0,
    ) -> None:
        self._lock = threading.RLock()
        self.seed_name = seed
        self.overlays = tuple(overlays)
        self.default_fan_model = fan_model
        self.default_sequence_delay = sequence_delay
        self._seed: Seed = load_seed(seed, self.overlays)
        self.reset()

    # ---- lifecycle -----------------------------------------------------------
    def reset(self) -> None:
        """Back to the seed state, with no faults and an empty write log."""
        with self._lock:
            self.input: dict[int, int] = dict(self._seed.input)
            self.holding: dict[int, int] = dict(self._seed.holding)
            # Alarm reset registers are writable even though no dump reads them.
            for addr in R.ALARM_RESET_RANGE:
                self.holding.setdefault(addr, 0)
            self.identity: dict[int, str] = dict(self._seed.identity)
            self.unit_id = self._seed.unit
            self.has_display = bool(self._seed.meta.get("display", False))
            self.display_on = self.has_display
            self._latched_display_off = False
            # R variant = has a damper output (1134 not "disabled").
            self.r_variant = self.input.get(R.DAMPER, 2) != 2
            self.pump_configured = self.input.get(R.WATER_VALVE_PUMP, 0) != 2
            self.fan_model = self.default_fan_model
            self.sequence_delay = self.default_sequence_delay
            self.alarms: set[str] = set()
            self.unplugged: set[int] = set()
            self.pump_fault = False
            self.ignore_writes: set[int] = set()
            # {register: n}: a write shows in reads only after n reads of it
            # (a unit that mirrors a request into its register late).
            self.lag_reads: dict[int, int] = {}
            self._staged: dict[int, list[int]] = {}
            self.forced: dict[int, int] = {}
            self.write_log: list[Write] = []
            self._running_since: Optional[float] = None
            self._auto_dehum = False
            self._auto_int = False
            self._mode_base = 4 if self.input.get(R.MODE_STATUS, 0) in (4, 5) else 0
            self._recompute()

    def power_cycle(self) -> None:
        """Mains off/on: the unit keeps every setting.

        Its memory keeps data on a power failure (installation manual), and a
        real unit read PH01 = 0, HA00 = 0, PH02 = 1 unchanged after one. Whether
        the Modbus requests (1105/1139/1140) survive is unverified; they are
        kept too.
        """
        with self._lock:
            self._staged.clear()
            self._recompute()

    # ---- Modbus access -------------------------------------------------------
    def read(self, kind: str, address: int, count: int) -> list[int]:
        """Read ``count`` registers; ``kind`` is ``"input"`` or ``"holding"``."""
        with self._lock:
            self._recompute()  # time-based sequence steps
            table = self.input if kind == "input" else self.holding
            if kind == "holding":
                self._release_staged(range(address, address + count))
            missing = [a for a in range(address, address + count) if a not in table]
            if missing:
                raise IllegalAddress(f"{kind} {missing[0]}")
            return [table[a] for a in range(address, address + count)]

    def write(self, address: int, value: int) -> int:
        """Write one holding register; returns the value the device stores."""
        with self._lock:
            value &= 0xFFFF
            if address not in self.holding:
                self.write_log.append(Write(address, value, False, None))
                raise IllegalAddress(f"holding {address}")
            accepted = self._apply_write(address, value)
            self.write_log.append(
                Write(address, value, accepted, self.holding[address])
            )
            self._recompute()
            return self.holding[address]

    def _release_staged(self, addresses: range) -> None:
        """Count a read against each lagging write; apply the ones that are due."""
        for addr in [a for a in self._staged if a in addresses]:
            value, left = self._staged[addr]
            if left > 0:
                self._staged[addr][1] = left - 1
                continue
            del self._staged[addr]
            self.holding[addr] = value
            self._recompute()

    def _apply_write(self, address: int, value: int) -> bool:
        """Store a write the way the unit would. False = acknowledged, ignored."""
        if address in self.ignore_writes:
            return False
        enable = R.ENABLE_FOR.get(address)
        if enable is not None and self.holding.get(enable) != 1:
            return False
        if address == R.HB04_SEASON:
            self.holding[address] = value
            if value in (R.SEASON_SUMMER, R.SEASON_WINTER):
                self.alarms.discard("AL25")
            else:
                self.alarms.add("AL25")
            return True
        if address == R.HUMIDITY_SETPOINT:
            low = self.holding.get(R.PH29_HUM_MIN, 0)
            high = self.holding.get(R.PH30_HUM_MAX, 100)
            self.holding[address] = max(low, min(high, value))
            return True
        if address in R.ALARM_RESET_RANGE:
            if value == 1:
                self.alarms.discard(f"AL{address - R.ALARM_RESET_BASE:02d}")
            self.holding[address] = 0
            return True
        if address == R.FAN_HOURS and value == 0:
            self.alarms.discard("AL22")
        if self.lag_reads.get(address):
            self._staged[address] = [value, self.lag_reads[address]]
            return True
        self.holding[address] = value
        return True

    # ---- fault injection -----------------------------------------------------
    def raise_alarm(self, code: str) -> None:
        with self._lock:
            R.alarm_bit(code)  # validate
            self.alarms.add(_norm(code))
            self._recompute()

    def clear_alarm(self, code: str) -> None:
        with self._lock:
            self.alarms.discard(_norm(code))
            self._recompute()

    def unplug_probe(self, address: int = R.ROOM_TEMP) -> None:
        with self._lock:
            self.unplugged.add(address)
            self._recompute()

    def plug_probe(self, address: int, raw: int) -> None:
        with self._lock:
            self.unplugged.discard(address)
            self.input[address] = raw & 0xFFFF
            self._recompute()

    def set_input(self, address: int, raw: int) -> None:
        with self._lock:
            self.input[address] = raw & 0xFFFF
            self._recompute()

    def set_holding(self, address: int, raw: int) -> None:
        """Change a setting as if done on the unit itself (not via Modbus)."""
        with self._lock:
            self.holding[address] = raw & 0xFFFF
            if address == R.HB04_SEASON:
                if raw in (R.SEASON_SUMMER, R.SEASON_WINTER):
                    self.alarms.discard("AL25")
                else:
                    self.alarms.add("AL25")
            self._recompute()

    def force_input(self, address: int, raw: Optional[int]) -> None:
        """Pin an input register to ``raw`` whatever the model computes
        (``None`` releases it) - e.g. a status value outside the enums."""
        with self._lock:
            if raw is None:
                self.forced.pop(address, None)
            else:
                self.forced[address] = raw & 0xFFFF
            self._recompute()

    def set_water_temperature(self, celsius: float) -> None:
        self.set_input(R.WATER_TEMP, round(celsius * 10))

    def set_room_humidity(self, percent: int) -> None:
        self.set_input(R.ROOM_HUMIDITY, int(percent))

    def set_pump_fault(self, fault: bool = True) -> None:
        with self._lock:
            self.pump_fault = fault
            self._recompute()

    def latch_display_off(self) -> None:
        """The stored display OFF a real unit keeps after PH01 = 0 (headless).

        Seen on hardware: PH01 = 0 and a power cycle did not clear it; the
        first Modbus ON did.
        """
        with self._lock:
            self._latched_display_off = True
            self._recompute()

    def set_display_on(self, on: bool) -> None:
        with self._lock:
            self.display_on = on
            self._recompute()

    def set_fan_model(self, model: str) -> None:
        if model not in FAN_MODELS:
            raise ValueError(f"fan_model must be one of {FAN_MODELS}")
        with self._lock:
            self.fan_model = model
            self._recompute()

    # ---- derived state -------------------------------------------------------
    def _unit_status(self) -> int:
        h = self.holding
        if h.get(R.PH01_ONOFF_DISPLAY) == 1 and not (
            self.has_display and self.display_on
        ):
            return 0  # off_by_display: OFF from the display (absent or off) wins
        if self._latched_display_off:
            if h.get(R.PH02_ONOFF_BMS) == 1 and h.get(R.BMS_ON) == 1:
                self._latched_display_off = False
            else:
                return 0  # stored display OFF, cleared by the first Modbus ON
        if h.get(R.PH02_ONOFF_BMS) == 1:
            return 5 if h.get(R.BMS_ON) == 1 else 2  # on / off_by_bms
        if h.get(R.PH01_ONOFF_DISPLAY) == 1:
            return 5  # display alone controls it, and it is on
        return 2

    def _probe_alarms(self, status: int) -> set[str]:
        """AL28/AL34: a probe is allocated but reads the unwired sentinel.

        Not raised while the unit is off_by_display (UNIT_BEHAVIOUR.md 8, T4).
        """
        if status == 0:
            return set()
        found = set()
        h, i = self.holding, self.input
        if h.get(R.HA02_AI2) in R.ROOM_TEMP_PROBE_CODES and _sentinel(i[R.ROOM_TEMP]):
            found.add("AL28")
        if h.get(R.HA03_AI3) in R.ROOM_HUMIDITY_PROBE_CODES and _sentinel(
            i[R.ROOM_HUMIDITY]
        ):
            found.add("AL34")
        return found

    def _auto_dehumidify(self, on: bool, summer: bool, alarms: set[str]) -> bool:
        """The unit's own DEU request from the room humidity (handbook 6.1.1).

        Needs a humidity source: a display with H (HA00) that is fitted and on,
        or a probe on AI3. On above PU01 + PU07, off below PU01; in winter only
        if PU02 allows dehumidifying.
        """
        h, i = self.holding, self.input
        source = h.get(R.HA03_AI3) in R.ROOM_HUMIDITY_PROBE_CODES or (
            self.has_display
            and self.display_on
            and h.get(R.HA00_PROBE_SOURCE) in R.DISPLAY_HUMIDITY_SOURCES
        )
        room = i.get(R.ROOM_HUMIDITY, R.PROBE_SENTINEL)
        if not (
            on
            and source
            and "AL34" not in alarms
            and not _sentinel(room)
            and (summer or h.get(R.PU02_WINTER_DEHUM, 0))
        ):
            self._auto_dehum = False
            return False
        setpoint = h.get(R.HUMIDITY_SETPOINT, 0)
        if room > setpoint + h.get(R.PU07_DEHUM_DIFF, 0):
            self._auto_dehum = True
        elif room < setpoint:
            self._auto_dehum = False
        return self._auto_dehum

    def _auto_integration(self, on: bool, summer: bool, alarms: set[str]) -> bool:
        """The unit's own INT request from the room temperature (handbook 6.1.2).

        Needs a temperature source: a display (HA00) that is fitted and on, or
        a probe on AI2. Summer: on above SEtC + PF12, off below SEtC - PF12.
        Winter: on below SEtH - PF12, off above SEtH + PF12. SEtH is clamped to
        PH09..PH10 (factory 14 degC both).
        """
        h, i = self.holding, self.input
        source = h.get(R.HA02_AI2) in R.ROOM_TEMP_PROBE_CODES or (
            self.has_display
            and self.display_on
            and h.get(R.HA00_PROBE_SOURCE) in R.DISPLAY_TEMP_SOURCES
        )
        room = i.get(R.ROOM_TEMP, R.PROBE_SENTINEL)
        if not (on and source and "AL28" not in alarms and not _sentinel(room)):
            self._auto_int = False
            return False
        room = _int16(room)
        band = h.get(R.PF12_TEMP_DEAD_BAND, 0)
        if summer:
            setpoint = _int16(h.get(R.SUMMER_SETPOINT, 0))
            if room > setpoint + band:
                self._auto_int = True
            elif room < setpoint - band:
                self._auto_int = False
        else:
            setpoint = _int16(h.get(R.WINTER_SETPOINT, 0))
            low = _int16(h.get(R.PH09_WINTER_SETPOINT_MIN, setpoint))
            high = _int16(h.get(R.PH10_WINTER_SETPOINT_MAX, setpoint))
            setpoint = max(low, min(high, setpoint))
            if room < setpoint - band:
                self._auto_int = True
            elif room > setpoint + band:
                self._auto_int = False
        return self._auto_int

    def _fan_band(self, deu: bool, integ: bool) -> tuple[int, int]:
        h = self.holding
        if integ:
            return h.get(R.PF27_FAN_MIN_INT, 5000), h.get(R.PF09_FAN_MAX_INT, 8500)
        if deu:
            return h.get(R.PF28_FAN_MIN_DEU, 5000), h.get(R.PF10_FAN_MAX_DEU, 8500)
        return h.get(R.PF07_FAN_MIN_VMC, 3000), 10000

    def _fan_output(self, request: int, band: tuple[int, int]) -> int:
        low, high = band
        request = max(0, min(10000, request))
        if self.fan_model == "direct":
            return request
        if self.fan_model == "clamp":
            return max(low, min(high, request))
        return round(low + request * (high - low) / 10000)

    def _recompute(self) -> None:
        h, i = self.holding, self.input
        for addr in self.unplugged:
            i[addr] = R.PROBE_SENTINEL

        summer = h.get(R.HB04_SEASON, R.SEASON_SUMMER) != R.SEASON_WINTER
        i[R.SEASON_READBACK] = 0 if summer else 1
        i[R.MODE_STATUS] = self._mode_base + (0 if summer else 1)
        setpoint = R.SUMMER_SETPOINT if summer else R.WINTER_SETPOINT
        i[R.ACTUAL_SETPOINT] = h.get(setpoint, 0)
        i[R.FAN_MANUAL_REQUEST] = h.get(R.FAN_MANUAL, 0)

        status = self._unit_status()
        alarms = set(self.alarms) | self._probe_alarms(status)
        shutdown = bool(alarms & set(SHUTDOWN_ALARMS))
        i[R.UNIT_STATUS] = status

        on = status == 5 and not shutdown
        # Request sources are ORed: Modbus (only with its PH28/PH27 enable,
        # handbook 6.1) and the unit's own room-probe logic.
        modbus_deu = h.get(R.DEU_REQUEST) == 1 and h.get(R.PH28_DEU_BMS) == 1
        modbus_int = h.get(R.INT_REQUEST) == 1 and h.get(R.PH27_INT_BMS) == 1
        deu = modbus_deu or self._auto_dehumidify(on, summer, alarms)
        integ = (modbus_int or self._auto_integration(on, summer, alarms)) and h.get(
            R.PG02_INTEGRATION
        ) == 1
        # AL03 disables summer integration, AL04 winter integration (heating).
        if ("AL03" if summer else "AL04") in alarms:
            integ = False
        # PU13: no dehumidifying while the room is colder than this.
        room = i.get(R.ROOM_TEMP, R.PROBE_SENTINEL)
        too_cold = not _sentinel(room) and _int16(room) < h.get(R.PU13_MIN_ROOM_TEMP, 0)
        request = on and (deu or integ) and not (too_cold and not integ)
        if request and self._running_since is None:
            self._running_since = time.monotonic()
        elif not request:
            self._running_since = None
        started = request and (
            time.monotonic() - (self._running_since or 0) >= self.sequence_delay
        )
        heating = integ and not summer
        manual_fan = on and not request and h.get(R.FAN_MANUAL, 0) > 0

        i[R.DEHUM_REQUEST] = 1 if request and not heating else 0
        # 1112 (FanIntegration_Request, a 0-100 % fan request) is left as
        # dumped: it stayed 0 through recirculating dehumidify runs, and its
        # value during INT is not yet seen on hardware.
        if self.r_variant:
            i[R.DAMPER] = 1 if request else 0
        if self.pump_configured:
            i[R.WATER_VALVE_PUMP] = 1 if request and not self.pump_fault else 0

        # Fan
        if not (request or manual_fan):
            i[R.FAN_STATUS] = 1
            out = 0
        elif request and not started:
            i[R.FAN_STATUS] = 2  # wait_on (PS01 damper pre-start)
            out = 0
        else:
            i[R.FAN_STATUS] = 3
            out = self._fan_output(h.get(R.FAN_MANUAL, 0), self._fan_band(deu, integ))
        i[R.FAN_OUTPUT] = out
        # The speed needs a tachometer input; without one 1117 reads 0 with the
        # fan running (UNIT_BEHAVIOUR.md 9.1, T16, T21).
        tachometer = any(
            h.get(a) in R.TACHOMETER_CODES for a in R.TACHOMETER_ALLOCATIONS
        )
        i[R.FAN_RPM] = round(out * 0.28) if tachometer else 0  # ~2800 rpm at 100 %

        # Compressor: dehumidify / summer integration; winter integration heats
        # with warm water only.
        if alarms & set(COMPRESSOR_ALARMS):
            i[R.COMPRESSOR_STATUS] = 1
        elif request and not heating:
            i[R.COMPRESSOR_STATUS] = 4 if started else 3
        else:
            i[R.COMPRESSOR_STATUS] = 6
        i[R.COMPRESSOR_OUTPUT] = 10000 if i[R.COMPRESSOR_STATUS] == 4 else 0

        words = {R.ALARMS_1: 0, R.ALARMS_2: 0, R.ALARMS_3: 0}
        for code in alarms:
            reg, bit = R.alarm_bit(code)
            words[reg] |= 1 << bit
        i.update(words)
        i[R.ANY_ALARM] = 1 if alarms else 0
        self.active_alarms = alarms
        i.update(self.forced)

    # ---- introspection -------------------------------------------------------
    def writes_to(self, address: int) -> list[Write]:
        with self._lock:
            return [w for w in self.write_log if w.address == address]

    def clear_write_log(self) -> None:
        with self._lock:
            self.write_log.clear()

    def state(self) -> dict:
        """Summary for the control API and for debugging."""
        with self._lock:
            i, h = self.input, self.holding
            return {
                "seed": self.seed_name,
                "overlays": list(self.overlays),
                "has_display": self.has_display,
                "display_on": self.display_on,
                "fan_model": self.fan_model,
                "alarms": sorted(self.active_alarms),
                "unit_status": i[R.UNIT_STATUS],
                "season": i[R.SEASON_READBACK],
                "fan_status": i[R.FAN_STATUS],
                "fan_output": i[R.FAN_OUTPUT],
                "compressor_status": i[R.COMPRESSOR_STATUS],
                "damper": i.get(R.DAMPER),
                "pump": i.get(R.WATER_VALVE_PUMP),
                "holding": {str(a): h[a] for a in sorted(h)},
                "input": {str(a): i[a] for a in sorted(i)},
                "writes": [w.as_dict() for w in self.write_log],
            }


def _norm(code: str) -> str:
    return f"AL{int(code.upper().removeprefix('AL')):02d}"


def _int16(raw: int) -> int:
    return raw - 0x10000 if raw & 0x8000 else raw


def _sentinel(raw: int) -> bool:
    return 0x7FF0 <= raw <= 0x800F
