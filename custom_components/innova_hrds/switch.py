"""Switch platform (read-write 0/1 holding registers)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.helpers.restore_state import RestoreEntity

from .const import BINARY_TYPES, OPERATION_TYPES, MyBinaryEntityDescription
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=OPERATION_TYPES,
        entity_cls=HrdsOperationSwitch,
    )
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=BINARY_TYPES,
        entity_cls=HrdsSwitch,
    )


class HrdsSwitch(HubBackedEntity, SwitchEntity):
    """A read-write 0/1 register exposed as a switch."""

    entity_description: MyBinaryEntityDescription

    def _apply_hub_payload(self, payload: Any) -> None:
        if isinstance(payload, str):
            self._attr_is_on = payload.strip().lower() not in {
                "off",
                "0",
                "false",
                "no",
            }
        elif payload is not None:
            self._attr_is_on = bool(payload)

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        await self._hub.setter_function_callback(self, True)

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        await self._hub.setter_function_callback(self, False)


class HrdsOperationSwitch(HubBackedEntity, SwitchEntity, RestoreEntity):
    """Integration-level gate: allow dehumidify, cooling and fan requests.

    Not backed by a register. Off by default so a freshly connected unit is never
    started before the user has reviewed the setup entities; the last choice is
    restored across restarts.
    """

    entity_description: MyBinaryEntityDescription
    _attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state == STATE_ON
        self._hub.operation_allowed = self._attr_is_on

    def _apply_hub_payload(self, payload: Any) -> None:
        self._attr_is_on = self._hub.operation_allowed

    async def async_turn_on(self, **kwargs) -> None:
        self._hub.set_operation_allowed(True)

    async def async_turn_off(self, **kwargs) -> None:
        self._hub.set_operation_allowed(False)
