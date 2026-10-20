"""Device failures as seen in real Home Assistant."""

from __future__ import annotations

import pytest

from .conftest import POLL
from .ha_client import ServiceError

CLIMATE = "hrds_climate"
DEU, BMS_ON, HB04, WATER, ROOM_HUMIDITY = 1140, 1105, 1825, 501, 505


def _start_drying(entry) -> None:
    entry.allow_operation()
    entry.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    entry.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})


def test_offline_unavailable_then_recovers(hl):
    hl.sim.call("/offline")
    try:
        for key in ("unit_status", CLIMATE, "hrds_supply_fan", "water_temperature"):
            hl.assert_state(key, "unavailable")
    finally:
        hl.sim.call("/online")
    hl.assert_state("unit_status", "off_by_bms")
    hl.assert_state(CLIMATE, "off")


def test_late_answers_never_show_wrong_values(hl):
    hl.sim.fault(delay=3.5)  # past the client's 3 s timeout
    try:
        hl.assert_state("unit_status", "unavailable", timeout=60)
    finally:
        hl.sim.fault(delay=0)
    hl.assert_state("unit_status", "off_by_bms", timeout=60)


def test_one_bad_address_keeps_the_rest(hl):
    hl.sim.fault(illegal_addresses=[ROOM_HUMIDITY])
    hl.sim.call("/set", {"input": {str(WATER): 214}})
    try:
        hl.assert_state("water_temperature", "21.4")
        hl.assert_state("unit_status", "off_by_bms")
    finally:
        hl.sim.fault(illegal_addresses=[])


def test_rejected_write_is_an_error_and_unit_stays_off(hl):
    hl.allow_operation()
    hl.sim.fault(reject_writes=[DEU])
    try:
        with pytest.raises(ServiceError) as err:
            hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
        assert err.value.code == "home_assistant_error"
        assert hl.sim.holding(BMS_ON) == 0
    finally:
        hl.sim.fault(reject_writes=[])


@pytest.mark.parametrize(
    ("alarm", "key"),
    [
        ("AL11", "alarm_compressor_lowpressure"),
        ("AL12", "alarm_compressor_highpressure"),
    ],
)
def test_compressor_alarm(hl, alarm, key):
    _start_drying(hl)
    hl.sim.call("/alarm", {"code": alarm})
    hl.assert_state(key, "on")
    hl.assert_state("alarm_active", "on")
    hl.assert_state("compressor_status", "alarm")
    hl.sim.call("/alarm", {"code": alarm, "active": False})
    hl.assert_state(key, "off")
    hl.assert_state("compressor_status", "on")


def test_filter_alarm(hl):
    hl.sim.call("/alarm", {"code": "AL22"})
    hl.assert_state("alarm_dirty_filter", "on")


def test_invalid_season_setting_al25(hl):
    _start_drying(hl)
    hl.sim.call("/set", {"holding": {str(HB04): 7}})
    hl.assert_state("alarm_active", "on")
    hl.assert_state("compressor_status", "off")
    hl.assert_state("season", "unknown")


def test_water_circuit_checks(hl):
    _start_drying(hl)
    hl.sim.fault(pump_fault=True)
    hl.assert_state(
        "water_check",
        "attention",
        {"issues": ["pump_off_while_compressor_runs"]},
    )
    hl.sim.fault(pump_fault=False, water_temperature=35.0)
    hl.assert_state(
        "water_check", lambda s: "water_too_warm" in s["attributes"]["issues"]
    )
    hl.sim.fault(water_temperature=18.0)
    hl.sim.call("/alarm", {"code": "AL16"})
    hl.assert_state(
        "water_check", lambda s: "antifreeze_alarm" in s["attributes"]["issues"]
    )
    hl.sim.call("/alarm", {"code": "AL16", "active": False})
    hl.assert_state("water_check", "ok", timeout=POLL)
