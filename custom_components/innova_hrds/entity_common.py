"""Shared entity base and platform setup helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Type, TypeVar

from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import (
    ATTR_MANUFACTURER,
    DEFAULT_NAME,
    DOMAIN,
    ENTITIES_DICT,
    INSTALLER_DEVICE_EXTRA_KEYS,
    INSTALLER_DEVICE_SUFFIX,
    INSTALLER_KEYS,
    SETUP_DEVICE_SUFFIX,
    SETUP_KEYS,
)

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=Entity)


class HubBackedEntity(Entity):
    """Base entity: holds the hub reference, device info and update hook."""

    entity_description: Any
    _attr_has_entity_name = True
    # Push-only: the hub drives updates, so HA must not also poll each entity.
    _attr_should_poll = False

    def __init__(self, platform_name: str, hub, device_info: dict, description: Any):
        self._platform_name = platform_name
        self._hub = hub
        self._attr_device_info = device_info
        self.entity_description = description

        entry_id = platform_name
        for dom, ident in device_info.get("identifiers") or ():
            if dom == DOMAIN:
                # The child devices only change where the entity is listed;
                # its unique id stays keyed on the config entry.
                entry_id = ident.removesuffix(SETUP_DEVICE_SUFFIX).removesuffix(
                    INSTALLER_DEVICE_SUFFIX
                )
                break
        self._attr_unique_id = f"{entry_id}-{description.key}"

    @property
    def available(self) -> bool:
        """Unavailable when the last poll failed or the key was never decoded.

        Home Assistant templates gate on `has_value()`, so an entity that keeps
        reporting its last good reading after the device has gone away is worse
        than one that reports nothing.
        """
        if not self._hub.last_update_success:
            return False
        key = self.entity_description.key
        # Not every entity is backed by a register. Composite entities (climate,
        # fan) aggregate several, and computed sensors are derived after the
        # poll - gating those on a register key would make climate and fan
        # permanently unavailable. They track the poll's health only.
        if key not in ENTITIES_DICT:
            return True
        return key in self._hub.data

    async def async_added_to_hass(self) -> None:
        self._hub.async_add_my_modbus_sensor(self._on_hub_update)
        # Setup primes the cache before creating entities: show that read-back
        # now instead of `unknown` until the first scheduled poll.
        if self._hub.last_update_success:
            self._on_hub_update()

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


def build_device_infos(
    entry, hub, main_device_id: str | None = None
) -> tuple[DeviceInfo, DeviceInfo, DeviceInfo]:
    """Return (main, setup, installer) device infos for a config entry.

    ``main_device_id`` is the registry id of the main device; the two child
    devices link to it with ``via_device_id`` (``via_device`` is deprecated and
    goes away in Home Assistant 2027.8). Leave it out only to build the main
    device itself, before there is an id.

    The device page then separates: the operational surface and post-setup
    configuration on the main device; everything the user must check once
    after connecting on the "setup" child; and the full installer menu, not
    needed for setup or day-to-day use, on the "installer" child.
    """
    identity = hub.identity
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    main = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=name,
        manufacturer=ATTR_MANUFACTURER,
        model="HRDS+ / DEH+",
        # The controller's own identification, as read by the identity check.
        model_id=identity.product_code,
        sw_version=identity.revision,
    )
    setup = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id + SETUP_DEVICE_SUFFIX)},
        name=f"{name} setup",
        manufacturer=ATTR_MANUFACTURER,
        model="Setup and installer configuration",
    )
    installer = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id + INSTALLER_DEVICE_SUFFIX)},
        name=f"{name} installer",
        manufacturer=ATTR_MANUFACTURER,
        model="Installer menu parameters",
    )
    if main_device_id is not None:
        setup["via_device_id"] = main_device_id
        installer["via_device_id"] = main_device_id
    return main, setup, installer


def get_hub_and_device_info(hass, entry) -> tuple:
    """Return (hub_name, hub, {main, setup, installer} device infos)."""
    hub_name = entry.options.get(CONF_NAME, entry.data[CONF_NAME])
    hub = entry.runtime_data
    # The main device is registered in async_setup_entry before the platforms.
    main = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    return hub_name, hub, build_device_infos(entry, hub, main.id if main else None)


def device_info_for(key: str, devices: tuple) -> DeviceInfo:
    """Pick the device an entity key is listed on."""
    main, setup, installer = devices
    if key in SETUP_KEYS:
        return setup
    if key in INSTALLER_KEYS or key in INSTALLER_DEVICE_EXTRA_KEYS:
        return installer
    return main


async def setup_platform_from_types(
    hass,
    entry,
    async_add_entities,
    types_dict: Dict[str, Any],
    entity_cls: Type[T],
) -> bool:
    """Instantiate one entity per entry in types_dict."""
    hub_name, hub, devices = get_hub_and_device_info(hass, entry)
    entities: List[T] = [
        entity_cls(hub_name, hub, device_info_for(desc.key, devices), desc)
        for desc in types_dict.values()
        # Setpoints the unit ignores (no room probe) are not created at all.
        if desc.key not in hub.hidden_keys
    ]
    async_add_entities(entities)
    return True
