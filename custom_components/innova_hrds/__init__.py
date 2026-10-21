"""Innova HRDS+ / hej.luft dehumidifier — Modbus TCP integration."""

from __future__ import annotations

import logging
import threading
import time
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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter
from pymodbus.client import ModbusTcpClient

from .const import (
    AUTO_HEATING_NEGLIGIBLE_BELOW,
    BMS_ENABLE_KEYS,
    BRINE_GUARD_MAX_AGE_HOURS,
    C_AI2_ALLOCATION,
    C_AI3_ALLOCATION,
    C_ALARM_ANTIFREEZE,
    C_ALARM_HIGH_WATER_TEMP,
    C_ALARM_LOW_WATER_TEMP,
    C_AUTO_HEATING,
    C_BRINE_GUARD,
    C_COMPRESSOR_STATUS,
    C_DEHUM_REQUEST,
    C_DEHUMIDIFY,
    C_DT_INT16,
    C_ENABLE_FREE_COOLING,
    C_ENABLE_INT_BMS,
    C_HUMIDITY_PROBE_OK,
    C_INSTALLER_LAST_READ,
    C_INTEGRATION_AVAILABLE,
    C_INTEGRATION_REQUEST,
    C_MAX_BLOCK,
    C_MAX_GAP,
    C_MAX_TOTAL_AIRFLOW,
    C_MODE_STATUS,
    C_OPERATING_MODE,
    C_OUTDOOR_TEMPERATURE,
    C_RECIRCULATION_DAMPER,
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
    C_TEMP_PROBE_OK,
    C_TEMPERATURE_UNIT,
    C_TIME_PROGRAMS,
    C_UNIT_ON_OFF,
    C_UNIT_STATUS,
    C_WATER_CHECK,
    C_WATER_TEMPERATURE,
    C_WATER_VALVE_PUMP,
    C_WINTER_DEHUM,
    C_WINTER_SETPOINT,
    CONF_AIRFLOW_MAX,
    CONF_ALLOW_WINTER_HEATING,
    CONF_BRINE_MIN_TEMPERATURE,
    CONF_BRINE_TEMPERATURE_ENTITY,
    CONF_HAS_DISPLAY,
    CONF_HOSTID,
    CONF_INSTALLER_DEVICE,
    CONF_MODEL,
    CONF_WATER_CIRCUIT,
    DEFAULT_ALLOW_WINTER_HEATING,
    DEFAULT_BRINE_MIN_TEMPERATURE,
    DEFAULT_HAS_DISPLAY,
    DEFAULT_HOSTID,
    DEFAULT_INSTALLER_DEVICE,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WATER_CIRCUIT,
    DOMAIN,
    ENTITIES_DICT,
    FAN_KEYS,
    HEADLESS_SETTINGS,
    HUMIDITY_TARGET_KEYS,
    INSTALLER_DEVICE_EXTRA_KEYS,
    INSTALLER_DEVICE_SUFFIX,
    INSTALLER_KEYS,
    INSTALLER_LOGIC_KEYS,
    MODEL_SPECS,
    OPERATIONAL_KEYS,
    PENDING_KEYS,
    PENDING_RECHECK_SECONDS,
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

# A single-register read slower than this does not prove the link is fine
# (the client timeout is 3 s; a healthy gateway answers in well under 1 s).
C_PROBE_MAX_SECONDS = 1.5

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.BUTTON,
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
    installer_enabled = bool(
        entry.options.get(
            CONF_INSTALLER_DEVICE,
            entry.data.get(CONF_INSTALLER_DEVICE, DEFAULT_INSTALLER_DEVICE),
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
        allow_winter_heating,
        water_circuit,
        brine_entity,
        brine_min,
        installer_enabled,
    )

    # Prime the cache before creating entities so they do not sit at `unknown`
    # for a whole scan interval, and so an unreachable device is reported as
    # such instead of setting up permanently-stale entities.
    if not await hass.async_add_executor_job(hub._do_read_cycle):
        raise ConfigEntryNotReady(f"Cannot reach HRDS+ Modbus gateway at {host}:{port}")
    # Installer parameters once per load (the water-check limits only, unless
    # the installer device is on). A failure here only leaves them unknown.
    await hass.async_add_executor_job(hub._do_read_installer)

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
    # devices point at the main one via `via_device_id`, which needs its id.
    registry = dr.async_get(hass)
    main_info, _, _ = build_device_infos(entry, hub)
    main_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id, **main_info
    )
    _, setup_info, installer_info = build_device_infos(entry, hub, main_device.id)
    registry.async_get_or_create(config_entry_id=entry.entry_id, **setup_info)
    if installer_enabled:
        registry.async_get_or_create(config_entry_id=entry.entry_id, **installer_info)
    elif installer_device := registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id + INSTALLER_DEVICE_SUFFIX), entry.entry_id
    ):
        # Turned off in the options: the device goes, and its entities with it.
        registry.async_remove_device(installer_device.id)

    _migrate_setup_entities(hass, entry)
    _migrate_renamed_keys(hass, entry)

    # HA02/HA03 were numbers up to 0.9.1 and are selects now, with the same
    # unique id: drop the orphaned number entities.
    ent_registry = er.async_get(hass)
    for key in (C_AI2_ALLOCATION, C_AI3_ALLOCATION):
        if old_id := ent_registry.async_get_entity_id(
            Platform.NUMBER, DOMAIN, f"{entry.entry_id}-{key}"
        ):
            ent_registry.async_remove(old_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _migrate_setup_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Carry the renamed PH27 switch over and drop the PG02 switch.

    PH27 was `enable_cooling_bms` but is the INT request's enable, so the key
    follows the register. The entity id stays as the user has it. PG02 is a
    hardware capability, shown by `integration_available`; its switch
    duplicated that register and is gone.
    """
    registry = er.async_get(hass)
    prefix = entry.entry_id + "-"
    old_uid = prefix + "enable_cooling_bms"
    if entity_id := registry.async_get_entity_id("switch", DOMAIN, old_uid):
        registry.async_update_entity(entity_id, new_unique_id=prefix + C_ENABLE_INT_BMS)
    if entity_id := registry.async_get_entity_id(
        "switch", DOMAIN, prefix + "enable_integration"
    ):
        registry.async_remove(entity_id)


# Keys renamed after a release: (platform, old key, new key). Register 1139 is
# the integration (INT) request, which cools in summer and heats in winter, and
# PG02 says whether the unit has INT; both used to be keyed "active cooling".
RENAMED_KEYS = (
    (Platform.SWITCH, "active_cooling", C_INTEGRATION_REQUEST),
    (Platform.BINARY_SENSOR, "active_cooling_available", C_INTEGRATION_AVAILABLE),
)


def _migrate_renamed_keys(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move entities of a renamed key to the new unique id, history included.

    An entity id that still carries the old key (e.g.
    `switch.hrds_active_cooling_modbus`) follows the new one, unless that id is
    taken; any other entity id stays as it is.
    """
    registry = er.async_get(hass)
    prefix = entry.entry_id + "-"
    for platform, old, new in RENAMED_KEYS:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, prefix + old)
        if entity_id is None or registry.async_get_entity_id(
            platform, DOMAIN, prefix + new
        ):
            continue
        changes: dict[str, Any] = {"new_unique_id": prefix + new}
        object_id = entity_id.split(".", 1)[1]
        new_entity_id = f"{platform}.{object_id.replace(old, new)}"
        if old in object_id and not registry.async_is_registered(new_entity_id):
            changes["new_entity_id"] = new_entity_id
        registry.async_update_entity(entity_id, **changes)
        _LOGGER.info(
            "Renamed %s to %s (key %s is now %s)",
            entity_id,
            changes.get("new_entity_id", entity_id),
            old,
            new,
        )


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
    addresses: List[int],
    foreign: frozenset[int] = frozenset(),
    max_block: int = C_MAX_BLOCK,
) -> List[Tuple[int, int]]:
    """Group sorted addresses into (start, count) blocks for block reads.

    Adjacent addresses (gap <= C_MAX_GAP) are merged; each block is capped at
    ``max_block`` registers (C_MAX_BLOCK unless the hub learned a lower limit).

    ``foreign`` holds the addresses a block is never allowed to span: those of
    the *other* function code (reading e.g. holding register 1105 with FC 04
    can return ILLEGAL DATA ADDRESS, which would fail the whole block) and
    those of keys not being read now (the poll leaves the installer menu out).
    """
    addresses = sorted({a for a in addresses if a is not None})
    if not addresses:
        return []
    blocks: List[Tuple[int, int]] = []
    start = prev = addresses[0]
    for addr in addresses[1:]:
        fits = addr - prev <= C_MAX_GAP and addr - start + 1 <= max_block
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
        installer_enabled: bool = DEFAULT_INSTALLER_DEVICE,
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
        # A request written but not yet read back: key -> (commanded value,
        # when it was written, what the unit last read). See PENDING_KEYS.
        self._pending: Dict[str, Tuple[str, float, Any]] = {}
        self._pending_lock = threading.Lock()
        self._verify_handles: List[Any] = []
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
        # R variant (recirculation fan); decided in update_hidden_keys.
        self.has_fan = True
        self.show_temperature_target = True
        self.show_humidity_target = True

        # The installer menu is opt-in, and never part of the regular poll:
        # it is read at setup and on its refresh button only.
        self.installer_enabled = installer_enabled
        self._poll_keys = frozenset(ENTITIES_DICT) - INSTALLER_KEYS
        # Every address of each function code; a block of one must not span an
        # address of the other.
        self._all_addrs = {
            fc: frozenset(
                get_entity_reg(p)[0]
                for p in ENTITIES_DICT.values()
                if get_entity_type(p) == rt
            )
            for fc, rt in (
                ("input", C_REG_TYPE_INPUT_REGISTERS),
                ("holding", C_REG_TYPE_HOLDING_REGISTERS),
            )
        }
        # Lowered (for the hub's lifetime) when the link does not answer a
        # block of this size but does answer a single register.
        self._max_block = C_MAX_BLOCK

    @property
    def installer_keys_to_read(self) -> frozenset[str]:
        """Installer registers read at setup and on refresh."""
        return INSTALLER_KEYS if self.installer_enabled else INSTALLER_LOGIC_KEYS

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
            # A write just before unload leaves its debounced refresh pending.
            if self._pending_refresh is not None:
                self._pending_refresh()
                self._pending_refresh = None
            self._cancel_verify()
            # Hand the socket close to an executor: it acquires the same lock a
            # poll in flight may hold, which would stall the event loop.
            self._hass.async_add_executor_job(self.close)

    @property
    def is_brine(self) -> bool:
        return self.water_circuit == WATER_CIRCUIT_BRINE

    @property
    def has_display(self) -> bool:
        return self._has_display

    @property
    def season(self) -> Optional[str]:
        """The season the unit reports (1583): summer, winter, auto or None."""
        return self.data.get(C_OPERATING_MODE)

    @property
    def active_season(self) -> Optional[str]:
        """The season the unit runs in now: summer, winter or None.

        1583 reads ``auto`` while the unit switches season itself (PC05); the
        mode status (1110: summer_manual, winter_auto, ...) says which one is
        in force.
        """
        mode = self.data.get(C_MODE_STATUS)
        if isinstance(mode, str):
            for season in ("summer", "winter"):
                if mode.startswith(season):
                    return season
        season = self.season
        return season if season in ("summer", "winter") else None

    @property
    def int_effect(self) -> Optional[str]:
        """What the integration (INT) request makes the unit do: cool, heat or None.

        INT cools in summer and heats in winter on a unit with the integration
        function (PG02). The unit does not know ``allow_winter_heating``: that
        option only governs the requests Home Assistant sends, so a winter INT
        set elsewhere (display, a season change under a latched Cool) heats all
        the same. Whether it really warms the air is ``is_heating``. On brine a
        winter INT only circulates cold brine (handbook 3.8.7: no heating). None
        while INT is off or cannot act; the unit then at most dehumidifies.
        """
        d = self.data
        if (
            d.get(C_INTEGRATION_REQUEST) != "on"
            or d.get(C_INTEGRATION_AVAILABLE) == "off"
        ):
            return None
        season = self.active_season
        if season == "summer":
            return "cool"
        if season == "winter" and not self.is_brine:
            return "heat"
        return None

    @property
    def auto_heating_band(self) -> Tuple[Optional[float], Optional[float]]:
        """(starts below, stops above) for the unit's own winter heating, in °C.

        Its room logic raises INT when the room falls below SEtH - PF12 and
        drops it above SEtH + PF12 (handbook 6.1.2). None where not read.
        """
        setpoint = self.data.get(C_WINTER_SETPOINT)
        if setpoint is None:
            return None, None
        band = self.data.get(installer_key("PF12")) or 0.0
        return setpoint - band, setpoint + band

    @property
    def can_heat_on_its_own(self) -> bool:
        """Whether the unit's room logic can raise a winter INT by itself.

        It needs a room temperature it regulates on (display or allocated
        probe, healthy) and the integration function (PG02). The integration
        option ``allow_winter_heating`` does not enter: the unit knows nothing
        of it. Judged for winter, whatever the season now.
        """
        return self._auto_sources("winter")[1]

    @property
    def auto_heating_active(self) -> bool:
        """Whether the unit, on and in winter, is set to heat by itself now."""
        return (
            self.active_season == "winter"
            and self.data.get(C_UNIT_STATUS) == "on"
            and self.can_heat_on_its_own
        )

    def _own_heating_request(self) -> bool:
        """Whether the unit's own winter INT may be standing now.

        The INT request is not readable (only DEU is, 1121): judged from the
        room temperature against the band, counting the hysteresis as on.
        """
        if not self.auto_heating_active or self.is_brine:
            return False
        room = self.data.get(C_ROOM_TEMPERATURE)
        _starts, stops = self.auto_heating_band
        return room is not None and stops is not None and room < stops

    @property
    def is_heating(self) -> bool:
        """Whether the unit heats now, judged from what it does.

        The unit has no heat source of its own: winter INT opens the water
        valve, runs the pump and fan, and keeps the compressor off (handbook
        2.6.2, 6.4). Only warm water warms the air, so this needs an INT (a
        latched one, or the unit's own from the room temperature), the valve /
        pump output on, no AL04, and water at or above PC08 (the unit's own
        minimum for winter integration; only judged while water circulates).
        """
        d = self.data
        if self.int_effect != "heat" and not self._own_heating_request():
            return False
        if d.get(C_WATER_VALVE_PUMP) != "on" or d.get(C_COMPRESSOR_STATUS) == "on":
            return False
        if d.get(C_ALARM_LOW_WATER_TEMP) == "on":
            return False
        water = d.get(C_WATER_TEMPERATURE)
        min_water = d.get(installer_key("PC08"))
        return water is None or min_water is None or water >= min_water

    @property
    def is_cooling(self) -> bool:
        """Whether the unit cools now: a summer INT it acts on, compressor on.

        AL03 (water above PC07) disables active cooling. The condenser valve
        (K4, 1124) is not used: a real unit reads it ON in standby, against the
        handbook, so its meaning is unverified.
        """
        d = self.data
        return (
            self.int_effect == "cool"
            and d.get(C_COMPRESSOR_STATUS) == "on"
            and d.get(C_ALARM_HIGH_WATER_TEMP) != "on"
        )

    def _auto_sources(self, season: Optional[str] = None) -> Tuple[bool, bool]:
        """(humidity, temperature): what the unit can request on its own.

        ``season`` judges another season than the one in force (e.g. before a
        season change).

        The unit ORs its request sources (handbook 6.1): the room probes
        (humidity above PU01 + PU07 -> DEU; temperature past SEtC/SEtH -> INT),
        the DEU/INT digital inputs and Modbus. Without a healthy room reading
        there is no automatic request, and a unit that is merely on does
        nothing.
        """
        d = self.data
        summer = (season or self.active_season) == "summer"
        humidity = (
            self.show_humidity_target
            and d.get(C_ROOM_HUMIDITY) is not None
            and d.get(C_HUMIDITY_PROBE_OK) != "off"
            # PU02: no dehumidifying in winter unless enabled (factory: off).
            and (summer or d.get(C_WINTER_DEHUM) != "disabled")
        )
        temperature = (
            self.show_temperature_target
            and d.get(C_ROOM_TEMPERATURE) is not None
            and d.get(C_TEMP_PROBE_OK) != "off"
            # In winter the unit heats by itself (SEtH), whatever the
            # integration's allow_winter_heating says.
            and d.get(C_INTEGRATION_AVAILABLE) == "on"
        )
        return bool(humidity), bool(temperature)

    @property
    def auto_capable(self) -> bool:
        """Whether the unit can raise a request on its own."""
        return any(self._auto_sources())

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
        # A non-R unit has no fan of its own: its damper output is disabled.
        self.has_fan = d.get(C_RECIRCULATION_DAMPER) != "disabled"
        if not self.has_fan:
            hidden |= FAN_KEYS
        if not self.show_temperature_target or (
            d.get(C_INTEGRATION_AVAILABLE) == "off"
        ):
            # No room temperature to regulate on, or no INT: it never heats.
            hidden.add(C_AUTO_HEATING)
        if not self.installer_enabled:
            # The logic limits (INSTALLER_LOGIC_KEYS) are still read, but not
            # shown.
            hidden |= INSTALLER_KEYS | INSTALLER_DEVICE_EXTRA_KEYS
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
        winter = self.active_season != "summer"
        d = self.data
        requests_on = (
            d.get(C_DEHUMIDIFY) == "on" or d.get(C_INTEGRATION_REQUEST) == "on"
        )
        # Switching the unit on starts it when a request is latched or when its
        # own room-probe logic can raise one.
        starts = bool(raw) and (
            entity_key in (C_DEHUMIDIFY, C_INTEGRATION_REQUEST)
            or (entity_key == C_UNIT_ON_OFF and (requests_on or self.auto_capable))
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
        if (
            entity_key == C_INTEGRATION_REQUEST
            and raw
            and d.get(C_INTEGRATION_AVAILABLE) == "off"
        ):
            raise ServiceValidationError(
                "The unit has no integration function (PG02 = 0); it ignores an "
                "integration request."
            )
        if entity_key == C_INTEGRATION_REQUEST and raw and winter:
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
        # The unit would dehumidify in winter on brine without a passing
        # guard, by its own room-probe logic or on a request from another
        # source (a digital input: 1121 on while neither of our requests is):
        # refuse switching it on in winter, and switching a running unit to
        # winter.
        foreign_dehum = (
            d.get(C_DEHUM_REQUEST) == "on"
            and d.get(C_DEHUMIDIFY) != "on"
            and d.get(C_INTEGRATION_REQUEST) != "on"
        )
        unguarded_winter_dehum = (
            self.is_brine
            and not brine_winter_ok
            and (self._auto_sources("winter")[0] or foreign_dehum)
        )
        if entity_key == C_UNIT_ON_OFF and raw and winter and unguarded_winter_dehum:
            raise ServiceValidationError(
                "The unit would dehumidify in winter on its own (room probe or "
                "a digital-input request); on a brine circuit that needs a "
                "brine temperature guard (the water register can freeze). "
                "Configure one in the integration options, or set winter "
                "dehumidification (PU02) to disabled."
            )
        if entity_key == C_SEASON and raw == 3:  # 3 = winter
            unit_on = d.get(C_UNIT_ON_OFF) == "on" or d.get(C_UNIT_STATUS) == "on"
            if unit_on and unguarded_winter_dehum:
                raise ServiceValidationError(
                    "The unit would dehumidify in winter on its own (room probe "
                    "or a digital-input request); on a brine circuit that needs "
                    "a brine temperature guard (the water register can freeze). "
                    "Switch the unit off first, configure a guard, or set winter "
                    "dehumidification (PU02) to disabled."
                )
            if (
                self.data.get(C_INTEGRATION_REQUEST) == "on"
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

    def _cancel_verify(self) -> None:
        for cancel in self._verify_handles:
            cancel()
        self._verify_handles = []
        with self._pending_lock:
            self._pending.clear()

    @callback
    def async_schedule_verify(self) -> None:
        """Re-read the pending request registers, and give up after the last."""
        for cancel in self._verify_handles:
            cancel()
        self._verify_handles = []
        last = len(PENDING_RECHECK_SECONDS) - 1
        for i, delay in enumerate(PENDING_RECHECK_SECONDS):

            async def _run(_now, final: bool = i == last) -> None:
                await self._async_verify_pending(final)

            self._verify_handles.append(async_call_later(self._hass, delay, _run))

    async def _async_verify_pending(self, final: bool) -> None:
        with self._pending_lock:
            keys = frozenset(self._pending)
        if not keys:
            return
        # Only the pending registers: a full cycle is ~30 reads on the gateway.
        await self._hass.async_add_executor_job(self._do_read_keys, keys)
        if final:
            self._expire_pending(keys)
        self._compute_derived()
        for cb in self._sensors:
            cb()

    def _apply_pending(self, keys: frozenset[str]) -> None:
        """Keep the commanded value until the unit's read-back agrees with it.

        Called with the registers just decoded into ``self.data``.
        """
        with self._pending_lock:
            for key in keys & self._pending.keys():
                wanted, since, _ = self._pending[key]
                actual = self.data.get(key)
                if actual == wanted:
                    del self._pending[key]
                    _LOGGER.debug(
                        "HRDS+ confirmed %s=%s after %.1f s",
                        key,
                        wanted,
                        time.monotonic() - since,
                    )
                else:
                    self._pending[key] = (wanted, since, actual)
                    self.data[key] = wanted

    def _expire_pending(self, keys: frozenset[str]) -> None:
        """The last re-read is done: what the unit reports stands."""
        with self._pending_lock:
            for key in keys & self._pending.keys():
                wanted, _since, actual = self._pending.pop(key)
                _LOGGER.warning(
                    "HRDS+ did not confirm %s=%s within %s s; showing the unit's "
                    "value (%s)",
                    key,
                    wanted,
                    PENDING_RECHECK_SECONDS[-1],
                    actual,
                )
                if actual is None:
                    self.data.pop(key, None)
                else:
                    self.data[key] = actual

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
                raw = self._read_keys_locked(self._poll_keys)
            finally:
                self._client.close()

        if raw is None:
            self.last_update_success = False
            return False
        self._decode_all(*raw, self._poll_keys)
        self._compute_derived()
        self.last_update_success = True
        return True

    def _do_read_keys(self, keys: frozenset[str]) -> bool:
        """Read just these entity keys (installer menu, a write read-back)."""
        with self._lock:
            if not self._client.connect():
                _LOGGER.warning("Modbus connect to HRDS+ failed")
                return False
            try:
                raw = self._read_keys_locked(keys)
            finally:
                self._client.close()
        if raw is None:
            return False
        self._decode_all(*raw, keys)
        return True

    def _do_read_installer(self) -> bool:
        if not self._do_read_keys(self.installer_keys_to_read):
            _LOGGER.warning("Reading the installer parameters failed")
            return False
        if self.installer_enabled:
            self.data[C_INSTALLER_LAST_READ] = dt_util.utcnow()
        self._compute_derived()
        return True

    async def async_refresh_installer(self) -> None:
        """Read the installer parameters now (the refresh button)."""
        ok = await self._hass.async_add_executor_job(self._do_read_installer)
        for cb in self._sensors:
            cb()
        if not ok:
            raise HomeAssistantError("Reading the installer parameters failed")

    def _read_keys_locked(
        self, keys: frozenset[str]
    ) -> Optional[Tuple[Dict[int, int], Dict[int, int]]]:
        """(input, holding) {address: raw} for these keys, or None on a link failure."""
        wanted: Dict[str, set[int]] = {"input": set(), "holding": set()}
        for key in keys:
            props = ENTITIES_DICT[key]
            fc = (
                "input"
                if get_entity_type(props) == C_REG_TYPE_INPUT_REGISTERS
                else "holding"
            )
            wanted[fc].add(get_entity_reg(props)[0])
        raw_input = self._read_blocks("input", wanted["input"])
        if raw_input is None:
            return None
        raw_holding = self._read_blocks("holding", wanted["holding"])
        if raw_holding is None:
            return None
        return raw_input, raw_holding

    def _read(self, fc: str, address: int, count: int):
        """One block read: the reply, or None if the link failed.

        A Modbus exception reply is a real answer and is returned as is. No
        answer, or one that does not have ``count`` registers, means the link
        failed; the connection is then dropped, because pymodbus would hand a
        late answer still on the socket to the *next* request and every
        following block would decode another block's registers.
        """
        try:
            if fc == "input":
                resp = self._client.read_input_registers(
                    address=address, count=count, device_id=self._hostid
                )
            else:
                resp = self._client.read_holding_registers(
                    address=address, count=count, device_id=self._hostid
                )
        except Exception as exc:  # noqa: BLE001 - any failure is a link failure
            _LOGGER.debug("Read of %s %s+%s raised: %r", fc, address, count, exc)
            resp = None
        if resp is not None and (
            resp.isError() or len(getattr(resp, "registers", None) or ()) == count
        ):
            return resp
        self._client.close()
        return None

    def _read_blocks(self, fc: str, addresses: set[int]) -> Optional[Dict[int, int]]:
        """Read these addresses of a register type into an {address: raw} map."""
        # A block never spans an address that is not being read now: one of
        # the other function code, or one of another group (the regular poll
        # must not touch the installer menu, nor the installer read the rest).
        foreign = (
            self._all_addrs["holding" if fc == "input" else "input"]
            | self._all_addrs[fc]
        ) - addresses
        values: Dict[int, int] = {}
        blocks = _build_blocks(list(addresses), foreign, self._max_block)
        index = 0
        while index < len(blocks):
            start, count = blocks[index]
            index += 1
            resp = self._read(fc, start, count)
            if resp is None and self._shrink_blocks(fc, start, count):
                # Carry on from this block with the smaller blocks.
                remaining = [a for a in addresses if a >= start]
                blocks = _build_blocks(remaining, foreign, self._max_block)
                index = 0
                continue
            if resp is None:
                _LOGGER.warning(
                    "No valid reply to Modbus block read (%s @ %s+%s)",
                    fc,
                    start,
                    count,
                )
                return None
            if resp.isError():
                _LOGGER.warning(
                    "Modbus block read rejected (%s @ %s+%s); retrying individually",
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

    def _shrink_blocks(self, fc: str, start: int, count: int) -> bool:
        """After a block got no reply: was it the size? If so, plan smaller.

        Some RS-485 gateways (or the unit) silently drop requests above some
        register count. A single register answering at the same address tells
        that apart from a dead link; then the cap is halved for every block and
        kept, so the timeout is paid once, not on every poll.

        The probe must answer promptly: on a slow link pymodbus' own retry
        accepts the late answer to its first attempt, which would make a slow
        gateway look like a size limit and shrink the blocks to nothing.
        """
        if count <= 1 or not self._client.connect():
            return False
        started = time.monotonic()
        if self._read(fc, start, 1) is None:
            return False  # the link is down, not the request too large
        if time.monotonic() - started > C_PROBE_MAX_SECONDS:
            self._client.close()  # a late answer may still be on its way
            return False
        self._max_block = max(1, min(self._max_block, count) // 2)
        _LOGGER.warning(
            "No reply to a %s-register Modbus read (%s @ %s) but a single register "
            "answers; reading at most %s registers per request from now on",
            count,
            fc,
            start,
            self._max_block,
        )
        return True

    def _read_block_individually(
        self, values: Dict[int, int], start: int, count: int, fc: str
    ) -> bool:
        """Re-read a rejected block one register at a time.

        Drops only the addresses the device rejects, so a single bad address
        cannot take out every entity in the integration. Returns False if the
        link fails or the whole range is rejected.
        """
        any_ok = False
        for addr in range(start, start + count):
            resp = self._read(fc, addr, 1)
            if resp is None:
                return False
            if resp.isError():
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
        self,
        raw_input: Dict[int, int],
        raw_holding: Dict[int, int],
        keys: frozenset[str],
    ) -> None:
        for key in keys:
            props = ENTITIES_DICT[key]
            reg, dt = get_entity_reg(props)
            source = (
                raw_input
                if get_entity_type(props) == C_REG_TYPE_INPUT_REGISTERS
                else raw_holding
            )
            if reg not in source:
                # The device stopped answering for this one address (the block
                # fell back to per-register reads). Drop the old reading so the
                # entity goes unavailable instead of showing it forever.
                self.data.pop(key, None)
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
        self._apply_pending(keys)

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
        elif status == "off_by_display":
            if self._has_display:
                issues.append("unit_off_by_display")
            elif "headless_settings_pending" not in issues:
                # PH01 is already 0, yet the unit keeps its stored display OFF
                # until the first Modbus ON (seen on a real unit).
                issues.append("unit_waiting_for_first_on")

        # An allocated analog input that reads the unwired sentinel is a probe
        # the unit waits for but cannot get.
        if (
            d.get(C_AI2_ALLOCATION) in ROOM_TEMP_PROBE_CODES
            and d.get(C_ROOM_TEMPERATURE) is None
        ):
            issues.append("room_temperature_probe_missing")
        if (
            d.get(C_AI3_ALLOCATION) in ROOM_HUMIDITY_PROBE_CODES
            and d.get(C_ROOM_HUMIDITY) is None
        ):
            issues.append("room_humidity_probe_missing")
        # Read but decoded to None: a code outside the documented probe codes.
        if any(k in d and d[k] is None for k in (C_AI2_ALLOCATION, C_AI3_ALLOCATION)):
            issues.append("probe_input_unrecognised")

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
        # The unit's own winter heating (room temperature below SEtH - PF12)
        # does not ask the integration: say so, unless its band is too low to
        # matter. On brine it only pumps cold brine through the register.
        starts, _stops = self.auto_heating_band
        if self.can_heat_on_its_own and (
            starts is None or starts >= AUTO_HEATING_NEGLIGIBLE_BELOW
        ):
            if self.is_brine:
                issues.append("unit_heats_on_its_own_on_brine")
            elif not self.allow_winter_heating:
                issues.append("unit_heats_on_its_own")
        if self.allow_winter_heating and d.get(C_INTEGRATION_AVAILABLE) == "off":
            issues.append("winter_heating_without_integration")
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
        if (
            self.is_brine
            and self.active_season == "winter"
            and d.get(C_UNIT_STATUS) == "on"
        ):
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
        self.data[C_AUTO_HEATING] = "on" if self.auto_heating_active else "off"
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
    def check_write_allowed(self, entity_key: str, raw: int) -> None:
        """Raise ServiceValidationError if writing ``raw`` would be refused.

        The request guards and the operation gate, without writing; lets a
        multi-write change refuse before its first write.
        """
        self._check_request_allowed(entity_key, raw)
        if entity_key in OPERATIONAL_KEYS and raw != 0 and not self.operation_allowed:
            raise ServiceValidationError(
                "Operational requests are not allowed yet. Review the setup "
                "entities, then turn on 'Allow operational requests'."
            )

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

        self.check_write_allowed(entity_key, raw)

        words = ModbusTcpClient.convert_to_registers(value=int(raw), data_type=dt)
        ok = await self._hass.async_add_executor_job(self._write_registers, reg, words)
        if not ok:
            raise HomeAssistantError(
                f"Modbus write to {entity_key} (register {reg}) failed. If this "
                "persists, check that the PH02/PH27/PH28 enables are set."
            )
        if entity_key in INSTALLER_KEYS:
            # Not in the regular poll: read back just this one register.
            await self._hass.async_add_executor_job(
                self._do_read_keys, frozenset({entity_key})
            )
            self._compute_derived()
            for cb in self._sensors:
                cb()
            return
        if entity_key in PENDING_KEYS:
            # Show the command now; the unit may take a while to mirror it.
            wanted = "on" if raw else "off"
            with self._pending_lock:
                self._pending[entity_key] = (
                    wanted,
                    time.monotonic(),
                    self.data.get(entity_key),
                )
            self.data[entity_key] = wanted
            self._compute_derived()
            for cb in self._sensors:
                cb()
            self.async_schedule_verify()
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
