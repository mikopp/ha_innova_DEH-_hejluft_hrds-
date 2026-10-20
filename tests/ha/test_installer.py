"""The installer device: opt-in, and its registers stay out of the poll."""

from __future__ import annotations

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.innova_hrds.const import (
    DOMAIN,
    ENTITIES_DICT,
    INSTALLER_DEVICE_SUFFIX,
    INSTALLER_KEYS,
    INSTALLER_LOGIC_KEYS,
)
from tests.sim import registers as R

from .conftest import Setup, add_entry

INSTALLER_ADDRS = {ENTITIES_DICT[k]["REG"] for k in INSTALLER_KEYS}
LOGIC_ADDRS = {ENTITIES_DICT[k]["REG"] for k in INSTALLER_LOGIC_KEYS}
PA03 = 1719  # hours alarm relay, a plain writable installer number


def holding_addresses_read(s: Setup) -> set[int]:
    """Every holding address any request since the last clear has covered."""
    return {
        a
        for kind, start, count in s.sim.read_log
        if kind == "holding"
        for a in range(start, start + count)
    }


def installer_device(s: Setup):
    return dr.async_get(s.hass).async_get_device_by_identifier(
        (DOMAIN, s.entry.entry_id + INSTALLER_DEVICE_SUFFIX), s.entry.entry_id
    )


async def set_installer_option(s: Setup, on: bool) -> None:
    hass = s.hass
    result = await hass.config_entries.options.async_init(s.entry.entry_id)
    schema = {str(k): k for k in result["data_schema"].schema}
    data = {
        key: marker.default() if callable(marker.default) else marker.default
        for key, marker in schema.items()
        if hasattr(marker, "default") and callable(marker.default)
    }
    data["installer_device"] = on
    result = await hass.config_entries.options.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_off_by_default_and_not_offered_at_first_install(hass, sim):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert "installer_device" not in {str(k) for k in result["data_schema"].schema}

    s = await add_entry(hass, sim)
    assert installer_device(s) is None
    registry = er.async_get(hass)
    keys = {
        e.unique_id.removeprefix(f"{s.entry.entry_id}-")
        for e in er.async_entries_for_config_entry(registry, s.entry.entry_id)
    }
    assert not keys & (INSTALLER_KEYS | {"refresh_installer", "installer_last_read"})
    # Only the water-check limits were read, once, at setup.
    assert holding_addresses_read(s) & INSTALLER_ADDRS == LOGIC_ADDRS
    assert s.entry.runtime_data.data["inst_pc07"] == 30.0


async def test_regular_poll_never_reads_installer_registers(hass, sim, clock):
    s = await add_entry(hass, sim, installer_device=True)
    s.sim.read_log.clear()
    await clock.poll()
    await clock.poll()
    assert s.sim.read_log, "the poll ran"
    assert not holding_addresses_read(s) & INSTALLER_ADDRS


async def test_values_come_from_setup_and_the_refresh_button(hass, sim, clock):
    s = await add_entry(hass, sim, installer_device=True)
    assert installer_device(s) is not None
    # Read once at setup (that is also what turning the option on does).
    assert float(s.state("number", "inst_pa03").state) == s.device.holding[PA03]
    assert s.state("sensor", "installer_last_read").state != STATE_UNKNOWN
    first = s.entry.runtime_data.data["installer_last_read"]

    s.device.set_holding(PA03, 2)  # changed on the unit
    await clock.poll()
    assert float(s.state("number", "inst_pa03").state) != 2, "not polled"

    await s.service("button", "press", "refresh_installer")
    assert float(s.state("number", "inst_pa03").state) == 2
    assert s.entry.runtime_data.data["installer_last_read"] > first


async def test_write_reads_back_only_that_register(hass, sim, clock):
    s = await add_entry(hass, sim, installer_device=True)
    s.sim.read_log.clear()
    await s.service("number", "set_value", "inst_pa03", value=1)
    assert s.device.holding[PA03] == 1
    assert float(s.state("number", "inst_pa03").state) == 1
    assert holding_addresses_read(s) == {PA03}


async def test_turning_the_option_on_and_off(hass, sim):
    s = await add_entry(hass, sim)
    assert installer_device(s) is None

    s.sim.read_log.clear()
    await set_installer_option(s, True)
    assert installer_device(s) is not None
    # Turning it on reads the installer menu straight away.
    assert INSTALLER_ADDRS <= holding_addresses_read(s)
    assert s.state("number", "inst_pa03").state != STATE_UNKNOWN
    assert s.state("sensor", "installer_last_read").state != STATE_UNKNOWN

    await set_installer_option(s, False)
    assert installer_device(s) is None
    assert s.entity_id("number", "inst_pa03") is None
    assert s.entity_id("button", "refresh_installer") is None


@pytest.mark.parametrize("entry_options", [{"installer_device": True}])
async def test_failed_refresh_raises(setup, clock):
    s = setup
    await s.sim.stop()
    with pytest.raises(Exception, match="installer parameters"):
        await s.service("button", "press", "refresh_installer")
    await s.sim.start()


async def test_water_check_uses_pc07_without_the_installer_device(hass, sim, clock):
    s = await add_entry(hass, sim)
    assert s.device.holding[R.PC07_MAX_WATER] == 300  # 30.0 degC, read at setup
    assert s.entry.runtime_data.data["inst_pc07"] == 30.0
