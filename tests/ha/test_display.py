"""Unit with a CNU2 display and its built-in room sensors (has_display on).

The scenario is the real headless dump patched best-effort into a display unit
(overlay ``display_cnu2``); no dump of a real display unit exists yet.
"""

from __future__ import annotations

import pytest
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.exceptions import ServiceValidationError

from tests.sim import registers as R

from .conftest import CLIMATE, allow_operation, set_hvac_mode

pytestmark = [
    pytest.mark.parametrize("sim_options", [{"overlays": ("display_cnu2",)}]),
    pytest.mark.parametrize("entry_options", [{"has_display": True}]),
]


async def test_display_settings_left_alone(setup):
    s = setup
    written = {w.address for w in s.device.write_log}
    assert R.PH01_ONOFF_DISPLAY not in written
    assert R.HA00_PROBE_SOURCE not in written
    # Only the enable the unit lacks: PH27/PH28 are 1 from factory.
    assert written == {R.PH02_ONOFF_BMS}
    assert s.device.holding[R.PH01_ONOFF_DISPLAY] == 1
    assert s.state("sensor", "setup_check").state == "attention"
    # Free cooling without an outdoor probe, and the display's room
    # temperature lets the unit heat by itself in winter - the display is on.
    assert s.state("sensor", "setup_check").attributes["issues"] == [
        "free_cooling_without_outdoor_probe",
        "unit_heats_on_its_own",
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
    # The unit clamps SEtH to PH09..PH10 (factory 14 degC both): the climate
    # offers only that range.
    with pytest.raises(ServiceValidationError, match="14.0 to 14.0"):
        await s.service("climate", "set_temperature", CLIMATE, temperature=18.0)
    await s.service("climate", "set_temperature", CLIMATE, temperature=14.0)
    await clock.settle()
    assert s.device.holding[R.WINTER_SETPOINT] == 140
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


# ---- auto: the unit's own room-sensor logic ------------------------------------
async def test_auto_lets_the_unit_dehumidify_on_its_own(setup, clock):
    s = setup
    await allow_operation(s)
    climate = s.state("climate", CLIMATE)
    assert "auto" in climate.attributes["hvac_modes"]
    s.device.clear_write_log()
    await set_hvac_mode(s, clock, "auto")
    # No Modbus request: the unit decides from its own humidity reading. The
    # requests are already clear, so only the unit is switched on.
    assert [(w.address, w.value) for w in s.device.write_log] == [(R.BMS_ON, 1)]
    climate = s.state("climate", CLIMATE)
    assert climate.state == "auto"
    assert climate.attributes["hvac_action"] == "idle"  # 55 %RH, below PU01 + PU07

    s.device.set_room_humidity(70)
    await clock.poll()
    climate = s.state("climate", CLIMATE)
    assert climate.state == "auto"
    assert climate.attributes["hvac_action"] == "drying"

    # Off has to switch the unit off: nothing else stops its own logic. Our
    # requests are already clear, so that is the only write.
    s.device.clear_write_log()
    await set_hvac_mode(s, clock, "off")
    assert [(w.address, w.value) for w in s.device.write_log] == [(R.BMS_ON, 0)]
    climate = s.state("climate", CLIMATE)
    assert climate.state == "off"
    assert climate.attributes["hvac_action"] == "off"
    assert s.state("binary_sensor", "dehumidify_request").state == "off"


async def test_explicit_request_wins_over_auto(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert s.state("climate", CLIMATE).state == "dry"
    await set_hvac_mode(s, clock, "auto")
    assert s.device.holding[R.DEU_REQUEST] == 0
    assert s.state("climate", CLIMATE).state == "auto"


async def test_turn_on_prefers_auto(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("climate", "turn_on", CLIMATE)
    await clock.settle()
    assert s.state("climate", CLIMATE).state == "auto"


async def test_auto_withdrawn_on_humidity_probe_fault(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    s.device.raise_alarm("AL34")
    s.device.unplug_probe(R.ROOM_HUMIDITY)
    await clock.poll()
    climate = s.state("climate", CLIMATE)
    # The temperature sensor still drives INT in summer (PG02 = 1).
    assert "auto" in climate.attributes["hvac_modes"]
    s.device.raise_alarm("AL28")
    s.device.unplug_probe(R.ROOM_TEMP)
    await clock.poll()
    climate = s.state("climate", CLIMATE)
    assert "auto" not in climate.attributes["hvac_modes"]
    # On with nothing that can make it act: Standby.
    assert climate.state == "fan_only"
    assert climate.attributes["hvac_action"] == "idle"
    with pytest.raises(ServiceValidationError, match="auto"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="auto")


# ---- the unit's own winter heating (room temperature below SEtH - PF12) -------
async def test_unit_heats_on_its_own_and_says_on_what(setup, clock):
    """'Allow winter heating' is off, yet the unit heats: the user is told."""
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    await set_hvac_mode(s, clock, "auto")
    sensor = s.state("binary_sensor", "automatic_heating")
    assert sensor.state == "on"
    assert sensor.attributes["heating"] is False  # room 22.5, SEtH 14
    assert sensor.attributes["temperature_source"] == "display"
    assert sensor.attributes["winter_setpoint"] == 14.0
    assert sensor.attributes["starts_below"] == 13.5  # PF12 = 0.5
    assert sensor.attributes["winter_setpoint_max"] == 14.0  # PH10
    assert sensor.attributes["winter_heating_allowed"] is False
    assert (
        "unit_heats_on_its_own"
        in (s.state("sensor", "setup_check").attributes["issues"])
    )

    s.device.set_input(R.ROOM_TEMP, 130)  # 13.0 degC
    await clock.poll()
    assert s.state("sensor", "water_valve_pump").state == "on"
    assert s.state("sensor", "compressor_status").state == "off"
    assert s.state("binary_sensor", "automatic_heating").attributes["heating"]
    climate = s.state("climate", CLIMATE)
    assert climate.state == "auto"
    assert climate.attributes["hvac_action"] == "heating"

    # Off has to switch the unit off: nothing else stops its own heating.
    s.device.clear_write_log()
    await set_hvac_mode(s, clock, "off")
    assert (R.BMS_ON, 0) in [(w.address, w.value) for w in s.device.write_log]
    assert s.state("sensor", "water_valve_pump").state == "off"
    assert s.state("binary_sensor", "automatic_heating").state == "off"


async def test_lowered_winter_setpoint_ends_the_own_heating_issue(setup, clock):
    s = setup
    # Done at the unit: PH09 first (it clamps SEtH), then SEtH to 5 degC.
    s.device.set_holding(R.PH09_WINTER_SETPOINT_MIN, 50)
    s.device.set_holding(R.WINTER_SETPOINT, 50)
    await clock.poll()
    assert (
        "unit_heats_on_its_own"
        not in (s.state("sensor", "setup_check").attributes["issues"])
    )


async def test_target_temperature_range_follows_the_season(setup, clock):
    """SEtH is clamped to PH09..PH10 (factory 14 degC both)."""
    s = setup
    climate = s.state("climate", CLIMATE).attributes
    assert (climate["min_temp"], climate["max_temp"]) == (15.0, 35.0)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    climate = s.state("climate", CLIMATE).attributes
    assert (climate["min_temp"], climate["max_temp"]) == (14.0, 14.0)
    assert climate["temperature"] == 14.0
