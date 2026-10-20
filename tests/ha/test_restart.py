"""The restart contract, as far as the integration's own code decides it.

"Restart" here is unloading the config entry and setting it up again: new hub,
new entities, same registries. That proves what the code does on a fresh start
given the state of the unit. That the state really comes back from disk after
a real Home Assistant boot is tests/e2e/test_restart.py. See tests/CLAUDE.md
for the contract these tests check:

1. what the user configured is still in force (options, gate, registry edits)
2. nothing the unit is doing is disturbed
3. the unit not being reachable at boot does not matter
4. a unit that lost its settings gets them back
5. derived state comes back identical
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.innova_hrds.const import DOMAIN
from tests.sim import registers as R

from .conftest import CLIMATE, Clock, Setup, add_entry, allow_operation, set_hvac_mode

REQUIRED_SETTINGS = {
    R.PH02_ONOFF_BMS,
    R.PH27_INT_BMS,
    R.PH28_DEU_BMS,
    R.PH01_ONOFF_DISPLAY,
    R.HA00_PROBE_SOURCE,
}
OPERATIONAL_REGISTERS = {R.BMS_ON, R.INT_REQUEST, R.DEU_REQUEST, R.FAN_MANUAL}


async def restart(
    hass: HomeAssistant, s: Setup, restore: dict[str, str] | None = None
) -> None:
    """Unload and set up the entry again.

    ``restore`` is what Home Assistant would hand back from its last-state
    storage ({entity_id: state}); it has to be put in place between unload and
    setup, like a real restart does.
    """
    assert await hass.config_entries.async_unload(s.entry.entry_id)
    await hass.async_block_till_done()
    if restore:
        mock_restore_cache(hass, [State(k, v) for k, v in restore.items()])
    await hass.config_entries.async_setup(s.entry.entry_id)
    await hass.async_block_till_done()


def entity_states(hass: HomeAssistant, s: Setup) -> dict[str, str]:
    registry = er.async_get(hass)
    return {
        entry.unique_id: hass.states.get(entry.entity_id).state
        for entry in er.async_entries_for_config_entry(registry, s.entry.entry_id)
        if hass.states.get(entry.entity_id) is not None
    }


# ---- 2. nothing the unit is doing is disturbed ------------------------------
async def test_restart_leaves_a_running_unit_alone(hass, setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    s.device.clear_write_log()

    await restart(hass, s)

    written = {w.address for w in s.device.write_log}
    assert written == REQUIRED_SETTINGS, "only the required settings, nothing else"
    assert not written & OPERATIONAL_REGISTERS
    assert s.device.input[R.UNIT_STATUS] == 5
    assert s.device.input[R.COMPRESSOR_STATUS] == 4
    climate = s.state("climate", CLIMATE)
    assert climate.state == "dry"
    assert climate.attributes["hvac_action"] == "drying"


async def test_restart_keeps_season_and_fan_setpoint(hass, setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await s.service("fan", "set_percentage", "hrds_supply_fan", percentage=40)
    await clock.settle()
    season, fan = s.device.holding[R.HB04_SEASON], s.device.holding[R.FAN_MANUAL]

    await restart(hass, s)

    assert s.device.holding[R.HB04_SEASON] == season == R.SEASON_WINTER
    assert s.device.holding[R.FAN_MANUAL] == fan == 4000
    assert s.state("select", "season").state == "winter"


# ---- 4. a unit that lost its settings gets them back -------------------------
async def test_restart_together_with_a_unit_power_cycle(hass, setup, clock):
    s = setup
    await allow_operation(s)
    await hass.config_entries.async_unload(s.entry.entry_id)
    await hass.async_block_till_done()
    s.device.power_cycle()
    assert s.device.input[R.UNIT_STATUS] == 0  # back to off_by_display
    s.device.clear_write_log()

    await hass.config_entries.async_setup(s.entry.entry_id)
    await hass.async_block_till_done()

    assert {w.address for w in s.device.write_log} == REQUIRED_SETTINGS
    assert s.state("sensor", "unit_status").state == "off_by_bms"
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "drying"


# ---- 3. the unit not being reachable at boot does not matter -----------------
async def test_boot_before_the_unit_is_reachable(hass, setup, clock):
    s = setup
    await hass.config_entries.async_unload(s.entry.entry_id)
    await hass.async_block_till_done()
    await s.sim.stop()

    await hass.config_entries.async_setup(s.entry.entry_id)
    await hass.async_block_till_done()
    assert s.entry.state is ConfigEntryState.SETUP_RETRY

    await s.sim.start()
    await clock.advance(120)  # past HA's retry back-off, no human involved

    assert s.entry.state is ConfigEntryState.LOADED
    assert s.state("sensor", "unit_status").state == "off_by_bms"
    assert s.state("climate", CLIMATE).state == "off"


# ---- 1. what the user configured is still in force ---------------------------
async def test_gate_defaults_off_and_is_restored(hass, sim):
    s = await add_entry(hass, sim)
    entity_id = s.entity_id("switch", "operation_allowed")
    assert s.state("switch", "operation_allowed").state == "off"
    assert s.entry.runtime_data.operation_allowed is False
    assert await hass.config_entries.async_unload(s.entry.entry_id)

    mock_restore_cache(hass, [State(entity_id, "on")])
    await hass.config_entries.async_setup(s.entry.entry_id)
    await hass.async_block_till_done()
    assert s.state("switch", "operation_allowed").state == "on"
    assert s.entry.runtime_data.operation_allowed is True

    assert await hass.config_entries.async_unload(s.entry.entry_id)
    mock_restore_cache(hass, [State(entity_id, "off")])
    await hass.config_entries.async_setup(s.entry.entry_id)
    await hass.async_block_till_done()
    assert s.state("switch", "operation_allowed").state == "off"
    assert s.entry.runtime_data.operation_allowed is False
    await hass.config_entries.async_unload(s.entry.entry_id)


async def test_restored_gate_allows_requests_straight_away(hass, sim, clock):
    s = await add_entry(hass, sim)
    entity_id = s.entity_id("switch", "operation_allowed")
    assert await hass.config_entries.async_unload(s.entry.entry_id)
    mock_restore_cache(hass, [State(entity_id, "on")])
    await hass.config_entries.async_setup(s.entry.entry_id)
    await hass.async_block_till_done()

    await set_hvac_mode(s, clock, "dry")  # no allow_operation() needed

    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "drying"
    await hass.config_entries.async_unload(s.entry.entry_id)


@pytest.mark.parametrize(
    ("data", "options", "brine_entity", "winter_heating"),
    [
        # Options replace the answers given in the config flow as a whole ...
        (
            {"water_circuit": "heating_cooling"},
            {"water_circuit": "brine", "brine_temperature_entity": "sensor.brine"},
            "sensor.brine",
            False,
        ),
        # ... so a brine sensor cleared in the options form stays cleared.
        (
            {"water_circuit": "brine", "brine_temperature_entity": "sensor.brine"},
            {"water_circuit": "brine"},
            None,
            False,
        ),
        (
            {"water_circuit": "heating_cooling"},
            {"water_circuit": "heating_cooling", "allow_winter_heating": True},
            None,
            True,
        ),
    ],
    ids=["brine-set-in-options", "brine-cleared-in-options", "winter-heating"],
)
async def test_options_are_authoritative_after_restart(
    hass, sim, data, options, brine_entity, winter_heating
):
    s = await add_entry(hass, sim, **data)
    hass.config_entries.async_update_entry(s.entry, options=options)
    await hass.async_block_till_done()  # the update listener reloads the entry

    await restart(hass, s)

    hub = s.entry.runtime_data
    assert hub.brine_entity == brine_entity
    assert hub.allow_winter_heating is winter_heating
    assert hub.water_circuit == options["water_circuit"]
    await hass.config_entries.async_unload(s.entry.entry_id)


async def test_user_registry_changes_are_kept(hass, setup, clock):
    s = setup
    registry = er.async_get(hass)
    renamed = s.entity_id("sensor", "unit_status")
    registry.async_update_entity(renamed, name="Unit state (mine)")
    disabled = next(
        entry
        for entry in er.async_entries_for_config_entry(registry, s.entry.entry_id)
        if entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    )
    assert hass.states.get(disabled.entity_id) is None
    registry.async_update_entity(disabled.entity_id, disabled_by=None)
    await clock.advance(60)  # HA reloads the entry after an entity is enabled
    assert hass.states.get(disabled.entity_id) is not None
    ids_before = {
        e.entity_id for e in registry.entities.values() if e.platform == DOMAIN
    }

    await restart(hass, s)

    assert registry.async_get(renamed).name == "Unit state (mine)"
    assert registry.async_get(disabled.entity_id).disabled_by is None
    assert hass.states.get(disabled.entity_id) is not None
    assert {
        e.entity_id for e in registry.entities.values() if e.platform == DOMAIN
    } == (ids_before)


# ---- 5. derived state comes back identical -----------------------------------
@pytest.mark.parametrize(
    ("sim_options", "entry_options"),
    [
        ({}, {}),
        (
            {"overlays": ("display_with_probes",)},
            {"has_display": True},
        ),
    ],
    ids=["headless", "display"],
)
async def test_every_entity_comes_back_identical(hass, setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    await clock.poll()
    before = entity_states(hass, s)
    issues_before = s.state("sensor", "setup_check").attributes["issues"]
    modes_before = s.state("climate", CLIMATE).attributes["hvac_modes"]
    assert len(before) > 100

    # The gate is restored from the last state like Home Assistant does it.
    gate = s.entity_id("switch", "operation_allowed")
    await restart(hass, s, restore={gate: "on"})
    await Clock(hass).poll()

    assert entity_states(hass, s) == before
    assert s.state("sensor", "setup_check").attributes["issues"] == issues_before
    assert s.state("climate", CLIMATE).attributes["hvac_modes"] == modes_before
