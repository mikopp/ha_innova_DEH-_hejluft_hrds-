"""Headless unit in real Home Assistant: setup, both operation modes, guards."""

from __future__ import annotations

import pytest

from .conftest import POLL
from .ha_client import ServiceError

CLIMATE = "hrds_climate"

PH01, PH02, HA00, PH27, PH28 = 1777, 1778, 1803, 1869, 1870
BMS_ON, INT, DEU, HB04 = 1105, 1139, 1140, 1825


def _issues(entry) -> list[str]:
    return entry.state("setup_check")["attributes"]["issues"]


# ---- setup -------------------------------------------------------------------
def test_setup_writes_and_unit_wakes(hl):
    # The reset fixture already waited for the re-assert; check the outcome.
    sim = hl.sim.state()
    assert sim["holding"][str(PH01)] == 0
    assert sim["holding"][str(PH02)] == 1
    assert sim["holding"][str(HA00)] == 0
    assert sim["unit_status"] == 2  # off_by_bms: waiting for a Modbus on
    hl.assert_state("unit_status", "off_by_bms")
    hl.assert_state("setup_check", "attention")
    assert _issues(hl) == ["free_cooling_without_outdoor_probe"]


def test_setup_check_ok_after_fixing_issue(hl):
    hl.service("switch", "turn_off", "enable_free_cooling")
    hl.assert_state("setup_check", "ok")
    assert _issues(hl) == []
    hl.service("switch", "turn_on", "enable_free_cooling")


def test_setpoints_hidden_without_room_probe(hl):
    for key in ("summer_setpoint", "winter_setpoint", "humidity_setpoint"):
        assert not hl.has(key), key
    assert hl.state(CLIMATE)["attributes"]["current_temperature"] is None


def test_power_cycle_self_heals(hl):
    hl.sim.call("/power_cycle")
    assert hl.sim.holding(PH02) == 0
    hl.sim.wait_for(lambda s: s["holding"][str(PH02)] == 1, what="PH02 re-asserted")
    hl.sim.wait_for(lambda s: s["holding"][str(PH01)] == 0, what="PH01 re-asserted")
    hl.assert_state("unit_status", "off_by_bms")


def test_bms_switch_turned_off_is_undone(hl):
    hl.service("switch", "turn_off", "enable_onoff_bms")
    hl.sim.wait_for(lambda s: s["holding"][str(PH02)] == 0, timeout=10, what="PH02 off")
    hl.sim.wait_for(lambda s: s["holding"][str(PH02)] == 1, what="PH02 back on")
    hl.assert_state("enable_onoff_bms", "on")


# ---- operation gate ----------------------------------------------------------
def test_gate_blocks_requests(hl):
    with pytest.raises(ServiceError) as err:
        hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    assert err.value.code == "service_validation_error"
    assert all(value == 0 for _addr, value in hl.sim.writes())
    assert hl.sim.holding(DEU) == 0


# ---- dehumidify --------------------------------------------------------------
def test_dehumidify(hl):
    hl.allow_operation()
    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    writes = [w for w in hl.sim.writes() if w[0] in (BMS_ON, INT, DEU)]
    assert writes == [(INT, 0), (DEU, 1), (BMS_ON, 1)]
    hl.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})
    hl.assert_state("compressor_status", "on")
    hl.assert_state("recirculation_damper", "on")
    hl.assert_state("dehumidify_request", "on")
    hl.assert_state("water_check", "ok")

    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    hl.assert_state(CLIMATE, "off", {"hvac_action": "off"})
    hl.assert_state("compressor_status", "off")


# ---- active cooling ------------------------------------------------------------
def test_active_cooling_in_summer(hl):
    hl.allow_operation()
    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="cool")
    hl.assert_state(CLIMATE, "cool", {"hvac_action": "cooling"})
    assert (hl.sim.holding(INT), hl.sim.holding(DEU)) == (1, 1)
    hl.assert_state("water_valve_pump", "on")
    # The season cannot go to winter while integration would turn into heating.
    with pytest.raises(ServiceError):
        hl.service("select", "select_option", "season", option="winter")
    assert hl.sim.holding(HB04) == 4


def test_winter_refuses_cooling_until_heating_allowed(hl):
    hl.allow_operation()
    hl.service("select", "select_option", "season", option="winter")
    hl.assert_state("season", "winter")
    hl.assert_state(CLIMATE, lambda s: "cool" not in s["attributes"]["hvac_modes"])
    with pytest.raises(ServiceError):
        hl.service("switch", "turn_on", "active_cooling")
    assert hl.sim.holding(INT) == 0

    hl.options(allow_winter_heating=True)
    try:
        hl.allow_operation()
        hl.assert_state(CLIMATE, lambda s: "heat" in s["attributes"]["hvac_modes"])
        hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="heat")
        hl.assert_state(CLIMATE, "heat", {"hvac_action": "heating"})
        hl.assert_state("compressor_status", "off")  # heating = warm water only
        hl.assert_state("water_valve_pump", "on")
        hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    finally:
        hl.options()
        hl.allow_operation()
        hl.service("select", "select_option", "season", option="summer")
        hl.assert_state("season", "summer")


# ---- brine circuit -----------------------------------------------------------
def test_brine_guard(hl):
    ha = hl.ha
    ha.call_service(
        "input_number", "set_value", "input_number.brine_temperature", value=6
    )
    hl.options(water_circuit="brine", brine_temperature_entity="sensor.brine_supply")
    try:
        hl.allow_operation()
        hl.assert_state("brine_temperature_guard", "on")
        with pytest.raises(ServiceError) as err:
            hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
        assert "Brine temperature guard" in err.value.message
        assert hl.sim.holding(DEU) == 0

        ha.call_service(
            "input_number", "set_value", "input_number.brine_temperature", value=14
        )
        hl.assert_state("brine_temperature_guard", "off")
        hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
        hl.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})

        # Cold again: flagged, but a running request is never stopped.
        ha.call_service(
            "input_number", "set_value", "input_number.brine_temperature", value=5
        )
        hl.assert_state(
            "water_check",
            lambda s: "brine_guard_blocking" in s["attributes"]["issues"],
            timeout=POLL,
        )
        assert hl.sim.holding(DEU) == 1
        hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    finally:
        hl.options()
