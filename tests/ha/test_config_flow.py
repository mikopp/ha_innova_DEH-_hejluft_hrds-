"""Config flow, options flow and setup outcomes against the simulator."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr

from custom_components.innova_hrds.const import DOMAIN
from tests.sim import registers as R
from tests.sim.server import free_port

from .conftest import add_entry, entry_data


async def _submit(hass: HomeAssistant, data: dict):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def test_user_flow_creates_entry(hass, sim):
    result = await _submit(hass, entry_data(sim))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == sim.host
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device.model_id == "EPB9ORSINDEU"
    assert device.sw_version == "V01.00.09.02"


async def test_setup_and_installer_devices_hang_off_the_main_device(hass, sim):
    s = await add_entry(hass, sim, installer_device=True)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), s.entry.entry_id)
    main = [d for d in devices if d.via_device_id is None]
    children = [d for d in devices if d.via_device_id is not None]
    assert len(main) == 1
    assert {d.name for d in children} == {"HRDS+ setup", "HRDS+ installer"}
    assert all(d.via_device_id == main[0].id for d in children)
    # Entities of a child device keep an id based on the config entry.
    assert s.state("sensor", "setup_check") is not None
    assert s.state("number", "inst_pa03") is not None


async def test_user_flow_cannot_connect(hass, sim):
    result = await _submit(hass, entry_data(sim, **{CONF_PORT: free_port()}))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_wrong_vendor(hass, sim):
    sim.identity_override = {0: "ACME", 1: "HEATPUMP-9", 2: "1.0"}
    sim.apply_identity()
    result = await _submit(hass, entry_data(sim))
    assert result["errors"] == {"base": "wrong_device"}


async def test_user_flow_wrong_fingerprint_without_fc43(hass, sim):
    sim.fc43 = False
    sim.apply_identity()
    sim.device.force_input(R.UNIT_STATUS, 9)  # not a documented unit status
    result = await _submit(hass, entry_data(sim))
    assert result["errors"] == {"base": "wrong_device"}


async def test_user_flow_without_fc43_uses_fingerprint(hass, sim):
    sim.fc43 = False
    sim.apply_identity()
    result = await _submit(hass, entry_data(sim))
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_rejects_duplicate_and_invalid_host(hass, sim):
    await add_entry(hass, sim)
    result = await _submit(hass, entry_data(sim))
    assert result["errors"] == {CONF_HOST: "already_configured"}
    result = await _submit(hass, entry_data(sim, **{CONF_HOST: "not a host!"}))
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_options_flow_reloads(hass, sim):
    s = await add_entry(hass, sim)
    result = await hass.config_entries.options.async_init(s.entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_HOST: sim.host,
            CONF_PORT: sim.port,
            CONF_SCAN_INTERVAL: 5,
            "hostid": 1,
            "model": "50",
            "has_display": False,
            "water_circuit": "heating_cooling",
            "allow_winter_heating": True,
            "brine_min_temperature": 10.0,
            "airflow_max_m3h": 500,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert s.entry.state is ConfigEntryState.LOADED
    hub = s.entry.runtime_data
    assert hub.allow_winter_heating is True
    assert s.state("sensor", "supply_fan_max_airflow").state == "500.0"


async def test_options_flow_reports_unreachable_device(hass, sim):
    s = await add_entry(hass, sim)
    result = await hass.config_entries.options.async_init(s.entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_HOST: sim.host,
            CONF_PORT: free_port(),
            CONF_SCAN_INTERVAL: 30,
            "hostid": 1,
            "model": "30",
            "has_display": False,
            "water_circuit": "heating_cooling",
            "allow_winter_heating": False,
            "brine_min_temperature": 10.0,
            "airflow_max_m3h": 300,
        },
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_setup_retries_while_device_offline(hass, sim):
    await sim.stop()
    s = await add_entry(hass, sim)
    assert s.entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_fails_on_wrong_device(hass, sim):
    sim.identity_override = {0: "ACME", 1: "METER", 2: ""}
    sim.apply_identity()
    s = await add_entry(hass, sim)
    assert s.entry.state is ConfigEntryState.SETUP_ERROR
    assert not s.device.write_log, "nothing may be written to a foreign device"


async def test_unload(hass, sim):
    s = await add_entry(hass, sim)
    assert await hass.config_entries.async_unload(s.entry.entry_id)
    await hass.async_block_till_done()
    assert s.entry.state is ConfigEntryState.NOT_LOADED
