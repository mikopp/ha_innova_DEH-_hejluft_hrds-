"""Device and transport failures: what the user sees in Home Assistant."""

from __future__ import annotations

import time

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError

from tests.sim import registers as R

from .conftest import CLIMATE, add_entry, allow_operation, set_hvac_mode


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


async def test_a_register_that_stops_answering_goes_unavailable(setup, clock):
    """No stale reading: the entity must not keep its last value forever."""
    s = setup
    s.device.set_water_temperature(21.4)
    await clock.poll()
    assert float(s.state("sensor", "water_temperature").state) == 21.4

    s.sim.illegal_addresses = {R.WATER_TEMP}
    s.device.set_water_temperature(30.0)  # would show if the old value were kept
    await clock.poll()
    assert s.state("sensor", "water_temperature").state == STATE_UNAVAILABLE
    assert s.state("sensor", "unit_status").state == "off_by_bms", "rest is intact"

    s.sim.illegal_addresses = set()
    await clock.poll()
    assert float(s.state("sensor", "water_temperature").state) == 30.0


async def test_rejected_write_raises(setup, clock):
    s = setup
    await allow_operation(s)
    s.sim.reject_writes = {R.DEU_REQUEST}
    with pytest.raises(HomeAssistantError, match="Modbus write to dehumidify"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    assert s.device.holding[R.BMS_ON] == 0, "unit must not start after a failed request"


async def test_off_switches_the_unit_off_when_a_request_cannot_be_cleared(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    s.sim.reject_writes = {R.DEU_REQUEST}
    with pytest.raises(HomeAssistantError, match="Modbus write to dehumidify"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    # The request is still latched: only switching the unit off stops it.
    assert s.device.holding[R.DEU_REQUEST] == 1
    assert s.device.holding[R.BMS_ON] == 0


async def test_off_reports_the_request_failure_when_the_unit_off_fails_too(
    setup, clock
):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    s.sim.reject_writes = {R.DEU_REQUEST, R.BMS_ON}
    with pytest.raises(HomeAssistantError, match="Modbus write to dehumidify"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")


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


async def test_gateway_that_drops_large_reads(hass, sim, clock, caplog):
    """A unit/gateway that never answers reads above a few registers.

    This is what a real HRDS+ behind an RS-485 gateway did with 120-register
    reads: no reply at all, so the entry never loaded. The hub must find a
    size that works, keep it, and not pay the timeout on every poll.
    """
    sim.max_count = 4
    s = await add_entry(hass, sim)
    assert s.entry.state is ConfigEntryState.LOADED
    assert s.state("sensor", "unit_status").state == "off_by_bms"
    assert "reading at most" in caplog.text

    sim.oversized_reads = 0
    sim.read_log.clear()
    started = time.monotonic()
    await clock.poll()
    assert sim.oversized_reads == 0, "the smaller block size is kept"
    assert max(count for _kind, _addr, count in sim.read_log) <= 4
    assert time.monotonic() - started < 3, "no timeout on later polls"
    assert s.state("sensor", "unit_status").state == "off_by_bms"
    await hass.config_entries.async_unload(s.entry.entry_id)


async def test_dead_link_is_not_mistaken_for_a_size_limit(setup, clock):
    """No answer at all: fail the poll fast instead of shrinking the blocks."""
    s = setup
    hub = s.entry.runtime_data
    block = hub._max_block
    s.sim.delay = 3.5
    await clock.poll()
    assert s.state("sensor", "unit_status").state == STATE_UNAVAILABLE
    assert hub._max_block == block
