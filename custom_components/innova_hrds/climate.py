"""Composite climate entity for the Innova HRDS+ dehumidifier.

This entity is not backed by a single register. It aggregates several status
registers for display (temperature, humidity, HVAC action) and translates the
selected HVAC mode into the unit's on/off + dehumidify + integration request
registers.

The unit has two requests: dehumidify (DEU) and integration (INT). INT
dehumidifies *and* cools in summer but heats in winter, so the offered modes
follow the season: Cool only in summer, Heat only in winter and only when the
user enabled winter heating (never on a brine circuit).

The unit ORs its request sources (handbook 6.1): its own room-probe logic, the
DEU/INT digital inputs and Modbus. So the mode says what can make the unit act:

* Off - the unit is off, or on with nothing that could make it act (no request,
  no room probe). The action is then idle.
* Auto - on with no Modbus request, and a display or room probe lets the unit
  request by itself. Only offered while that holds.
* Cool / Heat - the INT request is set and can act (``hub.int_effect``): Cool in
  summer on a unit with the integration function (PG02), Heat in winter only
  with winter heating allowed (never on brine). An INT request that cannot act
  does not decide the mode.
* Dry - the DEU request is set, or the unit reports a dehumidify request from
  another source such as a digital input.

The action reports what the unit does, not what was requested: Heating and
Cooling need the unit's own evidence (``hub.is_heating`` / ``hub.is_cooling``).

Setting Off clears both requests and, if the unit could still act on its own,
switches it off: over Modbus that is the only way to stop its automatic logic.
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
from homeassistant.exceptions import ServiceValidationError

from .const import (
    C_ACTIVE_COOLING,
    C_ACTIVE_COOLING_AVAILABLE,
    C_COMPRESSOR_STATUS,
    C_DEHUM_REQUEST,
    C_DEHUMIDIFY,
    C_FAN_MANUAL,
    C_HUMIDITY_PROBE_OK,
    C_SUPPLY_FAN_OUTPUT,
    C_SUPPLY_FAN_STATUS,
    C_TEMP_PROBE_OK,
    C_UNIT_ON_OFF,
    C_UNIT_STATUS,
    C_WINTER_SETPOINT,
    CLIMATE_CURRENT_HUMIDITY,
    CLIMATE_CURRENT_TEMP,
    CLIMATE_MAX_HUMIDITY,
    CLIMATE_MIN_HUMIDITY,
    CLIMATE_TARGET_HUMIDITY,
    CLIMATE_TARGET_TEMP,
    CLIMATE_TYPES,
    MyClimateEntityDescription,
)
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)

# Fan mode labels and the percentages written to PM20 (reg 1614).
#
# Read-back is the *actual* output (reg 639), so the mode shown is what the fan
# is doing, not what was asked of it. Those can differ: the manual describes the
# manual request as being scaled linearly across the active mode's min/max band
# (PF28/PF10 for dehumidify, PF27/PF09 for integration), so with the factory
# 50-85 % band, "low" (30) may read back as `medium`. Open PF28 to 0 and PF10 to
# 100 - both writable numbers - for the presets to map one-for-one.
# See plans/todo.md.
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

    def __init__(self, platform_name, hub, device_info, description):
        super().__init__(platform_name, hub, device_info, description)
        self._attr_temperature_unit = description.temperature_unit
        features = description.supported_features
        # Without a room probe the unit ignores its setpoints: do not offer them.
        if not hub.show_temperature_target:
            features &= ~ClimateEntityFeature.TARGET_TEMPERATURE
        if not hub.show_humidity_target:
            features &= ~ClimateEntityFeature.TARGET_HUMIDITY
        self._attr_supported_features = features
        self._attr_hvac_modes = self._modes_for(hub.active_season)
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._attr_min_temp = 15.0
        self._attr_max_temp = 35.0
        self._attr_target_temperature_step = 0.5
        self._attr_min_humidity = 30
        self._attr_max_humidity = 90
        self._attr_fan_modes = _FAN_MODES
        self._attr_fan_mode = _FAN_OFF

    def _modes_for(self, season) -> list[HVACMode]:
        hub = self._hub
        modes = [HVACMode.OFF]
        if hub.auto_capable:
            modes.append(HVACMode.AUTO)
        modes.append(HVACMode.DRY)
        # INT needs the integration function (PG02); unknown counts as present.
        if hub.data.get(C_ACTIVE_COOLING_AVAILABLE) != "off":
            if season == "summer":
                modes.append(HVACMode.COOL)
            elif season == "winter" and hub.allow_winter_heating:
                modes.append(HVACMode.HEAT)
        return modes

    @callback
    def _on_hub_update(self) -> None:
        data = self._hub.data
        self._attr_hvac_modes = self._modes_for(self._hub.active_season)

        # No reading when the unit reports a probe fault (AL28 / AL34;
        # probe_ok == "off" means the alarm is active) or when the input carries
        # the unwired-probe sentinel (the hub decodes that to None). Never keep
        # the previous value: a probe that disappears must not leave a stale
        # temperature on the card. probe_ok == None (no alarm data yet) is
        # treated as healthy.
        temp = data.get(CLIMATE_CURRENT_TEMP)
        if data.get(C_TEMP_PROBE_OK) == "off" or temp is None:
            self._attr_current_temperature = None
        else:
            self._attr_current_temperature = float(temp)

        hum = data.get(CLIMATE_CURRENT_HUMIDITY)
        if data.get(C_HUMIDITY_PROBE_OK) == "off" or hum is None:
            self._attr_current_humidity = None
        else:
            self._attr_current_humidity = int(hum)

        # Advertise the unit's own PU01 clamps (PH29/PH30) instead of a guess.
        hum_min = data.get(CLIMATE_MIN_HUMIDITY)
        hum_max = data.get(CLIMATE_MAX_HUMIDITY)
        if hum_min is not None and hum_max is not None and hum_min < hum_max:
            self._attr_min_humidity = int(hum_min)
            self._attr_max_humidity = int(hum_max)

        target_hum = data.get(CLIMATE_TARGET_HUMIDITY)
        if target_hum is not None:
            self._attr_target_humidity = int(target_hum)

        # SEtC drives summer integration, SEtH winter integration.
        target_temp = data.get(
            C_WINTER_SETPOINT
            if self._hub.active_season == "winter"
            else CLIMATE_TARGET_TEMP
        )
        if target_temp is not None:
            self._attr_target_temperature = float(target_temp)

        self._attr_hvac_mode = self._derive_mode(data)
        self._attr_hvac_action = self._derive_action(data)
        self._attr_fan_mode = self._derive_fan_mode(data)
        self.async_write_ha_state()

    def _derive_mode(self, data) -> HVACMode:
        if data.get(C_UNIT_ON_OFF) != "on" and data.get(C_UNIT_STATUS) != "on":
            return HVACMode.OFF
        effect = self._hub.int_effect
        if effect is not None:
            return HVACMode.HEAT if effect == "heat" else HVACMode.COOL
        if data.get(C_DEHUMIDIFY) == "on":
            return HVACMode.DRY
        if self._hub.auto_capable:
            return HVACMode.AUTO
        # A request we did not set (digital input, PU05): show what it does.
        if data.get(C_DEHUM_REQUEST) == "on":
            return HVACMode.DRY
        # On, but nothing can make it act: effectively off (action: idle).
        return HVACMode.OFF

    def _derive_fan_mode(self, data) -> str:
        status = data.get(C_SUPPLY_FAN_STATUS)
        if status in ("off", "disabled", "wait_off"):
            return _FAN_OFF
        # The *actual* output (reg 639), same source as fan.hrds_supply_fan, so
        # the two entities always agree about what the fan is doing. The
        # commanded setpoint is on number.fan_manual_speed and on the fan
        # entity's `commanded_percent` attribute.
        pct = data.get(C_SUPPLY_FAN_OUTPUT)  # float 0-100
        if pct is None:
            return _FAN_OFF
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
        # What the unit does, not what was asked: an INT request the unit
        # cannot or does not act on is at most dehumidifying.
        if self._hub.is_heating:
            return HVACAction.HEATING
        if self._hub.is_cooling:
            return HVACAction.COOLING
        if data.get(C_COMPRESSOR_STATUS) == "on" or data.get(C_DEHUM_REQUEST) == "on":
            return HVACAction.DRYING
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Translate the HVAC mode into on/off + request registers."""
        hub = self._hub
        if hvac_mode == HVACMode.OFF:
            data = hub.data
            # Judged before the writes: a request we did not set means some
            # other source (digital input, PU05) keeps the unit going.
            foreign_request = (
                data.get(C_DEHUM_REQUEST) == "on"
                and data.get(C_DEHUMIDIFY) != "on"
                and data.get(C_ACTIVE_COOLING) != "on"
            )
            await hub.write_entity_value(C_ACTIVE_COOLING, 0)
            await hub.write_entity_value(C_DEHUMIDIFY, 0)
            # The unit's own logic only stops when the unit is off.
            if hub.auto_capable or foreign_request:
                await hub.write_entity_value(C_UNIT_ON_OFF, 0)
            return

        if hvac_mode == HVACMode.AUTO:
            if not hub.auto_capable:
                raise ServiceValidationError(
                    "Auto needs a display or a room probe the unit can regulate "
                    "on; without one the unit never requests by itself. Use Dry"
                    + (" or Cool." if HVACMode.COOL in self.hvac_modes else ".")
                )
            await hub.write_entity_value(C_ACTIVE_COOLING, 0)
            await hub.write_entity_value(C_DEHUMIDIFY, 0)
            await hub.write_entity_value(C_UNIT_ON_OFF, 1)
            return

        # Requests first: the hub refuses heating (or brine winter dehumidify)
        # before the unit is switched on.
        if hvac_mode in (HVACMode.COOL, HVACMode.HEAT):
            await hub.write_entity_value(C_ACTIVE_COOLING, 1)
            await hub.write_entity_value(
                C_DEHUMIDIFY, 1 if hvac_mode == HVACMode.COOL else 0
            )
        elif hvac_mode == HVACMode.DRY:
            await hub.write_entity_value(C_ACTIVE_COOLING, 0)
            await hub.write_entity_value(C_DEHUMIDIFY, 1)
        await hub.write_entity_value(C_UNIT_ON_OFF, 1)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(
            HVACMode.AUTO if self._hub.auto_capable else HVACMode.DRY
        )

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        pct = _FAN_MODE_PCT.get(fan_mode)
        if pct is None:
            return
        # No optimistic update: fan_mode reflects actual output, which the unit
        # decides. Write and let the next poll report it.
        await self._hub.write_entity_value(C_FAN_MANUAL, pct)

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self._hub.write_entity_value(
                C_WINTER_SETPOINT
                if self._hub.active_season == "winter"
                else CLIMATE_TARGET_TEMP,
                temp,
            )

    async def async_set_humidity(self, humidity: int) -> None:
        await self._hub.write_entity_value(CLIMATE_TARGET_HUMIDITY, humidity)
