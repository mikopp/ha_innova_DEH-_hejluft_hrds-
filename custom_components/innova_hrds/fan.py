"""Fan platform for the HRDS+ recirculation fan.

The unit's own supply fan draws room air across the dehumidifier coil *in
addition* to whatever the central MVHR is already pushing through the duct, so
it is the lever an external controller uses to top the combined airflow up to a
target.

Standard HA fan semantics: the entity's ``percentage`` is what the fan is
*actually* doing (``outAO_SupplyFan``, reg 639), and ``set_percentage`` issues a
command (``PM20_SupplyFan_Manual``, reg 1614). The commanded value stays visible
as an attribute, so a divergence between the two is legible - which is exactly
how firmware clamping or band-rescaling shows up. ``number.fan_manual_speed``
exposes the same setpoint register as a plain input.
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

        # Report what the fan is actually doing, not what was asked for.
        actual = data.get(C_SUPPLY_FAN_OUTPUT)
        if actual is not None:
            self._attr_percentage = int(round(float(actual)))

        status = data.get(C_SUPPLY_FAN_STATUS)
        if status is not None:
            self._attr_is_on = status not in _FAN_STOPPED
        elif self._attr_percentage is not None:
            self._attr_is_on = self._attr_percentage > 0

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the commanded setpoint next to the actual state.

        The state is the actual output; `commanded_percent` is what was last
        written to PM20. If those disagree, the firmware is not taking the
        setpoint at face value - see `plans/todo.md` on band rescaling.
        """
        data = self._hub.data
        return {
            "commanded_percent": data.get(C_FAN_MANUAL),
            "actual_rpm": data.get(C_SUPPLY_FAN_RPM),
            "supply_fan_status": data.get(C_SUPPLY_FAN_STATUS),
        }

    async def async_set_percentage(self, percentage: int) -> None:
        # Deliberately no optimistic update: `percentage` means *actual* output,
        # and the unit may not adopt the setpoint verbatim. Write, then let the
        # next poll report what really happened.
        await self._hub.write_entity_value(C_FAN_MANUAL, float(percentage))

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs
    ) -> None:
        await self.async_set_percentage(percentage if percentage is not None else 100)

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_set_percentage(0)
