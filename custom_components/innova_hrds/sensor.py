"""Sensor platform (read-only input registers, including enum status)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity

from .const import C_SETUP_CHECK, C_WATER_CHECK, SENSOR_TYPES, MySensorEntityDescription
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=SENSOR_TYPES,
        entity_cls=HrdsSensor,
    )


class HrdsSensor(HubBackedEntity, SensorEntity):
    """A read-only numeric or enum sensor."""

    entity_description: MySensorEntityDescription

    def _apply_hub_payload(self, payload: Any) -> None:
        if payload is None:
            self._attr_native_value = None
            return
        # Enum sensors receive the translation slug as a string straight from
        # the hub; numeric sensors receive a float.
        self._attr_native_value = payload

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        key = self.entity_description.key
        if key == C_SETUP_CHECK:
            return {
                "issues": list(self._hub.setup_issues),
                "operation_allowed": self._hub.operation_allowed,
            }
        if key == C_WATER_CHECK:
            return {
                "issues": list(self._hub.water_issues),
                "water_circuit": self._hub.water_circuit,
            }
        return None
