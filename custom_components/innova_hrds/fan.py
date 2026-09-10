"""Fan platform for the HRDS+ recirculation fan.

The unit's own supply fan draws room air across the dehumidifier coil *in
addition* to whatever the central MVHR is already pushing through the duct, so
it is the lever an external controller uses to top the combined airflow up to a
target. `number.fan_manual_speed` writes the same register; this entity exists
because `fan.set_percentage` is the natural service for that job and it carries
commanded-vs-actual in one place.
"""

from __future__ import annotations

import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback

from .const import (
    C_FAN_MANUAL,
    C_SUPPLY_FAN_OUTPUT,
    C_SUPPLY_FAN_RPM,
    C_SUPPLY_FAN_STATUS,
    FAN_TYPES,
    MyFanEntityDescription,
)
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)

# supply_fan_status values that mean the fan is not moving air.
_FAN_STOPPED = {"off", "disabled", "wait_off", "alarm"}


async def async_setup_entry(hass, entry, async_add_entities):
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=FAN_TYPES,
        entity_cls=HrdsFan,
    )


class HrdsFan(HubBackedEntity, FanEntity):
    """The unit's supply/recirculation fan, as a percentage."""

    entity_description: MyFanEntityDescription

    def __init__(self, platform_name, hub, device_info, description):
        super().__init__(platform_name, hub, device_info, description)
        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
        )
        self._attr_percentage = 0
        self._attr_is_on = False

    @callback
    def _on_hub_update(self) -> None:
        data = self._hub.data

        # Report the *commanded* speed (holding register 1614, which we also
        # poll). Reading back the modulated analog output instead would make
        # the entity chase the unit's own modulation away from the setpoint.
        commanded = data.get(C_FAN_MANUAL)
        if commanded is not None:
            self._attr_percentage = int(round(float(commanded)))

        status = data.get(C_SUPPLY_FAN_STATUS)
        if status is not None:
            self._attr_is_on = status not in _FAN_STOPPED
        elif self._attr_percentage is not None:
            self._attr_is_on = self._attr_percentage > 0

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose actual output and RPM next to the commanded percentage.

        Whether the unit honours a commanded speed or clamps it into its
        dehumidify band is exactly what these two reveal.
        """
        data = self._hub.data
        return {
            "actual_output_percent": data.get(C_SUPPLY_FAN_OUTPUT),
            "actual_rpm": data.get(C_SUPPLY_FAN_RPM),
            "supply_fan_status": data.get(C_SUPPLY_FAN_STATUS),
        }

    async def async_set_percentage(self, percentage: int) -> None:
        self._attr_percentage = percentage
        self._attr_is_on = percentage > 0
        await self._hub.write_entity_value(C_FAN_MANUAL, float(percentage))

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs
    ) -> None:
        await self.async_set_percentage(percentage if percentage is not None else 100)

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_set_percentage(0)
