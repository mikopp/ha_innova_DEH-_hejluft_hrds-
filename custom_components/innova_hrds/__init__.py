"""Innova HRDS+ / hej.luft dehumidifier — Modbus TCP integration."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter
from pymodbus.client import ModbusTcpClient

from .const import (
    BMS_ENABLE_KEYS,
    BRINE_GUARD_MAX_AGE_HOURS,
    C_ACTIVE_COOLING,
    C_AI2_ALLOCATION,
    C_AI3_ALLOCATION,
    C_ALARM_ANTIFREEZE,
    C_ALARM_HIGH_WATER_TEMP,
    C_ALARM_LOW_WATER_TEMP,
    C_BRINE_GUARD,
    C_COMPRESSOR_STATUS,
    C_DEHUMIDIFY,
    C_DT_INT16,
    C_ENABLE_FREE_COOLING,
    C_MAX_BLOCK,
    C_MAX_GAP,
    C_MAX_TOTAL_AIRFLOW,
    C_OPERATING_MODE,
    C_OUTDOOR_TEMPERATURE,
    C_REG_TYPE_HOLDING_REGISTERS,
    C_REG_TYPE_INPUT_REGISTERS,
    C_ROOM_HUMIDITY,
    C_ROOM_TEMPERATURE,
    C_SEASON,
    C_SETUP_CHECK,
    C_SUPPLY_FAN_AIRFLOW,
    C_SUPPLY_FAN_MAX_AIRFLOW,
    C_SUPPLY_FAN_OUTPUT,
    C_SUPPLY_FAN_STATUS,
    C_TEMPERATURE_UNIT,
    C_TIME_PROGRAMS,
    C_UNIT_ON_OFF,
    C_UNIT_STATUS,
    C_WATER_CHECK,
    C_WATER_TEMPERATURE,
    C_WATER_VALVE_PUMP,
    C_WINTER_DEHUM,
    CONF_AIRFLOW_MAX,
    CONF_ALLOW_WINTER_HEATING,
    CONF_BRINE_MIN_TEMPERATURE,
    CONF_BRINE_TEMPERATURE_ENTITY,
    CONF_HAS_DISPLAY,
    CONF_HOSTID,
    CONF_MODEL,
    CONF_WATER_CIRCUIT,
    DEFAULT_ALLOW_WINTER_HEATING,
    DEFAULT_BRINE_MIN_TEMPERATURE,
    DEFAULT_HAS_DISPLAY,
    DEFAULT_HOSTID,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WATER_CIRCUIT,
    ENTITIES_DICT,
    HEADLESS_SETTINGS,
    HUMIDITY_TARGET_KEYS,
    MODEL_SPECS,
    OPERATIONAL_KEYS,
    ROOM_HUMIDITY_PROBE_CODES,
    ROOM_TEMP_PROBE_CODES,
    TEMPERATURE_TARGET_KEYS,
    WATER_CIRCUIT_BRINE,
    get_entity_bitmask,
    get_entity_factor,
    get_entity_props,
    get_entity_reg,
    get_entity_select,
    get_entity_switch,
    get_entity_type,
    is_entity_readonly,
    is_entity_select,
    is_entity_switch,
    is_probe_sentinel,
)
from .entity_common import build_device_infos
from .identity import CannotConnect, DeviceIdentity, WrongDevice, verify_device
from .installer_params import installer_key

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.CLIMATE,
    Platform.FAN,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    name = entry.data.get(CONF_NAME)
    host = entry.options.get(CONF_HOST, entry.data.get(CONF_HOST))
    port = entry.options.get(CONF_PORT, entry.data.get(CONF_PORT, DEFAULT_PORT))
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    try:
        scan_interval = max(int(scan_interval), 5)
    except (TypeError, ValueError):
        scan_interval = DEFAULT_SCAN_INTERVAL
    hostid = entry.options.get(CONF_HOSTID, entry.data.get(CONF_HOSTID, DEFAULT_HOSTID))
    try:
        hostid = int(hostid)
    except (TypeError, ValueError):
        hostid = DEFAULT_HOSTID

    model = entry.options.get(CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL))
    spec = MODEL_SPECS.get(model, MODEL_SPECS[DEFAULT_MODEL])
    try:
        airflow_max = float(
            entry.options.get(
                CONF_AIRFLOW_MAX, entry.data.get(CONF_AIRFLOW_MAX, spec["max"])
            )
        )
    except (TypeError, ValueError):
        airflow_max = spec["max"]

    has_display = bool(
        entry.options.get(
            CONF_HAS_DISPLAY, entry.data.get(CONF_HAS_DISPLAY, DEFAULT_HAS_DISPLAY)
        )
    )

    allow_winter_heating = bool(
        entry.options.get(
            CONF_ALLOW_WINTER_HEATING,
            entry.data.get(CONF_ALLOW_WINTER_HEATING, DEFAULT_ALLOW_WINTER_HEATING),
        )
    )
    water_circuit = entry.options.get(
        CONF_WATER_CIRCUIT, entry.data.get(CONF_WATER_CIRCUIT, DEFAULT_WATER_CIRCUIT)
    )
    # Once options exist they are authoritative: clearing the entity in the
    # options form must not fall back to the one given at initial setup.
    brine_source = entry.options if entry.options else entry.data
    brine_entity = brine_source.get(CONF_BRINE_TEMPERATURE_ENTITY) or None
    try:
        brine_min = float(
            brine_source.get(CONF_BRINE_MIN_TEMPERATURE, DEFAULT_BRINE_MIN_TEMPERATURE)
        )
    except (TypeError, ValueError):
        brine_min = DEFAULT_BRINE_MIN_TEMPERATURE

    # Refuse to write configuration registers into something that is not an
    # HRDS+ (wrong IP, wrong slave id behind a shared gateway).
    try:
        identity = await hass.async_add_executor_job(verify_device, host, port, hostid)
    except CannotConnect as exc:
        raise ConfigEntryNotReady(
            f"Cannot reach HRDS+ at {host}:{port}: {exc}"
        ) from exc
    except WrongDevice as exc:
        raise ConfigEntryError(
            f"{host}:{port} (unit id {hostid}) is not an HRDS+: {exc}"
        ) from exc

    hub = HrdsModbusHub(
        hass,
        name,
        host,
        port,
        scan_interval,
        hostid,
        airflow_max,
        has_display,
        identity,
        allow_winter_heating,
        water_circuit,
        brine_entity,
        brine_min,
    )

    # Prime the cache before creating entities so they do not sit at `unknown`
    # for a whole scan interval, and so an unreachable device is reported as
    # such instead of setting up permanently-stale entities.
    if not await hass.async_add_executor_job(hub._do_read_cycle):
        raise ConfigEntryNotReady(f"Cannot reach HRDS+ Modbus gateway at {host}:{port}")

    # runtime_data is keyed by the config entry, so two entries sharing a name
    # can no longer clobber each other's hub the way hass.data[DOMAIN][name] did.
    entry.runtime_data = hub
    hub.update_brine_guard()
    if brine_entity:
        # Re-judge the guard as soon as the source sensor reports, not only on
        # the next poll.
        entry.async_on_unload(
            async_track_state_change_event(
                hass, [brine_entity], hub.async_brine_state_changed
            )
        )
    # Decided from the primed read-back; changing HA02/HA03 needs a reload.
    hub.update_hidden_keys()

    # Register the devices up front, parent first: the setup and installer
    # devices point at the main one via `via_device`, which must already exist.
    registry = dr.async_get(hass)
    for info in build_device_infos(entry, hub):
        registry.async_get_or_create(config_entry_id=entry.entry_id, **info)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hub = getattr(entry, "runtime_data", None)
        if hub is not None:
            await hass.async_add_executor_job(hub.shutdown)
    return unload_ok


def _build_blocks(
    addresses: List[int], foreign: frozenset[int] = frozenset()
) -> List[Tuple[int, int]]:
    """Group sorted addresses into (start, count) blocks for block reads.

    Adjacent addresses (gap <= C_MAX_GAP) are merged; each block is capped at
    C_MAX_BLOCK registers so we never exceed the Modbus per-request limit.

    ``foreign`` holds the addresses that belong to the *other* function code. A
    block is never allowed to span one: reading e.g. holding register 1105 with
    FC 04 can return ILLEGAL DATA ADDRESS, which would fail the whole block.
    """
    addresses = sorted({a for a in addresses if a is not None})
    if not addresses:
        return []
    blocks: List[Tuple[int, int]] = []
    start = prev = addresses[0]
    for addr in addresses[1:]:
        fits = addr - prev <= C_MAX_GAP and addr - start + 1 <= C_MAX_BLOCK
        spans_foreign = any(a in foreign for a in range(prev + 1, addr))
        if fits and not spans_foreign:
            prev = addr
        else:
            blocks.append((start, prev - start + 1))
            start = prev = addr
    blocks.append((start, prev - start + 1))
    return blocks


class HrdsModbusHub:
    """Thread-safe pymodbus wrapper that polls the configured registers."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        host: str,
        port: int,
        scan_interval: int,
        hostid: int,
        airflow_max: float,
        has_display: bool = DEFAULT_HAS_DISPLAY,
        identity: Optional[DeviceIdentity] = None,
        allow_winter_heating: bool = DEFAULT_ALLOW_WINTER_HEATING,
        water_circuit: str = DEFAULT_WATER_CIRCUIT,
        brine_entity: Optional[str] = None,
        brine_min_temperature: float = DEFAULT_BRINE_MIN_TEMPERATURE,
    ) -> None:
        self._hass = hass
        self._name = name
        self._has_display = has_display
        self.water_circuit = water_circuit
        # A brine circuit cannot heat (handbook 3.8.7), whatever the option says.
        self.allow_winter_heating = (
            allow_winter_heating and water_circuit != WATER_CIRCUIT_BRINE
        )
        # Optional brine temperature guard (a Home Assistant sensor entity).
        # brine_guard_ok is None while no guard is configured.
        self.brine_entity = brine_entity or None
        self.brine_min_temperature = brine_min_temperature
        self.brine_guard_ok: Optional[bool] = None
        self.brine_guard_reason: Optional[str] = None
        self.brine_temperature: Optional[float] = None
        self.brine_last_reported: Optional[datetime] = None
        self.identity = identity or DeviceIdentity()
        self._client = ModbusTcpClient(host=host, port=port, timeout=3, retries=3)
        self._lock = threading.Lock()
        self._hostid = hostid
        self._scan_interval = timedelta(seconds=scan_interval)
        self._unsub: Optional[Any] = None
        self._sensors: list = []
        self._airflow_max = airflow_max
        self._pending_refresh: Optional[Any] = None
        # False until a full read cycle succeeds; entities key their
        # availability off this so a dead gateway is visible in HA.
        self.last_update_success = False
        self.data: Dict[str, Any] = {}
        # Gate for requests that make the unit act. Off until the user has gone
        # through the setup checks and turned the switch on; restored by the
        # switch entity across restarts.
        self.operation_allowed = False
        self.setup_issues: list[str] = []
        self.water_issues: list[str] = []
        # Setpoint entities not created because nothing makes them act.
        self.hidden_keys: frozenset[str] = frozenset()
        self.show_temperature_target = True
        self.show_humidity_target = True

        # Pre-compute the block reads per register type, keeping each function
        # code's blocks clear of the other's addresses.
        input_addrs = [
            get_entity_reg(p)[0]
            for p in ENTITIES_DICT.values()
            if get_entity_type(p) == C_REG_TYPE_INPUT_REGISTERS
        ]
        holding_addrs = [
            get_entity_reg(p)[0]
            for p in ENTITIES_DICT.values()
            if get_entity_type(p) == C_REG_TYPE_HOLDING_REGISTERS
        ]
        self._input_blocks = _build_blocks(input_addrs, frozenset(holding_addrs))
        self._holding_blocks = _build_blocks(holding_addrs, frozenset(input_addrs))

    @property
    def name(self) -> str:
        return self._name

    # ---- listener registration -------------------------------------------
    @callback
    def async_add_my_modbus_sensor(self, update_callback) -> None:
        if not self._sensors:
            self._unsub = async_track_time_interval(
                self._hass, self.async_refresh_modbus_data, self._scan_interval
            )
        self._sensors.append(update_callback)

    @callback
    def async_remove_my_modbus_sensor(self, update_callback) -> None:
        if update_callback in self._sensors:
            self._sensors.remove(update_callback)
        if not self._sensors and self._unsub:
            self._unsub()
            self._unsub = None
            # Hand the socket close to an executor: it acquires the same lock a
            # poll in flight may hold, which would stall the event loop.
            self._hass.async_add_executor_job(self.close)

    @property
    def is_brine(self) -> bool:
        return self.water_circuit == WATER_CIRCUIT_BRINE

    @property
    def season(self) -> Optional[str]:
        """The season the unit reports (1583): summer, winter, auto or None."""
        return self.data.get(C_OPERATING_MODE)

    def update_hidden_keys(self) -> None:
        """Hide setpoints the unit cannot act on.

        Without a display the unit only regulates on its setpoints when a room
        probe is wired and allocated (handbook 6.7; Modbus manual: "Die
        Soll-Werte sind nur wirksam, wenn das Display vorhanden ist oder externe
        Sensoren angeschlossen sind"). Otherwise Home Assistant decides when to
        request, and an editable target would only mislead.
        """
        d = self.data
        self.show_temperature_target = self._has_display or (
            d.get(C_AI2_ALLOCATION) in ROOM_TEMP_PROBE_CODES
        )
        self.show_humidity_target = self._has_display or (
            d.get(C_AI3_ALLOCATION) in ROOM_HUMIDITY_PROBE_CODES
        )
        hidden: set[str] = set()
        if not self.show_temperature_target:
            hidden |= TEMPERATURE_TARGET_KEYS
        if not self.show_humidity_target:
            hidden |= HUMIDITY_TARGET_KEYS
        if not self.brine_entity:
            hidden.add(C_BRINE_GUARD)
        self.hidden_keys = frozenset(hidden)

    # ---- brine temperature guard -----------------------------------------
    def _read_brine_sensor(
        self,
    ) -> Tuple[Optional[str], Optional[float], Optional[datetime]]:
        """(reason the guard blocks or None, temperature in degC, last report)."""
        state = self._hass.states.get(self.brine_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return "unavailable", None, None
        # last_reported moves on every report, also when the value is unchanged;
        # last_updated would call a steady sensor stale.
        reported = state.last_reported
        try:
            value = float(state.state)
        except ValueError:
            return "not_a_number", None, reported
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit and unit != UnitOfTemperature.CELSIUS:
            try:
                value = TemperatureConverter.convert(
                    value, unit, UnitOfTemperature.CELSIUS
                )
            except (HomeAssistantError, KeyError, ValueError):
                return "not_a_temperature", None, reported
        if dt_util.utcnow() - reported > timedelta(hours=BRINE_GUARD_MAX_AGE_HOURS):
            return "stale", value, reported
        if value < self.brine_min_temperature:
            return "too_cold", value, reported
        return None, value, reported

    @callback
    def update_brine_guard(self) -> None:
        """Re-judge the brine guard from the configured sensor (event loop)."""
        if not self.brine_entity:
            self.brine_guard_ok = None
            self.brine_guard_reason = None
            return
        reason, value, reported = self._read_brine_sensor()
        self.brine_guard_ok = reason is None
        self.brine_guard_reason = reason
        self.brine_temperature = value
        self.brine_last_reported = reported
        # Problem indicator: on = the guard blocks requests.
        self.data[C_BRINE_GUARD] = "off" if self.brine_guard_ok else "on"

    @callback
    def async_brine_state_changed(self, _event: Event) -> None:
        self.update_brine_guard()
        self._compute_derived()
        for cb in self._sensors:
            cb()

    def _brine_guard_message(self) -> str:
        if self.brine_guard_reason == "too_cold":
            why = (
                f"reads {self.brine_temperature:.1f} degC, below the safe "
                f"{self.brine_min_temperature:.1f} degC"
            )
        else:
            why = {
                "unavailable": "is unavailable",
                "not_a_number": "does not report a number",
                "not_a_temperature": "does not report a temperature",
                "stale": f"has not reported for over {BRINE_GUARD_MAX_AGE_HOURS} h",
            }.get(self.brine_guard_reason, "blocks requests")
        return f"Brine temperature guard: {self.brine_entity} {why}."

    def _check_request_allowed(self, entity_key: str, raw: int) -> None:
        """Refuse requests that would heat, or freeze a brine coil.

        The integration (INT) request cools in summer but HEATS in winter, and
        dehumidifying in winter on a brine circuit risks freezing the coil.
        Raises ServiceValidationError; switching things off always passes.
        """
        winter = self.season != "summer"
        d = self.data
        requests_on = d.get(C_DEHUMIDIFY) == "on" or d.get(C_ACTIVE_COOLING) == "on"
        starts = bool(raw) and (
            entity_key in (C_DEHUMIDIFY, C_ACTIVE_COOLING)
            or (entity_key == C_UNIT_ON_OFF and requests_on)
        )
        if self.brine_entity:
            # Judge the sensor as of now, not as of the last poll.
            self.update_brine_guard()
        if starts and self.brine_entity and not self.brine_guard_ok:
            # A configured guard is checked in every season.
            raise ServiceValidationError(self._brine_guard_message())
        # On brine, winter dehumidifying needs a passing guard: the unit only
        # dehumidifies with brine flowing, and cold brine freezes the register.
        brine_winter_ok = self.brine_guard_ok is True
        if entity_key == C_ACTIVE_COOLING and raw and winter:
            if self.is_brine:
                raise ServiceValidationError(
                    "The unit is not in summer season, where an integration "
                    "request heats - impossible on a brine circuit."
                )
            if not self.allow_winter_heating:
                raise ServiceValidationError(
                    "The unit is not in summer season, where an integration "
                    "request heats. Enable 'Allow winter heating' in the "
                    "integration options to permit it."
                )
        if (
            entity_key == C_DEHUMIDIFY
            and raw
            and winter
            and self.is_brine
            and not brine_winter_ok
        ):
            raise ServiceValidationError(
                "Dehumidifying in winter on a brine circuit needs a brine "
                "temperature guard (the water register can freeze). Configure "
                "one in the integration options."
            )
        if entity_key == C_SEASON and raw == 3:  # 3 = winter
            if (
                self.data.get(C_ACTIVE_COOLING) == "on"
                and not self.allow_winter_heating
            ):
                raise ServiceValidationError(
                    "An integration request is active and would turn into "
                    "heating in winter. Turn it off first."
                )
            if (
                self.data.get(C_DEHUMIDIFY) == "on"
                and self.is_brine
                and not brine_winter_ok
            ):
                raise ServiceValidationError(
                    "A dehumidify request is active; on a brine circuit it must "
                    "not run in winter without a brine temperature guard. Turn "
                    "it off first."
                )

    @callback
    def set_operation_allowed(self, allowed: bool) -> None:
        """Open or close the operational-request gate and refresh the check."""
        self.operation_allowed = allowed
        self._compute_derived()
        for cb in self._sensors:
            cb()

    def close(self) -> None:
        with self._lock:
            self._client.close()

    def shutdown(self) -> None:
        """Close the socket during unload (runs in an executor, not the loop)."""
        self.close()

    # ---- polling ----------------------------------------------------------
    async def async_refresh_modbus_data(self, _now=None) -> None:
        if not self._sensors:
            return
        # Before the read cycle, so the water check it computes is current
        # (also catches a sensor that went silent: no event marks it stale).
        self.update_brine_guard()
        await self._hass.async_add_executor_job(self._do_read_cycle)
        # Notify on failure too - that is what moves entities to `unavailable`.
        for cb in self._sensors:
            cb()

    @callback
    def async_schedule_refresh(self, delay: float = 1.5) -> None:
        """Debounced refresh after a write.

        Gives the unit a moment to mirror the command into its status registers
        and coalesces the several writes of one HVAC mode change into a single
        poll instead of one full cycle per register.
        """
        if self._pending_refresh is not None:
            self._pending_refresh()

        async def _run(_now) -> None:
            self._pending_refresh = None
            await self.async_refresh_modbus_data()

        self._pending_refresh = async_call_later(self._hass, delay, _run)

    def _do_read_cycle(self) -> bool:
        with self._lock:
            if not self._client.connect():
                _LOGGER.warning("Modbus connect to HRDS+ failed")
                self.last_update_success = False
                return False
            try:
                # Uses the previous cycle's read-back, so on the very first
                # cycle (empty data) every required setting is written.
                self._sync_required_settings_locked()
                raw_input = self._read_blocks(self._input_blocks, fc="input")
                raw_holding = self._read_blocks(self._holding_blocks, fc="holding")
            finally:
                self._client.close()

        if raw_input is None or raw_holding is None:
            self.last_update_success = False
            return False
        self._decode_all(raw_input, raw_holding)
        self._compute_derived()
        self.last_update_success = True
        return True

    def _read_blocks(self, blocks, fc: str) -> Optional[Dict[int, int]]:
        """Read every block of a register type into an {address: raw} map."""
        values: Dict[int, int] = {}
        for start, count in blocks:
            if fc == "input":
                resp = self._client.read_input_registers(
                    address=start, count=count, device_id=self._hostid
                )
            else:
                resp = self._client.read_holding_registers(
                    address=start, count=count, device_id=self._hostid
                )
            if resp is None or resp.isError() or not getattr(resp, "registers", None):
                _LOGGER.warning(
                    "Modbus block read failed (%s @ %s+%s); retrying individually",
                    fc,
                    start,
                    count,
                )
                if not self._read_block_individually(values, start, count, fc):
                    return None
                continue
            for offset, reg in enumerate(resp.registers):
                values[start + offset] = reg
        return values

    def _read_block_individually(
        self, values: Dict[int, int], start: int, count: int, fc: str
    ) -> bool:
        """Re-read a failed block one register at a time.

        Drops only the addresses the device rejects, so a single bad address
        cannot take out every entity in the integration. Returns False only if
        the whole range is unreadable (a genuine comms failure).
        """
        any_ok = False
        for addr in range(start, start + count):
            try:
                if fc == "input":
                    resp = self._client.read_input_registers(
                        address=addr, count=1, device_id=self._hostid
                    )
                else:
                    resp = self._client.read_holding_registers(
                        address=addr, count=1, device_id=self._hostid
                    )
            except Exception as exc:  # noqa: BLE001 - one bad address is not fatal
                _LOGGER.debug("Read of %s register %s raised: %r", fc, addr, exc)
                continue
            if resp is None or resp.isError() or not getattr(resp, "registers", None):
                continue
            values[addr] = resp.registers[0]
            any_ok = True
        if not any_ok:
            _LOGGER.error(
                "Modbus read failed for every register in %s block %s", fc, start
            )
        return any_ok

    def _required_settings(self) -> list[tuple[str, str, int]]:
        """(entity key, decoded value, raw value) the unit must hold for us."""
        required = [(key, "on", 1) for key in BMS_ENABLE_KEYS]
        if not self._has_display:
            required += [
                (key, decoded, raw) for key, (decoded, raw) in HEADLESS_SETTINGS.items()
            ]
        return required

    def _sync_required_settings_locked(self) -> None:
        """Keep PH02/PH27/PH28 (and, headless, PH01/HA00) at the values we need.

        Driven by the polled read-back rather than a one-shot flag: if the unit
        power-cycles and loses a setting, every subsequent write would silently
        no-op until Home Assistant restarted. Re-asserting each cycle self-heals
        that, and only writes when the read-back differs.

        Note this deliberately overrides the matching switches/select - these are
        required for the integration to control the unit at all, so changing one
        by hand is undone on the next poll. Without a display, PH01 must be 0
        (else the unit stays OFF-by-display) and HA00 must be 0 (else it waits
        for room T/H from a display that is not there).
        """
        for key, expected, raw in self._required_settings():
            if self.data.get(key) == expected:
                continue
            reg, _dt = get_entity_reg(get_entity_props(key))
            try:
                resp = self._client.write_register(
                    address=reg, value=raw, device_id=self._hostid
                )
            except Exception as exc:  # noqa: BLE001 - retried next cycle
                _LOGGER.warning("Could not set required setting %s: %r", key, exc)
                continue
            if resp is not None and resp.isError():
                _LOGGER.warning(
                    "Device rejected required setting %s (register %s): %s",
                    key,
                    reg,
                    resp,
                )
            else:
                _LOGGER.info(
                    "Set required setting %s (register %s) to %s", key, reg, raw
                )

    # ---- decoding ---------------------------------------------------------
    def _decode_all(
        self, raw_input: Dict[int, int], raw_holding: Dict[int, int]
    ) -> None:
        for key, props in ENTITIES_DICT.items():
            reg, dt = get_entity_reg(props)
            source = (
                raw_input
                if get_entity_type(props) == C_REG_TYPE_INPUT_REGISTERS
                else raw_holding
            )
            if reg not in source:
                continue
            raw = ModbusTcpClient.convert_from_registers(
                registers=[source[reg]], data_type=dt
            )
            if is_entity_switch(props):
                bitmask = get_entity_bitmask(props)
                if bitmask is not None:
                    # Bit-field register: extract the specific bit.
                    bit_val = bool((raw >> bitmask) & 1)
                    if props.get("BITMASK_INVERT", False):
                        bit_val = not bit_val
                    self.data[key] = "on" if bit_val else "off"
                else:
                    off_v = (get_entity_switch(props) or {}).get("off", 0)
                    self.data[key] = "off" if raw == off_v else "on"
            elif is_entity_select(props):
                # An unmapped raw value decodes to None. Emitting "unknown_<raw>"
                # would not be in the entity's `options` and HA raises on write.
                decoded = (get_entity_select(props) or {}).get(raw)
                if decoded is None:
                    _LOGGER.warning(
                        "Register %s (%s) returned unmapped value %s", reg, key, raw
                    )
                self.data[key] = decoded
            elif dt == C_DT_INT16 and is_probe_sentinel(source[reg]):
                # An unwired/failed analog input: not a reading. Keep the key so
                # the entity is available but has no value (unknown), rather
                # than reporting about -3276 degC.
                self.data[key] = None
            else:
                self.data[key] = float(raw) * get_entity_factor(props)

    def _compute_setup_issues(self) -> list[str]:
        """Slugs of things the user should look at before operating the unit.

        Derived from the polled read-back only, so it reflects the unit's real
        state rather than what we last tried to write.
        """
        d = self.data
        issues: list[str] = []
        pending = [k for k, want, _raw in self._required_settings() if d.get(k) != want]
        if any(k in BMS_ENABLE_KEYS for k in pending):
            issues.append("modbus_enables_pending")
        if any(k not in BMS_ENABLE_KEYS for k in pending):
            issues.append("headless_settings_pending")

        status = d.get(C_UNIT_STATUS)
        if status == "off_by_di":
            issues.append("unit_off_by_digital_input")
        elif status == "off_by_scheduler":
            issues.append("unit_off_by_scheduler")
        elif status == "off_by_rtc":
            issues.append("unit_off_by_clock")
        elif status == "off_by_display" and self._has_display:
            issues.append("unit_off_by_display")

        # An allocated analog input that reads the unwired sentinel is a probe
        # the unit waits for but cannot get.
        if d.get(C_AI2_ALLOCATION) and d.get(C_ROOM_TEMPERATURE) is None:
            issues.append("room_temperature_probe_missing")
        if d.get(C_AI3_ALLOCATION) and d.get(C_ROOM_HUMIDITY) is None:
            issues.append("room_humidity_probe_missing")

        if d.get(C_TIME_PROGRAMS) in ("on", 1, 1.0):
            issues.append("time_programs_enabled")
        if d.get(C_ENABLE_FREE_COOLING) == "on" and (
            d.get(C_OUTDOOR_TEMPERATURE) is None
        ):
            issues.append("free_cooling_without_outdoor_probe")
        if d.get(C_TEMPERATURE_UNIT) == "fahrenheit":
            issues.append("temperature_unit_fahrenheit")
        # Relay K5 drives the external valve and, with it, the pump output. If
        # it is not configured the unit cannot start the circulation pump.
        if d.get(C_WATER_VALVE_PUMP) == "disabled":
            issues.append("water_pump_output_not_configured")
        # With a brine temperature guard, winter dehumidifying is a deliberate
        # choice (the guard refuses it on cold brine); without one it is not.
        if (
            self.is_brine
            and not self.brine_entity
            and d.get(C_WINTER_DEHUM) not in (None, "disabled")
        ):
            issues.append("winter_dehumidify_on_brine")
        return issues

    def _compute_water_issues(self) -> list[str]:
        """Water-circuit diagnostics. Read-only: the unit runs valve and pump.

        Temperature limits are only judged while the unit circulates water,
        since a standing circuit just reads the plant-room temperature.
        """
        d = self.data
        issues: list[str] = []
        pump = d.get(C_WATER_VALVE_PUMP)
        if d.get(C_COMPRESSOR_STATUS) == "on" and pump == "off":
            issues.append("pump_off_while_compressor_runs")
        water = d.get(C_WATER_TEMPERATURE)
        if pump == "on" and water is not None:
            max_water = d.get(installer_key("PC07"))
            if max_water is not None and water > max_water:
                issues.append("water_too_warm")
            cold_only = d.get(installer_key("PU08"))
            if cold_only is not None and water < cold_only:
                issues.append("water_below_compressor_limit")
        if d.get(C_ALARM_HIGH_WATER_TEMP) == "on":
            issues.append("high_water_temperature_alarm")
        if d.get(C_ALARM_LOW_WATER_TEMP) == "on":
            issues.append("low_water_temperature_alarm")
        if d.get(C_ALARM_ANTIFREEZE) == "on":
            issues.append("antifreeze_alarm")
        if self.is_brine and self.season == "winter" and d.get(C_UNIT_STATUS) == "on":
            # Anti-stagnation pulses run the pump and send cold air puffs.
            issues.append("brine_unit_on_in_winter")
        if self.brine_guard_ok is False:
            issues.append("brine_guard_blocking")
        return issues

    def _compute_derived(self) -> None:
        """Write computed values: setup check and airflow (m³/h)."""
        self.setup_issues = self._compute_setup_issues()
        self.data[C_SETUP_CHECK] = "attention" if self.setup_issues else "ok"
        self.water_issues = self._compute_water_issues()
        self.data[C_WATER_CHECK] = "attention" if self.water_issues else "ok"
        self.data[C_MAX_TOTAL_AIRFLOW] = self._airflow_max
        self.data[C_SUPPLY_FAN_MAX_AIRFLOW] = self._airflow_max
        out = self.data.get(C_SUPPLY_FAN_OUTPUT)
        if out is None:
            self.data.setdefault(C_SUPPLY_FAN_AIRFLOW, None)
            return
        # "Fan is not moving air" is the device's own judgement, not a
        # percentage threshold of ours. The per-mode minimum speed lives in
        # PF28/PF27/PF07 and is exposed as writable numbers; duplicating it as
        # a config option here would shadow the registers and silently report
        # 0 m3/h while the fan was actually running below that figure.
        if self.data.get(C_SUPPLY_FAN_STATUS) in ("off", "disabled", "alarm"):
            self.data[C_SUPPLY_FAN_AIRFLOW] = 0.0
            return
        self.data[C_SUPPLY_FAN_AIRFLOW] = min(
            self._airflow_max, out / 100.0 * self._airflow_max
        )

    # ---- writing ----------------------------------------------------------
    async def write_entity_value(self, entity_key: str, value: Any) -> None:
        """Encode and write a single entity's value, then refresh."""
        props = get_entity_props(entity_key)
        if is_entity_readonly(props):
            raise ServiceValidationError(f"Register {entity_key} is read-only")
        reg, dt = get_entity_reg(props)

        if is_entity_switch(props):
            raw = self._encode_switch(value)
        elif is_entity_select(props):
            raw = self._encode_select(props, value)
        else:
            faktor = get_entity_factor(props)
            raw = round(float(value) / faktor) if faktor else round(float(value))

        self._check_request_allowed(entity_key, raw)
        if entity_key in OPERATIONAL_KEYS and raw != 0 and not self.operation_allowed:
            raise ServiceValidationError(
                "Operational requests are not allowed yet. Review the setup "
                "entities, then turn on 'Allow operational requests'."
            )

        words = ModbusTcpClient.convert_to_registers(value=int(raw), data_type=dt)
        ok = await self._hass.async_add_executor_job(self._write_registers, reg, words)
        if not ok:
            raise HomeAssistantError(
                f"Modbus write to {entity_key} (register {reg}) failed. If this "
                "persists, check that the PH02/PH27/PH28 enables are set."
            )
        # Debounced: the unit needs a moment to mirror a command into its status
        # registers, and one HVAC mode change issues several writes.
        self.async_schedule_refresh()

    async def setter_function_callback(self, entity, value) -> None:
        await self.write_entity_value(entity.entity_description.key, value)

    @staticmethod
    def _encode_switch(value: Any) -> int:
        if isinstance(value, str):
            return 0 if value.strip().lower() in {"off", "0", "false", "no"} else 1
        return 1 if bool(value) else 0

    @staticmethod
    def _encode_select(props: Dict[str, Any], value: Any) -> int:
        values = get_entity_select(props) or {}
        inv = {str(v): k for k, v in values.items()}
        if isinstance(value, str) and value in inv:
            return int(inv[value])
        return int(value)

    def _write_registers(self, base_reg: int, words) -> bool:
        """Write one or more registers. Returns True only if every write took."""
        with self._lock:
            if not self._client.connect():
                _LOGGER.warning("Modbus connect failed during write")
                return False
            try:
                for offset, word in enumerate(words):
                    try:
                        resp = self._client.write_register(
                            address=base_reg + offset,
                            value=int(word) & 0xFFFF,
                            device_id=self._hostid,
                        )
                    except Exception as exc:  # noqa: BLE001 - reported to caller
                        _LOGGER.error(
                            "Write to register %s raised: %r", base_reg + offset, exc
                        )
                        return False
                    if resp is not None and resp.isError():
                        _LOGGER.error(
                            "Write to register %s failed: %s", base_reg + offset, resp
                        )
                        return False
            finally:
                self._client.close()
        return True
