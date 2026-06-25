"""Composite climate entity for the Innova HRDS+ dehumidifier.

This entity is not backed by a single register. It aggregates several status
registers for display (temperature, humidity, HVAC action) and translates the
selected HVAC mode into the unit's on/off + dehumidify + active-cooling request
registers.
"""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import callback

from .const import (
    C_ACTIVE_COOLING,
    C_COMPRESSOR_STATUS,
    C_DEHUM_REQUEST,
    C_DEHUMIDIFY,
    C_FAN_MANUAL,
    C_SUPPLY_FAN_OUTPUT,
    C_SUPPLY_FAN_STATUS,
    C_UNIT_ON_OFF,
    C_UNIT_STATUS,
    CLIMATE_CURRENT_HUMIDITY,
    CLIMATE_CURRENT_TEMP,
    CLIMATE_TARGET_HUMIDITY,
    CLIMATE_TARGET_TEMP,
    CLIMATE_TYPES,
    MyClimateEntityDescription,
)
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)

# Fan mode labels and their manual-speed percentages.
# "off" relies on the unit honouring a 0 % setpoint while a mode is active —
# the unit pushes air via the central MVHR's passive inflow instead.
# Needs hardware verification (plans/todo.md).
_FAN_OFF = "off"
_FAN_LOW = "low"
_FAN_MEDIUM = "medium"
_FAN_HIGH = "high"
_FAN_MODES = [_FAN_OFF, _FAN_LOW, _FAN_MEDIUM, _FAN_HIGH]
_FAN_MODE_PCT: dict[str, float] = {
    _FAN_OFF: 0.0,
    _FAN_LOW: 30.0,
    _FAN_MEDIUM: 55.0,
    _FAN_HIGH: 85.0,
}
# Midpoints between preset values for read-back mapping (nearest neighbour).
_FAN_LOW_THRESHOLD = (_FAN_MODE_PCT[_FAN_LOW] + _FAN_MODE_PCT[_FAN_MEDIUM]) / 2  # 42.5
_FAN_MED_THRESHOLD = (_FAN_MODE_PCT[_FAN_MEDIUM] + _FAN_MODE_PCT[_FAN_HIGH]) / 2  # 70.0


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate entity from a config entry."""
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=CLIMATE_TYPES,
        entity_cls=HrdsClimate,
    )


class HrdsClimate(HubBackedEntity, ClimateEntity):
    """Climate front-end for the HRDS+ dehumidifier."""

    entity_description: MyClimateEntityDescription
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, platform_name, hub, device_info, description):
        super().__init__(platform_name, hub, device_info, description)
        self._attr_temperature_unit = description.temperature_unit
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TARGET_HUMIDITY
            | ClimateEntityFeature.FAN_MODE
        )
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.DRY,
            HVACMode.COOL,
        ]
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._attr_min_temp = 15.0
        self._attr_max_temp = 35.0
        self._attr_target_temperature_step = 0.5
        self._attr_min_humidity = 30
        self._attr_max_humidity = 90
        self._attr_fan_modes = _FAN_MODES
        self._attr_fan_mode = _FAN_OFF

    @callback
    def _on_hub_update(self) -> None:
        data = self._hub.data

        temp = data.get(CLIMATE_CURRENT_TEMP)
        if temp is not None:
            self._attr_current_temperature = float(temp)

        hum = data.get(CLIMATE_CURRENT_HUMIDITY)
        if hum is not None:
            self._attr_current_humidity = int(hum)

        target_hum = data.get(CLIMATE_TARGET_HUMIDITY)
        if target_hum is not None:
            self._attr_target_humidity = int(target_hum)

        target_temp = data.get(CLIMATE_TARGET_TEMP)
        if target_temp is not None:
            self._attr_target_temperature = float(target_temp)

        self._attr_hvac_mode = self._derive_mode(data)
        self._attr_hvac_action = self._derive_action(data)
        self._attr_fan_mode = self._derive_fan_mode(data)
        self.async_write_ha_state()

    def _derive_mode(self, data) -> HVACMode:
        if data.get(C_UNIT_ON_OFF) != "on" and data.get(C_UNIT_STATUS) != "on":
            return HVACMode.OFF
        if data.get(C_ACTIVE_COOLING) == "on":
            return HVACMode.COOL
        return HVACMode.DRY

    def _derive_fan_mode(self, data) -> str:
        status = data.get(C_SUPPLY_FAN_STATUS)
        if status in ("off", "disabled", "wait_off"):
            return _FAN_OFF
        pct = data.get(C_SUPPLY_FAN_OUTPUT)  # float 0–100
        if pct is None:
            return self._attr_fan_mode or _FAN_OFF
        if pct < 5.0:
            return _FAN_OFF
        if pct < _FAN_LOW_THRESHOLD:
            return _FAN_LOW
        if pct < _FAN_MED_THRESHOLD:
            return _FAN_MEDIUM
        return _FAN_HIGH

    def _derive_action(self, data) -> HVACAction:
        if data.get(C_UNIT_STATUS) != "on":
            return HVACAction.OFF
        if data.get(C_COMPRESSOR_STATUS) == "on":
            return (
                HVACAction.COOLING
                if data.get(C_ACTIVE_COOLING) == "on"
                else HVACAction.DRYING
            )
        if data.get(C_DEHUM_REQUEST) == "on":
            return HVACAction.DRYING
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Translate the HVAC mode into on/off + request registers."""
        if hvac_mode == HVACMode.OFF:
            await self._hub.write_entity_value(C_UNIT_ON_OFF, 0)
            return

        await self._hub.write_entity_value(C_UNIT_ON_OFF, 1)
        if hvac_mode == HVACMode.COOL:
            await self._hub.write_entity_value(C_ACTIVE_COOLING, 1)
            await self._hub.write_entity_value(C_DEHUMIDIFY, 1)
        elif hvac_mode == HVACMode.DRY:
            await self._hub.write_entity_value(C_ACTIVE_COOLING, 0)
            await self._hub.write_entity_value(C_DEHUMIDIFY, 1)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.DRY)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        pct = _FAN_MODE_PCT.get(fan_mode)
        if pct is None:
            return
        self._attr_fan_mode = fan_mode
        await self._hub.write_entity_value(C_FAN_MANUAL, pct)

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self._hub.write_entity_value(CLIMATE_TARGET_TEMP, temp)

    async def async_set_humidity(self, humidity: int) -> None:
        await self._hub.write_entity_value(CLIMATE_TARGET_HUMIDITY, humidity)
