"""Button platform (actions not backed by a register)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .const import BUTTON_TYPES, MyButtonEntityDescription
from .entity_common import HubBackedEntity, setup_platform_from_types


async def async_setup_entry(hass, entry, async_add_entities):
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=BUTTON_TYPES,
        entity_cls=HrdsInstallerRefreshButton,
    )


class HrdsInstallerRefreshButton(HubBackedEntity, ButtonEntity):
    """Read the installer parameters, which the regular poll leaves out."""

    entity_description: MyButtonEntityDescription

    async def async_press(self) -> None:
        await self._hub.async_refresh_installer()
