"""The fan is the unit's: Home Assistant reads it and cannot set its speed.

The unit takes no fan-speed request over Modbus. It runs the fan at its own
manual request (PM20, 1614), clamped into the active band, and keeps it there
(UNIT_BEHAVIOUR.md 9.1, T22-T28). The band numbers are the only lever.
"""

from __future__ import annotations

import pytest
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.const import STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError

from tests.sim import registers as R

from .conftest import CLIMATE, FAN, add_entry, allow_operation, set_hvac_mode


async def test_fan_follows_the_band_during_dehumidify(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    fan = s.state("fan", FAN)
    assert fan.attributes["output_percent"] == 50
    assert fan.attributes["manual_request_percent"] == pytest.approx(50)
    assert float(s.state("sensor", "fan_manual_speed").state) == pytest.approx(50)
    assert float(s.state("sensor", "supply_fan_airflow").state) == pytest.approx(150)

    # A raised minimum raises the running fan (T25) ...
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=55)
    await clock.settle()
    assert s.state("fan", FAN).attributes["output_percent"] == 55
    assert float(s.state("sensor", "supply_fan_output").state) == pytest.approx(55)
    assert float(s.state("sensor", "fan_manual_speed").state) == pytest.approx(55)
    # ... a lowered one leaves it (T24, T26).
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=50)
    await clock.settle()
    assert s.state("fan", FAN).attributes["output_percent"] == 55


async def test_no_speed_control_and_nothing_written_to_pm20(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    s.device.clear_write_log()
    assert s.state("fan", FAN).attributes["supported_features"] == 0
    climate = s.state("climate", CLIMATE).attributes
    assert not climate["supported_features"] & ClimateEntityFeature.FAN_MODE
    assert "fan_modes" not in climate
    assert s.entity_id("number", "fan_manual_speed") is None
    with pytest.raises(HomeAssistantError):
        await s.service("fan", "set_percentage", FAN, percentage=60)
    await clock.settle()
    assert s.device.writes_to(R.FAN_MANUAL) == []


async def test_no_optimistic_update_before_poll(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=60)
    # Before the debounced refresh the state still shows the old values.
    assert s.state("fan", FAN).attributes["output_percent"] == 50
    assert float(s.state("number", "fan_min_speed_dehumidify").state) == 50
    await clock.settle()
    assert s.state("fan", FAN).attributes["output_percent"] == 60


async def test_airflow_zero_when_fan_off(setup, clock):
    s = setup
    assert s.state("sensor", "supply_fan_status").state == "off"
    assert float(s.state("sensor", "supply_fan_airflow").state) == 0.0
    assert s.state("fan", FAN).state == "off"


async def test_recirculation_is_damper_open_and_fan_running(setup, clock):
    s = setup
    assert s.state("binary_sensor", "recirculation_active").state == "off"
    await allow_operation(s)
    # The damper opens with the request; the fan waits out the pre-start.
    s.device.sequence_delay = 3600
    await set_hvac_mode(s, clock, "dry")
    assert s.state("sensor", "recirculation_damper").state == "on"
    assert s.state("sensor", "supply_fan_status").state == "wait_on"
    assert s.state("binary_sensor", "recirculation_active").state == "off"

    s.device.sequence_delay = 0
    await clock.poll()
    assert s.state("sensor", "supply_fan_status").state == "on"
    assert s.state("binary_sensor", "recirculation_active").state == "on"
    # 1112 is a fan request in %; it stays 0 while the unit recirculates for
    # a dehumidify request (UNIT_BEHAVIOUR.md T16, T18).
    assert float(s.state("sensor", "fan_integration_request").state) == 0

    await set_hvac_mode(s, clock, "fan_only")
    assert s.state("binary_sensor", "recirculation_active").state == "off"


async def test_fan_speed_unknown_without_a_tachometer_input(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert float(s.state("sensor", "supply_fan_output").state) > 0
    assert s.device.input[R.FAN_RPM] == 0
    assert s.state("sensor", "supply_fan_rpm").state == STATE_UNKNOWN


async def test_fan_speed_shown_with_a_tachometer_input(hass, sim, clock):
    sim.device.holding[R.TACHOMETER_ALLOCATIONS[-1]] = 45  # HB07: DI3 expansion
    s = await add_entry(hass, sim)
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert float(s.state("sensor", "supply_fan_rpm").state) > 0
