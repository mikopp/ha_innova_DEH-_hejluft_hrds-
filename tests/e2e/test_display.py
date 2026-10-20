"""Unit with display and room probes in real Home Assistant."""

from __future__ import annotations

import pytest

CLIMATE = "hrds_climate"
PH01, HA00, ROOM_TEMP = 1777, 1803, 499
SUMMER_SP, WINTER_SP, HUM_SP = 1584, 1585, 1586


def test_display_settings_never_written(disp, headless):
    # Across the reset and the re-assert polls, nothing touched PH01/HA00.
    written = {addr for addr, _value in disp.sim.writes()}
    assert PH01 not in written and HA00 not in written
    assert disp.sim.holding(PH01) == 1
    # The headless entry on the other simulator did write them.
    assert headless.sim.holding(PH01) == 0


def test_room_readings(disp):
    disp.assert_state("room_temperature", "22.5")
    disp.assert_state("room_humidity", "55.0")
    disp.assert_state(
        CLIMATE, "off", {"current_temperature": 22.5, "current_humidity": 55}
    )


def test_display_off_is_reported(disp):
    disp.sim.fault(display_on=False)
    disp.assert_state("unit_status", "off_by_display")
    disp.assert_state(
        "setup_check", lambda s: "unit_off_by_display" in s["attributes"]["issues"]
    )
    disp.sim.fault(display_on=True)
    disp.assert_state("unit_status", "off_by_bms")


def test_setpoints_per_season(disp):
    for key in ("summer_setpoint", "winter_setpoint", "humidity_setpoint"):
        assert disp.has(key), key
    disp.assert_state(CLIMATE, "off", {"temperature": 28.0})
    disp.service("climate", "set_temperature", CLIMATE, temperature=26.5)
    disp.sim.wait_for(lambda s: s["holding"][str(SUMMER_SP)] == 265, timeout=10)
    disp.assert_state(CLIMATE, "off", {"temperature": 26.5})

    disp.service("select", "select_option", "season", option="winter")
    disp.assert_state(CLIMATE, "off", {"temperature": 14.0})
    disp.service("climate", "set_temperature", CLIMATE, temperature=18)
    disp.sim.wait_for(lambda s: s["holding"][str(WINTER_SP)] == 180, timeout=10)
    disp.service("select", "select_option", "season", option="summer")
    disp.assert_state("season", "summer")


def test_humidity_clamped_by_unit(disp):
    disp.assert_state(CLIMATE, "off", {"min_humidity": 55, "max_humidity": 65})
    disp.service("climate", "set_humidity", CLIMATE, humidity=62)
    disp.sim.wait_for(lambda s: s["holding"][str(HUM_SP)] == 62, timeout=10)
    disp.service("number", "set_value", "humidity_setpoint", value=80)
    disp.sim.wait_for(lambda s: s["holding"][str(HUM_SP)] == 65, timeout=10)
    disp.assert_state("humidity_setpoint", "65.0")


@pytest.mark.parametrize(("mode", "action"), [("dry", "drying"), ("cool", "cooling")])
def test_operation_and_display_off_wins(disp, mode, action):
    disp.allow_operation()
    disp.service("climate", "set_hvac_mode", CLIMATE, hvac_mode=mode)
    disp.assert_state(CLIMATE, mode, {"hvac_action": action})
    disp.sim.fault(display_on=False)
    disp.assert_state(CLIMATE, lambda s: s["attributes"]["hvac_action"] == "off")
    disp.sim.fault(display_on=True)
    disp.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")


def test_probe_fault_blanks_reading(disp):
    disp.sim.call("/probe", {"address": ROOM_TEMP, "unplug": True})
    disp.assert_state("room_temperature", "unknown")
    disp.assert_state("temp_probe_ok", "off")
    disp.assert_state(CLIMATE, lambda s: s["attributes"]["current_temperature"] is None)
    disp.sim.call("/alarm", {"code": "AL34"})
    disp.assert_state(
        CLIMATE, lambda s: s["attributes"].get("current_humidity") is None
    )
