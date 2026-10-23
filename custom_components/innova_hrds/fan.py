"""Fan platform for the HRDS+ recirculation fan.

The unit's own supply fan draws room air across the dehumidifier coil *in
addition* to whatever the central MVHR is already pushing through the duct.

The entity is read-only: ``output_percent`` is what the fan is *actually* doing
(``outAO_SupplyFan``, reg 639) and ``is_on`` follows the unit's fan status. Home
Assistant shows ``percentage`` only on a fan that can set its speed, so the
output is an attribute of its own. The
unit takes no fan-speed request over Modbus: ``PM20`` (1614) is its own manual
request and does not hold a written value (``UNIT_BEHAVIOUR.md`` 9.1, T23). The
speed follows the active band (``PF28``/``PF10`` dehumidify, ``PF27``/``PF09``
integration), which are number entities of their own.
"""

from __future__ import annotations

import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback

from .const import (
    C_FAN_MANUAL,
    C_SUPPLY_FAN_OUTPUT,
    C_SUPPLY_FAN_RPM,
    C_SUPPLY_FAN_STATUS,
    FAN_TYPES,
    MyFanEntityDescription,
)
from .entity_common import HubBackedEntity, setup_platform_from_types

_LOGGER = logging.getLogger(__name__)

# supply_fan_status values that mean the fan is not moving air.
_FAN_STOPPED = {"off", "disabled", "wait_off", "alarm"}


async def async_setup_entry(hass, entry, async_add_entities):
    return await setup_platform_from_types(
        hass=hass,
        entry=entry,
        async_add_entities=async_add_entities,
        types_dict=FAN_TYPES,
        entity_cls=HrdsFan,
    )


class HrdsFan(HubBackedEntity, FanEntity):
    """The unit's supply/recirculation fan, as a percentage (read-only)."""

    entity_description: MyFanEntityDescription

    def __init__(self, platform_name, hub, device_info, description):
        super().__init__(platform_name, hub, device_info, description)
        self._attr_supported_features = FanEntityFeature(0)
        self._output: int | None = None
        self._attr_is_on = False

    @callback
    def _on_hub_update(self) -> None:
        data = self._hub.data

        actual = data.get(C_SUPPLY_FAN_OUTPUT)
        if actual is not None:
            self._output = int(round(float(actual)))

        status = data.get(C_SUPPLY_FAN_STATUS)
        if status is not None:
            self._attr_is_on = status not in _FAN_STOPPED
        elif self._output is not None:
            self._attr_is_on = self._output > 0

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """The actual output, the unit's manual request, RPM and fan status."""
        data = self._hub.data
        return {
            "output_percent": self._output,
            "manual_request_percent": data.get(C_FAN_MANUAL),
            "actual_rpm": data.get(C_SUPPLY_FAN_RPM),
            "supply_fan_status": data.get(C_SUPPLY_FAN_STATUS),
        }
