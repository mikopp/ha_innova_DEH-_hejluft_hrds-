"""Binary-sensor platform (read-only 0/1 input registers)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import (
    BINARYSENSOR_TYPES,
    BRINE_GUARD_MAX_AGE_HOURS,
    C_BRINE_GUARD,
    MyBinarySensorEntityDescription,
)
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

    @property
    def available(self) -> bool:
        # The brine guard judges a Home Assistant sensor, not the unit: it must
        # keep showing a blocked guard while the Modbus link is down.
        if self.entity_description.key == C_BRINE_GUARD:
            return True
        return super().available

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != C_BRINE_GUARD:
            return None
        hub = self._hub
        reported = hub.brine_last_reported
        return {
            "source_entity": hub.brine_entity,
            "temperature": hub.brine_temperature,
            "minimum_temperature": hub.brine_min_temperature,
            "last_reported": reported.isoformat() if reported else None,
            "max_age_hours": BRINE_GUARD_MAX_AGE_HOURS,
            "reason": hub.brine_guard_reason,
        }
