"""A request the unit mirrors into its register late (seen on a real unit).

Writing OFF to the on/off request worked, but the register read back ON for
several polls, so the switch flicked back. The request switches now show the
command until the read-back agrees, re-reading just that register meanwhile.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryState

from tests.sim import registers as R

from .conftest import allow_operation


async def _unit_on(s, clock) -> None:
    await allow_operation(s)
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    assert s.state("switch", "unit_on_off").state == "on"
    assert s.state("sensor", "unit_status").state == "on"


async def test_switch_follows_the_command_while_the_unit_lags(setup, clock, caplog):
    s = setup
    await _unit_on(s, clock)
    s.device.lag_reads = {R.BMS_ON: 3}

    await s.service("switch", "turn_off", "unit_on_off")
    assert s.state("switch", "unit_on_off").state == "off"  # at once

    await clock.settle()  # the post-write poll still reads the old value
    assert s.device.holding[R.BMS_ON] == 1
    assert s.state("switch", "unit_on_off").state == "off"

    await clock.advance(30)  # the re-reads of that one register
    assert s.device.holding[R.BMS_ON] == 0
    assert s.state("switch", "unit_on_off").state == "off"
    assert s.state("sensor", "unit_status").state == "off_by_bms"
    assert "did not confirm" not in caplog.text


async def test_unconfirmed_request_falls_back_to_the_units_value(setup, clock, caplog):
    s = setup
    await _unit_on(s, clock)
    s.device.lag_reads = {R.BMS_ON: 1000}

    with caplog.at_level(logging.WARNING):
        await s.service("switch", "turn_off", "unit_on_off")
        await clock.settle()
        assert s.state("switch", "unit_on_off").state == "off"
        await clock.advance(30)

    assert "did not confirm unit_on_off=off" in caplog.text
    assert s.state("switch", "unit_on_off").state == "on"


async def test_fan_is_not_pending_but_enables_are(setup, clock):
    s = setup
    await allow_operation(s)
    await clock.settle()
    hub = s.entry.runtime_data
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=55)
    assert hub._pending == {}
    # What may be requested follows an enable at once, before the read-back.
    await s.service("switch", "turn_off", "enable_onoff_bms")
    assert set(hub._pending) == {"enable_onoff_bms"}
    await clock.settle()


async def test_unload_drops_a_pending_request(hass, setup, clock):
    s = setup
    await allow_operation(s)
    s.device.lag_reads = {R.BMS_ON: 1000}
    hub = s.entry.runtime_data
    await s.service("switch", "turn_on", "unit_on_off")
    assert hub._pending and hub._verify_handles

    assert await hass.config_entries.async_unload(s.entry.entry_id)
    await hass.async_block_till_done()

    assert s.entry.state is ConfigEntryState.NOT_LOADED
    assert hub._pending == {}
    assert hub._verify_handles == []
