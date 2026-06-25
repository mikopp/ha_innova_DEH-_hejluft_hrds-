"""Number platform (read-write numeric holding registers)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity

from .const import NUMBER_TYPES, MyNumberEntityDescription
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=NUMBER_TYPES,
        entity_cls=HrdsNumber,
    )


class HrdsNumber(HubBackedEntity, NumberEntity):
    """A read-write numeric register."""

    entity_description: MyNumberEntityDescription

    def __init__(self, platform_name, hub, device_info, description):
        super().__init__(platform_name, hub, device_info, description)
        self._attr_mode = description.mode
        self._attr_native_unit_of_measurement = description.unit_of_measurement
        self._attr_native_min_value = description.min_value
        self._attr_native_max_value = description.max_value
        self._attr_native_step = description.step

    def _apply_hub_payload(self, payload: Any) -> None:
        self._attr_native_value = payload

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        await self._hub.setter_function_callback(self, value)
