"""The fan is the unit's: Home Assistant shows it and can neither switch it nor
set its speed.

The unit runs the fan with every request and stops it after a run-on. It runs
it at its own manual request (PM20, 1614), clamped into the active band, and
keeps it there (UNIT_BEHAVIOUR.md 9.1-9.3, T19, T22-T28). The band numbers are
the only lever. Whether the fan turns is its status (1119): On or the run-on
Wait OFF (ADR-0028).
"""

from __future__ import annotations

import pytest
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er

from custom_components.innova_hrds.const import DOMAIN
from tests.sim import registers as R

from .conftest import CLIMATE, FAN_RUNNING, add_entry, allow_operation, set_hvac_mode


async def test_fan_follows_the_band_during_dehumidify(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert s.state("binary_sensor", FAN_RUNNING).state == "on"
    assert float(s.state("sensor", "supply_fan_output").state) == pytest.approx(50)
    assert float(s.state("sensor", "fan_manual_speed").state) == pytest.approx(50)
    assert float(s.state("sensor", "supply_fan_airflow").state) == pytest.approx(150)

    # A raised minimum raises the running fan (T25) ...
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=55)
    await clock.settle()
    assert float(s.state("sensor", "supply_fan_output").state) == pytest.approx(55)
    assert float(s.state("sensor", "fan_manual_speed").state) == pytest.approx(55)
    # ... a lowered one leaves it (T24, T26).
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=50)
    await clock.settle()
    assert float(s.state("sensor", "supply_fan_output").state) == pytest.approx(55)


async def test_no_fan_control_and_nothing_written_to_pm20(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    s.device.clear_write_log()
    assert s.entity_id("fan", "hrds_supply_fan") is None
    assert s.entity_id("number", "fan_manual_speed") is None
    climate = s.state("climate", CLIMATE).attributes
    assert not climate["supported_features"] & ClimateEntityFeature.FAN_MODE
    assert "fan_modes" not in climate
    await clock.poll()
    assert s.device.writes_to(R.FAN_MANUAL) == []


async def test_no_optimistic_update_before_poll(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=60)
    # Before the debounced refresh the state still shows the old values.
    assert float(s.state("sensor", "supply_fan_output").state) == pytest.approx(50)
    assert float(s.state("number", "fan_min_speed_dehumidify").state) == 50
    await clock.settle()
    assert float(s.state("sensor", "supply_fan_output").state) == pytest.approx(60)


async def test_airflow_zero_when_fan_off(setup, clock):
    s = setup
    assert s.state("sensor", "supply_fan_status").state == "off"
    assert s.state("binary_sensor", FAN_RUNNING).state == "off"
    assert float(s.state("sensor", "supply_fan_airflow").state) == 0.0


async def test_running_follows_the_status_through_start_and_run_on(setup, clock):
    s = setup
    await allow_operation(s)
    # Wait ON: the damper is open, the fan waits out PS01 and does not turn.
    s.device.sequence_delay = 3600
    await set_hvac_mode(s, clock, "dry")
    assert s.state("sensor", "supply_fan_status").state == "wait_on"
    assert s.state("binary_sensor", FAN_RUNNING).state == "off"
    assert float(s.state("sensor", "supply_fan_airflow").state) == 0.0

    s.device.sequence_delay = 0
    await clock.poll()
    assert s.state("binary_sensor", FAN_RUNNING).state == "on"

    # Wait OFF: the request ended, the fan runs on at PF26 (T19).
    s.device.holding[R.PF26_FAN_POST_RUN] = 4000
    s.device.run_on = 3600
    await set_hvac_mode(s, clock, "fan_only")
    assert s.state("sensor", "supply_fan_status").state == "wait_off"
    assert s.state("binary_sensor", FAN_RUNNING).state == "on"
    assert float(s.state("sensor", "supply_fan_airflow").state) == pytest.approx(120)
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "fan"
    assert s.state("binary_sensor", "recirculation_active").state == "off"

    s.device.run_on = 0
    await clock.poll()
    assert s.state("binary_sensor", FAN_RUNNING).state == "off"
    assert float(s.state("sensor", "supply_fan_airflow").state) == 0.0
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "idle"


async def test_alarm_stops_the_fan(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    s.device.set_fan_fault()
    await clock.poll()
    assert s.state("sensor", "supply_fan_status").state == "alarm"
    assert s.state("binary_sensor", FAN_RUNNING).state == "off"
    assert float(s.state("sensor", "supply_fan_airflow").state) == 0.0


async def test_old_fan_entity_and_manual_speed_number_are_removed(hass, sim):
    # Up to 0.9.4 the fan was a fan entity and PM20 a number.
    s = await add_entry(hass, sim)
    registry = er.async_get(hass)
    prefix = f"{s.entry.entry_id}-"
    registry.async_get_or_create(
        "fan", DOMAIN, prefix + "hrds_supply_fan", config_entry=s.entry
    )
    registry.async_get_or_create(
        "number", DOMAIN, prefix + "fan_manual_speed", config_entry=s.entry
    )
    await hass.config_entries.async_reload(s.entry.entry_id)
    await hass.async_block_till_done()
    assert s.entity_id("fan", "hrds_supply_fan") is None
    assert s.entity_id("number", "fan_manual_speed") is None
    assert s.state("binary_sensor", FAN_RUNNING) is not None


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
