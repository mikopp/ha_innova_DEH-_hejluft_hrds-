"""Unit with a CNU2 display and wired room probes (has_display option on)."""

from __future__ import annotations

import pytest
from homeassistant.components.climate import ClimateEntityFeature

from tests.sim import registers as R

from .conftest import CLIMATE, allow_operation, set_hvac_mode

pytestmark = [
    pytest.mark.parametrize("sim_options", [{"overlays": ("display_with_probes",)}]),
    pytest.mark.parametrize("entry_options", [{"has_display": True}]),
]


async def test_display_settings_left_alone(setup):
    s = setup
    written = {w.address for w in s.device.write_log}
    assert R.PH01_ONOFF_DISPLAY not in written
    assert R.HA00_PROBE_SOURCE not in written
    # The first cycle has no read-back yet, so it writes every enable.
    assert written == {R.PH02_ONOFF_BMS, R.PH27_INT_BMS, R.PH28_DEU_BMS}
    assert s.device.holding[R.PH01_ONOFF_DISPLAY] == 1
    assert s.state("sensor", "setup_check").state == "attention"
    # Only free cooling without an outdoor probe - the display is on.
    assert s.state("sensor", "setup_check").attributes["issues"] == [
        "free_cooling_without_outdoor_probe"
    ]


async def test_display_switched_off_is_reported(setup, clock):
    s = setup
    s.device.set_display_on(False)
    await clock.poll()
    assert s.state("sensor", "unit_status").state == "off_by_display"
    assert (
        "unit_off_by_display" in (s.state("sensor", "setup_check").attributes["issues"])
    )
    s.device.set_display_on(True)
    await clock.poll()
    assert (
        "unit_off_by_display"
        not in (s.state("sensor", "setup_check").attributes["issues"])
    )


async def test_real_room_readings(setup):
    s = setup
    assert float(s.state("sensor", "room_temperature").state) == 22.5
    assert float(s.state("sensor", "room_humidity").state) == 55
    climate = s.state("climate", CLIMATE).attributes
    assert climate["current_temperature"] == 22.5
    assert climate["current_humidity"] == 55
    assert s.state("binary_sensor", "temp_probe_ok").state == "on"
    assert s.state("binary_sensor", "humidity_probe_ok").state == "on"


async def test_setpoints_offered_and_written_per_season(setup, clock):
    s = setup
    for key in ("summer_setpoint", "winter_setpoint", "humidity_setpoint"):
        assert s.entity_id("number", key), key
    climate = s.state("climate", CLIMATE).attributes
    assert climate["supported_features"] & ClimateEntityFeature.TARGET_TEMPERATURE
    assert climate["supported_features"] & ClimateEntityFeature.TARGET_HUMIDITY
    assert climate["temperature"] == 28.0  # summer setpoint

    await s.service("climate", "set_temperature", CLIMATE, temperature=26.5)
    await clock.settle()
    assert s.device.holding[R.SUMMER_SETPOINT] == 265
    assert s.state("climate", CLIMATE).attributes["temperature"] == 26.5

    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    assert s.state("climate", CLIMATE).attributes["temperature"] == 14.0
    await s.service("climate", "set_temperature", CLIMATE, temperature=18.0)
    await clock.settle()
    assert s.device.holding[R.WINTER_SETPOINT] == 180
    assert s.device.holding[R.SUMMER_SETPOINT] == 265


async def test_humidity_target_follows_unit_clamps(setup, clock):
    s = setup
    climate = s.state("climate", CLIMATE).attributes
    assert (climate["min_humidity"], climate["max_humidity"]) == (55, 65)
    await s.service("climate", "set_humidity", CLIMATE, humidity=62)
    await clock.settle()
    assert s.device.holding[R.HUMIDITY_SETPOINT] == 62
    # The number entity allows more than the unit accepts: the unit clamps
    # to PH30 and the read-back shows what it kept.
    await s.service("number", "set_value", "humidity_setpoint", value=80)
    await clock.settle()
    assert s.device.holding[R.HUMIDITY_SETPOINT] == 65
    assert float(s.state("number", "humidity_setpoint").state) == 65
    assert s.state("climate", CLIMATE).attributes["humidity"] == 65


@pytest.mark.parametrize(("mode", "action"), [("dry", "drying"), ("cool", "cooling")])
async def test_operation_with_display(setup, clock, mode, action):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, mode)
    climate = s.state("climate", CLIMATE)
    assert climate.state == mode
    assert climate.attributes["hvac_action"] == action
    # Switched off at the display: an OFF from any source wins.
    s.device.set_display_on(False)
    await clock.poll()
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "off"
