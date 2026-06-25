"""Shared entity base and platform setup helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Type, TypeVar

from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .const import ATTR_MANUFACTURER, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=Entity)


class HubBackedEntity(Entity):
    """Base entity: holds the hub reference, device info and update hook."""

    entity_description: Any
    _attr_has_entity_name = True

    def __init__(self, platform_name: str, hub, device_info: dict, description: Any):
        self._platform_name = platform_name
        self._hub = hub
        self._attr_device_info = device_info
        self.entity_description = description

        entry_id = platform_name
        for dom, ident in device_info.get("identifiers") or set():
            if dom == DOMAIN:
                entry_id = ident
                break
        self._attr_unique_id = f"{entry_id}-{description.key}"

    async def async_added_to_hass(self) -> None:
        self._hub.async_add_my_modbus_sensor(self._on_hub_update)

    async def async_will_remove_from_hass(self) -> None:
        self._hub.async_remove_my_modbus_sensor(self._on_hub_update)

    @callback
    def _on_hub_update(self) -> None:
        try:
            self._apply_hub_payload(self._hub.data.get(self.entity_description.key))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "apply payload failed for %s: %r", self.entity_description.key, exc
            )
        self.async_write_ha_state()

    def _apply_hub_payload(self, payload: Any) -> None:
        """Map the hub payload onto entity attributes (override in subclasses)."""


def get_hub_and_device_info(hass, entry) -> tuple:
    """Return (hub_name, hub, device_info) for a config entry."""
    hub_name = entry.options.get(CONF_NAME, entry.data[CONF_NAME])
    hub = hass.data[DOMAIN][hub_name]["hub"]
    device_info = {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": entry.data.get(CONF_NAME, DEFAULT_NAME),
        "manufacturer": ATTR_MANUFACTURER,
        "model": "HRDS+ / DEH+",
    }
    return hub_name, hub, device_info


async def setup_platform_from_types(
    hass,
    entry,
    async_add_entities,
    types_dict: Dict[str, Any],
    entity_cls: Type[T],
) -> bool:
    """Instantiate one entity per entry in types_dict."""
    hub_name, hub, device_info = get_hub_and_device_info(hass, entry)
    entities: List[T] = [
        entity_cls(hub_name, hub, device_info, desc) for desc in types_dict.values()
    ]
    async_add_entities(entities)
    return True
