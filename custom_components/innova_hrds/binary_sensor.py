"""Binary-sensor platform (read-only 0/1 input registers)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import (
    BINARYSENSOR_TYPES,
    BRINE_GUARD_MAX_AGE_HOURS,
    C_ACTIVE_COOLING_AVAILABLE,
    C_AUTO_HEATING,
    C_BRINE_GUARD,
    C_ROOM_TEMPERATURE,
    C_WINTER_SETPOINT,
    MyBinarySensorEntityDescription,
)
from .entity_common import HubBackedEntity, setup_platform_from_types
from .installer_params import installer_key

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
        key = self.entity_description.key
        if key == C_AUTO_HEATING:
            return self._auto_heating_attributes()
        if key != C_BRINE_GUARD:
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

    def _auto_heating_attributes(self) -> dict[str, Any]:
        """On what the unit heats by itself, so the user can react."""
        hub = self._hub
        d = hub.data
        starts, stops = hub.auto_heating_band
        return {
            "heating": hub.is_heating,
            "temperature_source": "display" if hub.has_display else "room_probe",
            "room_temperature": d.get(C_ROOM_TEMPERATURE),
            "winter_setpoint": d.get(C_WINTER_SETPOINT),
            "dead_band": d.get(installer_key("PF12")),
            "starts_below": starts,
            "stops_above": stops,
            "winter_setpoint_min": d.get(installer_key("PH09")),
            "winter_setpoint_max": d.get(installer_key("PH10")),
            "integration_function": d.get(C_ACTIVE_COOLING_AVAILABLE),
            "season": hub.active_season,
            "winter_heating_allowed": hub.allow_winter_heating,
            "water_circuit": hub.water_circuit,
        }
