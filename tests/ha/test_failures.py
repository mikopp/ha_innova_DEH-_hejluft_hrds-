"""Device and transport failures: what the user sees in Home Assistant."""

from __future__ import annotations

import time

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError

from tests.sim import registers as R

from .conftest import CLIMATE, allow_operation, set_hvac_mode


async def test_offline_goes_unavailable_and_recovers(setup, clock):
    s = setup
    await s.sim.stop()
    await clock.poll()
    for platform, key in (
        ("sensor", "unit_status"),
        ("sensor", "water_temperature"),
        ("climate", CLIMATE),
        ("fan", "hrds_supply_fan"),
        ("sensor", "supply_fan_airflow"),
    ):
        assert s.state(platform, key).state == STATE_UNAVAILABLE, key
    await s.sim.start()
    await clock.poll()
    assert s.state("sensor", "unit_status").state == "off_by_bms"
    assert s.state("climate", CLIMATE).state == "off"


async def test_unanswered_requests_time_out(setup, clock):
    """A gateway that accepts the connection but answers too late.

    pymodbus hands a late answer to the *next* request; the hub must not decode
    one block's registers as another's (that showed e.g. off_by_display for a
    running unit). Unavailable is right, a wrong value is not.
    """
    s = setup
    s.sim.delay = 3.5  # past the client's 3 s timeout
    started = time.monotonic()
    await clock.poll()
    assert s.state("sensor", "unit_status").state == STATE_UNAVAILABLE
    assert time.monotonic() - started < 60, "a dead link must fail fast"
    s.sim.delay = 0
    await clock.poll()
    assert s.state("sensor", "unit_status").state == "off_by_bms"


async def test_one_bad_address_does_not_blank_the_block(setup, clock):
    s = setup
    s.sim.illegal_addresses = {R.ROOM_HUMIDITY}  # inside the 499+13 block
    s.device.set_water_temperature(21.4)
    await clock.poll()
    assert float(s.state("sensor", "water_temperature").state) == 21.4
    assert s.state("sensor", "unit_status").state == "off_by_bms"


async def test_rejected_write_raises(setup, clock):
    s = setup
    await allow_operation(s)
    s.sim.reject_writes = {R.DEU_REQUEST}
    with pytest.raises(HomeAssistantError, match="Modbus write to dehumidify"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    assert s.device.holding[R.BMS_ON] == 0, "unit must not start after a failed request"


@pytest.mark.parametrize(
    ("alarm", "key"),
    [
        ("AL11", "alarm_compressor_lowpressure"),
        ("AL12", "alarm_compressor_highpressure"),
    ],
)
async def test_compressor_alarms(setup, clock, alarm, key):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "drying"
    s.device.raise_alarm(alarm)
    await clock.poll()
    assert s.state("binary_sensor", key).state == "on"
    assert s.state("binary_sensor", "alarm_active").state == "on"
    assert s.state("sensor", "compressor_status").state == "alarm"
    # The request is still latched, so the unit reports drying without the
    # compressor; the alarm is visible on its own entities.
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "drying"
    s.device.clear_alarm(alarm)
    await clock.poll()
    assert s.state("binary_sensor", key).state == "off"
    assert s.state("sensor", "compressor_status").state == "on"


async def test_dirty_filter_alarm(setup, clock):
    s = setup
    s.device.raise_alarm("AL22")
    await clock.poll()
    assert s.state("binary_sensor", "alarm_dirty_filter").state == "on"


async def test_invalid_season_config_raises_al25(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    s.device.set_holding(R.HB04_SEASON, 7)  # someone mis-set HB04 on the unit
    await clock.poll()
    assert s.state("binary_sensor", "alarm_active").state == "on"
    assert s.state("sensor", "compressor_status").state == "off"
    assert s.state("select", "season").state == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("alarm", "attr"), [("AL28", "current_temperature"), ("AL34", "current_humidity")]
)
@pytest.mark.parametrize("sim_options", [{"overlays": ("display_with_probes",)}])
@pytest.mark.parametrize("entry_options", [{"has_display": True}])
async def test_probe_alarm_blanks_climate_reading(setup, clock, alarm, attr):
    s = setup
    assert s.state("climate", CLIMATE).attributes[attr] is not None
    s.device.raise_alarm(alarm)
    await clock.poll()
    # HA drops current_humidity from the attributes when it is None.
    assert s.state("climate", CLIMATE).attributes.get(attr) is None


@pytest.mark.parametrize("sim_options", [{"overlays": ("display_with_probes",)}])
@pytest.mark.parametrize("entry_options", [{"has_display": True}])
async def test_unplugged_probe_is_unknown_not_stale(setup, clock):
    s = setup
    assert float(s.state("sensor", "room_temperature").state) == 22.5
    s.device.unplug_probe(R.ROOM_TEMP)
    await clock.poll()
    assert s.state("sensor", "room_temperature").state == STATE_UNKNOWN
    assert s.state("climate", CLIMATE).attributes["current_temperature"] is None
    assert s.state("binary_sensor", "temp_probe_ok").state == "off"  # AL28 raised


async def test_water_circuit_problems(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert s.state("sensor", "water_check").state == "ok"

    s.device.set_pump_fault(True)
    await clock.poll()
    issues = s.state("sensor", "water_check").attributes["issues"]
    assert issues == ["pump_off_while_compressor_runs"]
    s.device.set_pump_fault(False)

    s.device.set_water_temperature(35.0)  # above PC07 = 30 degC
    await clock.poll()
    assert "water_too_warm" in s.state("sensor", "water_check").attributes["issues"]
    s.device.set_water_temperature(18.0)

    for alarm, issue in (
        ("AL03", "high_water_temperature_alarm"),
        ("AL04", "low_water_temperature_alarm"),
        ("AL16", "antifreeze_alarm"),
    ):
        s.device.raise_alarm(alarm)
        await clock.poll()
        assert issue in s.state("sensor", "water_check").attributes["issues"]
        s.device.clear_alarm(alarm)
    await clock.poll()
    assert s.state("sensor", "water_check").state == "ok"
