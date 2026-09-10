"""Select platform (read-write enum holding registers)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity

from .const import SELECT_TYPES, MySelectEntityDescription
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=SELECT_TYPES,
        entity_cls=HrdsSelect,
    )


class HrdsSelect(HubBackedEntity, SelectEntity):
    """A read-write enum register exposed as a select."""

    entity_description: MySelectEntityDescription

    def __init__(self, platform_name, hub, device_info, description):
        super().__init__(platform_name, hub, device_info, description)
        self._attr_options = list(description.options or [])
        self._attr_current_option = description.default_select_option

    def _apply_hub_payload(self, payload: Any) -> None:
        # The hub decodes enum registers to the translation slug. A raw value
        # outside VALUES decodes to None rather than an option HA would reject.
        self._attr_current_option = payload if payload in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        await self._hub.setter_function_callback(self, option)
