"""Switch platform (read-write 0/1 holding registers)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import (
    BINARY_TYPES,
    OPERATION_TYPES,
    SWITCH_HINTS,
    MyBinaryEntityDescription,
)
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """When to leave the switch on or turn it off, in the user's language."""
        hint = SWITCH_HINTS.get(self.entity_description.key)
        if hint is None:
            return None
        german = self.hass is not None and self.hass.config.language.startswith("de")
        return {"hint": hint[1] if german else hint[0]}

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


class _GateOwner(ExtraStoredData):
    """Which entity (unique id) a stored gate state belongs to."""

    def __init__(self, unique_id: str | None) -> None:
        self.unique_id = unique_id

    def as_dict(self) -> dict[str, Any]:
        return {"unique_id": self.unique_id}


class HrdsOperationSwitch(HubBackedEntity, SwitchEntity, RestoreEntity):
    """Integration-level gate: allow dehumidify, cooling and fan requests.

    Not backed by a register. Off by default so a freshly connected unit is never
    started before the user has reviewed the setup entities; the last choice is
    restored across restarts.

    Home Assistant keys restored state by entity id, and a re-added entry gets
    the same entity id as the one it replaces. The stored state therefore
    carries the unique id (which contains the config entry id), and a state
    left behind by another entry is not restored: a new entry starts closed.
    A state stored without an owner (written before this check existed) is not
    restored either, so the gate is closed once after the update.
    """

    entity_description: MyBinaryEntityDescription
    _attr_is_on = False

    async def async_added_to_hass(self) -> None:
        # Restore before the base class publishes the hub state, so the gate
        # never flickers off on startup.
        last = await self.async_get_last_state()
        owner = await self.async_get_last_extra_data()
        if (
            last is not None
            and owner is not None
            and owner.as_dict().get("unique_id") == self.unique_id
        ):
            self._attr_is_on = last.state == STATE_ON
        self._hub.operation_allowed = self._attr_is_on
        await super().async_added_to_hass()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return _GateOwner(self.unique_id)

    def _apply_hub_payload(self, payload: Any) -> None:
        self._attr_is_on = self._hub.operation_allowed

    async def async_turn_on(self, **kwargs) -> None:
        self._hub.set_operation_allowed(True)

    async def async_turn_off(self, **kwargs) -> None:
        self._hub.set_operation_allowed(False)
