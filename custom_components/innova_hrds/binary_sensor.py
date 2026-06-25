"""Binary-sensor platform (read-only 0/1 input registers)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import BINARYSENSOR_TYPES, MyBinarySensorEntityDescription
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=BINARYSENSOR_TYPES,
        entity_cls=HrdsBinarySensor,
    )


class HrdsBinarySensor(HubBackedEntity, BinarySensorEntity):
    """A read-only 0/1 register exposed as a binary sensor."""

    entity_description: MyBinarySensorEntityDescription

    def _apply_hub_payload(self, payload: Any) -> None:
        if payload is None:
            return
        if isinstance(payload, str):
            self._attr_is_on = payload.lower() != "off"
        else:
            self._attr_is_on = bool(payload)
