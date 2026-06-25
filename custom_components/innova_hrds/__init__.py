"""Innova HRDS+ / hej.luft dehumidifier — Modbus TCP integration."""

from __future__ import annotations

import asyncio
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
from homeassistant.helpers.event import async_track_time_interval
from pymodbus.client import ModbusTcpClient

from .const import (
    BMS_ENABLE_KEYS,
    C_MAX_BLOCK,
    C_MAX_GAP,
    C_REG_TYPE_HOLDING_REGISTERS,
    C_REG_TYPE_INPUT_REGISTERS,
    CONF_HOSTID,
    DEFAULT_HOSTID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENTITIES_DICT,
    get_entity_factor,
    get_entity_props,
    get_entity_reg,
    get_entity_select,
    get_entity_switch,
    get_entity_type,
    is_entity_readonly,
    is_entity_select,
    is_entity_switch,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.CLIMATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    hass.data.setdefault(DOMAIN, {})

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

    hub = HrdsModbusHub(hass, name, host, port, scan_interval, hostid)
    hass.data[DOMAIN][name] = {"hub": hub}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.data[CONF_NAME], None)
    return unload_ok


def _build_blocks(addresses: List[int]) -> List[Tuple[int, int]]:
    """Group sorted addresses into (start, count) blocks for block reads.

    Adjacent addresses (gap <= C_MAX_GAP) are merged; each block is capped at
    C_MAX_BLOCK registers so we never exceed the Modbus per-request limit.
    """
    if not addresses:
        return []
    addresses = sorted(set(addresses))
    blocks: List[Tuple[int, int]] = []
    start = prev = addresses[0]
    for addr in addresses[1:]:
        if addr - prev <= C_MAX_GAP and addr - start + 1 <= C_MAX_BLOCK:
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
    ) -> None:
        self._hass = hass
        self._name = name
        self._client = ModbusTcpClient(host=host, port=port, timeout=3, retries=3)
        self._lock = threading.Lock()
        self._hostid = hostid
        self._scan_interval = timedelta(seconds=scan_interval)
        self._unsub: Optional[Any] = None
        self._sensors: list = []
        self._bms_enabled = False
        self.data: Dict[str, Any] = {}

        # Pre-compute the block reads per register type.
        self._input_blocks = _build_blocks(
            [
                get_entity_reg(p)[0]
                for p in ENTITIES_DICT.values()
                if get_entity_type(p) == C_REG_TYPE_INPUT_REGISTERS
            ]
        )
        self._holding_blocks = _build_blocks(
            [
                get_entity_reg(p)[0]
                for p in ENTITIES_DICT.values()
                if get_entity_type(p) == C_REG_TYPE_HOLDING_REGISTERS
            ]
        )

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
        self._sensors.remove(update_callback)
        if not self._sensors and self._unsub:
            self._unsub()
            self._unsub = None
            self.close()

    def close(self) -> None:
        with self._lock:
            self._client.close()

    # ---- polling ----------------------------------------------------------
    async def async_refresh_modbus_data(self, _now=None) -> None:
        if not self._sensors:
            return
        ok = await self._hass.async_add_executor_job(self._do_read_cycle)
        if ok:
            for cb in self._sensors:
                cb()

    def _do_read_cycle(self) -> bool:
        with self._lock:
            if not self._client.connect():
                _LOGGER.warning("Modbus connect to HRDS+ failed")
                return False
            try:
                if not self._bms_enabled:
                    self._enable_bms_control_locked()
                raw_input = self._read_blocks(self._input_blocks, fc="input")
                raw_holding = self._read_blocks(self._holding_blocks, fc="holding")
            finally:
                self._client.close()

        if raw_input is None or raw_holding is None:
            return False
        self._decode_all(raw_input, raw_holding)
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
                _LOGGER.error("Modbus read failed (%s @ %s+%s)", fc, start, count)
                return None
            for offset, reg in enumerate(resp.registers):
                values[start + offset] = reg
        return values

    def _enable_bms_control_locked(self) -> None:
        """Write the PH02/PH27/PH28 enable registers so writes are honoured."""
        try:
            for key in BMS_ENABLE_KEYS:
                reg, _dt = get_entity_reg(get_entity_props(key))
                self._client.write_register(
                    address=reg, value=1, device_id=self._hostid
                )
            self._bms_enabled = True
        except Exception as exc:  # noqa: BLE001 - best effort, retried next cycle
            _LOGGER.warning("Could not enable BMS control: %r", exc)

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
            raw = self._client.convert_from_registers(
                registers=[source[reg]], data_type=dt
            )
            if is_entity_switch(props):
                off_v = (get_entity_switch(props) or {}).get("off", 0)
                self.data[key] = "off" if raw == off_v else "on"
            elif is_entity_select(props):
                self.data[key] = (get_entity_select(props) or {}).get(
                    raw, f"unknown_{raw}"
                )
            else:
                self.data[key] = float(raw) * get_entity_factor(props)

    # ---- writing ----------------------------------------------------------
    async def write_entity_value(self, entity_key: str, value: Any) -> None:
        """Encode and write a single entity's value, then refresh."""
        props = get_entity_props(entity_key)
        if is_entity_readonly(props):
            raise PermissionError(f"Register {entity_key} is read-only")
        reg, dt = get_entity_reg(props)

        if is_entity_switch(props):
            raw = self._encode_switch(value)
        elif is_entity_select(props):
            raw = self._encode_select(props, value)
        else:
            faktor = get_entity_factor(props)
            raw = round(float(value) / faktor) if faktor else round(float(value))

        words = self._client.convert_to_registers(value=int(raw), data_type=dt)
        await self._hass.async_add_executor_job(self._write_registers, reg, words)
        await self.async_refresh_modbus_data()

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
        inv = {str(v): k for k, v in values.items() if k != "default"}
        if isinstance(value, str) and value in inv:
            return int(inv[value])
        return int(value)

    def _write_registers(self, base_reg: int, words) -> None:
        with self._lock:
            if not self._client.connect():
                _LOGGER.warning("Modbus connect failed during write")
                return
            try:
                for offset, word in enumerate(words):
                    resp = self._client.write_register(
                        address=base_reg + offset,
                        value=int(word) & 0xFFFF,
                        device_id=self._hostid,
                    )
                    if resp is not None and resp.isError():
                        _LOGGER.error(
                            "Write to register %s failed: %s", base_reg + offset, resp
                        )
            finally:
                self._client.close()
