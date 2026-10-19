"""Innova HRDS+ / hej.luft dehumidifier — Modbus TCP integration."""

from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from pymodbus.client import ModbusTcpClient

from .const import (
    BMS_ENABLE_KEYS,
    C_AI2_ALLOCATION,
    C_AI3_ALLOCATION,
    C_DT_INT16,
    C_ENABLE_FREE_COOLING,
    C_MAX_BLOCK,
    C_MAX_GAP,
    C_MAX_TOTAL_AIRFLOW,
    C_OUTDOOR_TEMPERATURE,
    C_REG_TYPE_HOLDING_REGISTERS,
    C_REG_TYPE_INPUT_REGISTERS,
    C_ROOM_HUMIDITY,
    C_ROOM_TEMPERATURE,
    C_SETUP_CHECK,
    C_SUPPLY_FAN_AIRFLOW,
    C_SUPPLY_FAN_MAX_AIRFLOW,
    C_SUPPLY_FAN_OUTPUT,
    C_SUPPLY_FAN_STATUS,
    C_TEMPERATURE_UNIT,
    C_TIME_PROGRAMS,
    C_UNIT_STATUS,
    CONF_AIRFLOW_MAX,
    CONF_HAS_DISPLAY,
    CONF_HOSTID,
    CONF_MODEL,
    DEFAULT_HAS_DISPLAY,
    DEFAULT_HOSTID,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    ENTITIES_DICT,
    HEADLESS_SETTINGS,
    MODEL_SPECS,
    OPERATIONAL_KEYS,
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
    )

    # Prime the cache before creating entities so they do not sit at `unknown`
    # for a whole scan interval, and so an unreachable device is reported as
    # such instead of setting up permanently-stale entities.
    if not await hass.async_add_executor_job(hub._do_read_cycle):
        raise ConfigEntryNotReady(f"Cannot reach HRDS+ Modbus gateway at {host}:{port}")

    # runtime_data is keyed by the config entry, so two entries sharing a name
    # can no longer clobber each other's hub the way hass.data[DOMAIN][name] did.
    entry.runtime_data = hub

    # Register both devices up front: the setup device points at the main one
    # via `via_device`, which must already exist when the child is created.
    main_info, setup_info = build_device_infos(entry, hub)
    registry = dr.async_get(hass)
    registry.async_get_or_create(config_entry_id=entry.entry_id, **main_info)
    registry.async_get_or_create(config_entry_id=entry.entry_id, **setup_info)

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
    ) -> None:
        self._hass = hass
        self._name = name
        self._has_display = has_display
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
        return issues

    def _compute_derived(self) -> None:
        """Write computed values: setup check and airflow (m³/h)."""
        self.setup_issues = self._compute_setup_issues()
        self.data[C_SETUP_CHECK] = "attention" if self.setup_issues else "ok"
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
