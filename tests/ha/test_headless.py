"""Headless unit (no display, no room probes): setup and both operating modes."""

from __future__ import annotations

import pytest
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.innova_hrds.const import DOMAIN
from tests.sim import registers as R

from .conftest import CLIMATE, add_entry, allow_operation, set_hvac_mode

SETUP_WRITES = {
    R.PH02_ONOFF_BMS: 1,
    R.PH28_DEU_BMS: 1,
    R.PH27_INT_BMS: 1,
    R.PH01_ONOFF_DISPLAY: 0,
    R.HA00_PROBE_SOURCE: 0,
}


def _issues(s) -> list[str]:
    return s.state("sensor", "setup_check").attributes["issues"]


# ---- setup -------------------------------------------------------------------
async def test_first_connect_writes_required_settings(setup):
    s = setup
    written = {w.address: w.value for w in s.device.write_log}
    assert written == SETUP_WRITES
    assert all(w.accepted for w in s.device.write_log)
    # The unit left off_by_display and now waits for a Modbus on.
    assert s.state("sensor", "unit_status").state == "off_by_bms"


async def test_setup_check_lists_real_issues_until_fixed(setup, clock):
    s = setup
    # The factory unit has free cooling enabled but no outdoor probe.
    assert s.state("sensor", "setup_check").state == "attention"
    assert _issues(s) == ["free_cooling_without_outdoor_probe"]
    await s.service("switch", "turn_off", "enable_free_cooling")
    await clock.settle()
    assert s.device.holding[1799] == 0
    assert s.state("sensor", "setup_check").state == "ok"
    assert _issues(s) == []


async def test_headless_unit_stuck_off_by_display_says_how_to_start_it(setup, clock):
    s = setup
    s.device.latch_display_off()
    await clock.poll()
    assert s.state("sensor", "unit_status").state == "off_by_display"
    assert "unit_waiting_for_first_on" in _issues(s)
    assert any(
        "Unit on/off (Modbus)" in text
        for text in s.state("sensor", "setup_check").attributes["to_fix"]
    )
    await allow_operation(s)
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    assert s.state("sensor", "unit_status").state == "on"
    assert "unit_waiting_for_first_on" not in _issues(s)


async def test_setup_switches_say_when_to_turn_them_off(setup):
    free_cooling = setup.state("switch", "enable_free_cooling").attributes["hint"]
    assert free_cooling.startswith("Turn this OFF unless an outdoor temperature probe")
    assert "hint" in setup.state("switch", "enable_integration_bms").attributes
    # Switches without guidance carry no empty attribute.
    assert "hint" not in setup.state("switch", "enable_time_programs").attributes


async def test_setpoints_hidden_without_room_probe(setup):
    s = setup
    for key in ("summer_setpoint", "winter_setpoint", "humidity_setpoint"):
        assert s.entity_id("number", key) is None, key
    features = s.state("climate", CLIMATE).attributes["supported_features"]
    assert not features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not features & ClimateEntityFeature.TARGET_HUMIDITY
    assert s.state("climate", CLIMATE).attributes["current_temperature"] is None


async def test_power_cycle_self_heals(setup, clock):
    s = setup
    s.device.clear_write_log()
    s.device.power_cycle()
    await clock.poll()  # reads the dropped settings
    assert s.state("sensor", "setup_check").attributes["issues"]
    await clock.poll()  # re-asserts them before reading
    # Only what the power cycle changed (PH27/PH28 are already 1 from factory).
    assert {w.address: w.value for w in s.device.write_log} == {
        R.PH02_ONOFF_BMS: 1,
        R.PH01_ONOFF_DISPLAY: 0,
        R.HA00_PROBE_SOURCE: 0,
    }
    assert s.device.input[R.UNIT_STATUS] == 2
    assert "modbus_enables_pending" not in _issues(s)


async def test_bms_enable_switched_off_by_hand_is_undone(setup, clock):
    s = setup
    await s.service("switch", "turn_off", "enable_onoff_bms")
    await clock.settle()
    assert s.device.holding[R.PH02_ONOFF_BMS] == 0
    await clock.poll()
    assert s.device.holding[R.PH02_ONOFF_BMS] == 1
    assert s.state("switch", "enable_onoff_bms").state == "on"


async def test_enables_ignored_by_device_are_reported(hass, sim, clock):
    sim.device.ignore_writes = {R.PH02_ONOFF_BMS}
    s = await add_entry(hass, sim)
    await clock.poll()
    assert "modbus_enables_pending" in _issues(s)


async def test_probe_inputs_are_named_options(setup, clock):
    s = setup
    temp = s.state("select", "ai2_allocation")
    assert temp.state == "unused"
    assert temp.attributes["options"] == ["unused", "room_temperature_ntc"]
    s.device.clear_write_log()
    await s.service(
        "select", "select_option", "ai2_allocation", option="room_temperature_ntc"
    )
    await s.service(
        "select", "select_option", "ai3_allocation", option="room_humidity_0_10v"
    )
    await clock.settle()
    assert {w.address: w.value for w in s.device.write_log} == {
        R.HA02_AI2: 45,
        R.HA03_AI3: 54,
    }
    # Nothing is wired on this unit, so the setup check says so.
    assert {"room_temperature_probe_missing", "room_humidity_probe_missing"} <= set(
        _issues(s)
    )


async def test_undocumented_probe_code_is_flagged(setup, clock):
    s = setup
    s.device.holding[R.HA02_AI2] = 7
    await clock.poll()
    assert s.state("select", "ai2_allocation").state == "unknown"
    assert "probe_input_unrecognised" in _issues(s)
    assert "room_temperature_probe_missing" not in _issues(s)


async def test_old_probe_numbers_are_removed(hass, sim):
    # Up to 0.9.1 HA02/HA03 were number entities with the same unique id.
    s = await add_entry(hass, sim)
    registry = er.async_get(hass)
    for key in ("ai2_allocation", "ai3_allocation"):
        registry.async_get_or_create(
            "number", DOMAIN, f"{s.entry.entry_id}-{key}", config_entry=s.entry
        )
    await hass.config_entries.async_reload(s.entry.entry_id)
    await hass.async_block_till_done()
    for key in ("ai2_allocation", "ai3_allocation"):
        assert s.entity_id("number", key) is None, key
        assert s.entity_id("select", key) is not None, key
    await hass.config_entries.async_unload(s.entry.entry_id)
    await hass.async_block_till_done()


# ---- operation gate ----------------------------------------------------------
async def test_gate_refuses_requests_and_starts_nothing(setup):
    s = setup
    s.device.clear_write_log()
    with pytest.raises(ServiceValidationError):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    # DRY clears the integration request (a 0) before the gate refuses the
    # dehumidify request; nothing is switched on.
    assert all(w.value == 0 for w in s.device.write_log)
    assert s.device.holding[R.DEU_REQUEST] == 0
    # Switching off is always allowed: it clears both requests.
    s.device.clear_write_log()
    await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    assert [(w.address, w.value) for w in s.device.write_log] == [
        (R.INT_REQUEST, 0),
        (R.DEU_REQUEST, 0),
    ]


# ---- dehumidify --------------------------------------------------------------
async def test_dehumidify(setup, clock):
    s = setup
    await allow_operation(s)
    s.device.clear_write_log()
    await set_hvac_mode(s, clock, "dry")
    # Requests first, unit on last (the guard can refuse before anything runs).
    assert [(w.address, w.value) for w in s.device.write_log] == [
        (R.INT_REQUEST, 0),
        (R.DEU_REQUEST, 1),
        (R.BMS_ON, 1),
    ]
    climate = s.state("climate", CLIMATE)
    assert climate.state == "dry"
    assert climate.attributes["hvac_action"] == "drying"
    assert s.state("sensor", "compressor_status").state == "on"
    assert s.state("sensor", "recirculation_damper").state == "on"
    assert s.state("binary_sensor", "dehumidify_request").state == "on"
    assert s.state("sensor", "water_check").state == "ok"

    s.device.clear_write_log()
    await set_hvac_mode(s, clock, "off")
    # Off clears the requests. Without a room probe nothing else can make the
    # unit act, so it is left on: off in effect, idle.
    assert [(w.address, w.value) for w in s.device.write_log] == [
        (R.INT_REQUEST, 0),
        (R.DEU_REQUEST, 0),
    ]
    climate = s.state("climate", CLIMATE)
    assert climate.state == "off"
    assert climate.attributes["hvac_action"] == "idle"
    assert s.state("sensor", "compressor_status").state == "off"


async def test_unit_on_without_request_is_off_and_idle(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    assert s.state("sensor", "unit_status").state == "on"
    climate = s.state("climate", CLIMATE)
    # Nothing can make a sensor-less unit act: no Dry, no Auto.
    assert climate.state == "off"
    assert climate.attributes["hvac_action"] == "idle"
    assert "auto" not in climate.attributes["hvac_modes"]


async def test_auto_refused_without_room_probe(setup):
    s = setup
    await allow_operation(s)
    s.device.clear_write_log()
    with pytest.raises(ServiceValidationError, match="auto"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="auto")
    assert s.device.write_log == []


async def test_dehumidify_request_from_another_source_shows_dry(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    # E.g. the DEU digital input: the unit dries though we requested nothing.
    s.device.force_input(R.DEHUM_REQUEST, 1)
    await clock.poll()
    assert s.state("climate", CLIMATE).state == "dry"
    # Off cannot clear that request, so it switches the unit off.
    s.device.clear_write_log()
    await set_hvac_mode(s, clock, "off")
    assert (R.BMS_ON, 0) in [(w.address, w.value) for w in s.device.write_log]


# ---- active cooling (integration) --------------------------------------------
async def test_active_cooling_in_summer(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "cool")
    assert s.device.holding[R.INT_REQUEST] == 1
    assert s.device.holding[R.DEU_REQUEST] == 1
    climate = s.state("climate", CLIMATE)
    assert climate.state == "cool"
    assert climate.attributes["hvac_action"] == "cooling"
    assert s.state("sensor", "water_valve_pump").state == "on"


async def test_cooling_refused_in_winter(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    assert s.device.input[R.SEASON_READBACK] == 1
    climate = s.state("climate", CLIMATE)
    assert "cool" not in climate.attributes["hvac_modes"]
    assert "heat" not in climate.attributes["hvac_modes"]
    with pytest.raises(ServiceValidationError):
        await s.hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": s.entity_id("switch", "active_cooling")},
            blocking=True,
        )
    assert s.device.holding[R.INT_REQUEST] == 0


@pytest.mark.parametrize("entry_options", [{"allow_winter_heating": True}])
async def test_winter_heating_when_allowed(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    await set_hvac_mode(s, clock, "heat")
    climate = s.state("climate", CLIMATE)
    assert climate.state == "heat"
    assert climate.attributes["hvac_action"] == "heating"
    # Winter integration heats with water only.
    assert s.state("sensor", "compressor_status").state == "off"
    assert s.state("sensor", "water_valve_pump").state == "on"


@pytest.mark.parametrize("entry_options", [{"allow_winter_heating": True}])
async def test_heating_needs_warm_water(setup, clock):
    """Winter INT only opens valve and pump; cold water heats nothing."""
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    await set_hvac_mode(s, clock, "heat")
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "heating"
    # Below PC08 (factory 10 degC): the request stands, but nothing heats.
    s.device.set_water_temperature(8.0)
    await clock.poll()
    climate = s.state("climate", CLIMATE)
    assert climate.state == "heat"
    assert climate.attributes["hvac_action"] == "idle"
    # AL04 is the unit's own verdict: it drops the request (valve closes).
    s.device.set_water_temperature(18.0)
    s.device.raise_alarm("AL04")
    await clock.poll()
    assert s.state("sensor", "water_valve_pump").state == "off"
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "idle"


async def test_winter_int_from_elsewhere_is_not_heating(setup, clock):
    """INT set at the unit in winter, heating not allowed: no Heat anywhere."""
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    s.device.set_holding(R.INT_REQUEST, 1)  # e.g. from a display
    await clock.poll()
    assert s.state("switch", "active_cooling").state == "on"
    climate = s.state("climate", CLIMATE)
    assert "heat" not in climate.attributes["hvac_modes"]
    assert climate.state == "off"
    assert climate.attributes["hvac_action"] == "idle"


async def test_summer_int_blocked_by_al03_is_drying(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "cool")
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "cooling"
    # AL03 (water above PC07) disables active cooling; the DEU request that
    # Cool also sets keeps the compressor dehumidifying.
    s.device.raise_alarm("AL03")
    await clock.poll()
    assert s.state("sensor", "compressor_status").state == "on"
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "drying"


@pytest.mark.parametrize("entry_options", [{"allow_winter_heating": True}])
async def test_auto_season_follows_mode_status(setup, clock):
    """1583 reads auto while the unit switches season; 1110 says which."""
    s = setup
    s.device.force_input(R.SEASON_READBACK, 2)
    s.device.force_input(R.MODE_STATUS, 3)  # winter_auto
    await clock.poll()
    modes = s.state("climate", CLIMATE).attributes["hvac_modes"]
    assert "heat" in modes
    assert "cool" not in modes
    s.device.force_input(R.MODE_STATUS, 2)  # summer_auto
    await clock.poll()
    modes = s.state("climate", CLIMATE).attributes["hvac_modes"]
    assert "cool" in modes
    assert "heat" not in modes


async def test_season_change_refused_while_integration_runs(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "cool")
    with pytest.raises(ServiceValidationError):
        await s.service("select", "select_option", "season", option="winter")
    assert s.device.holding[R.HB04_SEASON] == R.SEASON_SUMMER


# ---- brine circuit -----------------------------------------------------------
BRINE = "sensor.brine_supply"


@pytest.mark.parametrize(
    "entry_options",
    [{"water_circuit": "brine", "brine_temperature_entity": BRINE}],
)
async def test_brine_guard_gates_starts_only(hass, setup, clock):
    s = setup
    await allow_operation(s)
    hass.states.async_set(BRINE, "6.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert s.state("binary_sensor", "brine_temperature_guard").state == "on"
    with pytest.raises(ServiceValidationError, match="Brine temperature guard"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    assert s.device.holding[R.DEU_REQUEST] == 0

    # 9 °C passes the default 8 °C minimum (below PU08: the passive path).
    hass.states.async_set(BRINE, "9.0", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert s.state("binary_sensor", "brine_temperature_guard").state == "off"
    await set_hvac_mode(s, clock, "dry")
    assert s.state("climate", CLIMATE).attributes["hvac_action"] == "drying"

    # Cold again: the running request is not stopped, only flagged.
    hass.states.async_set(BRINE, "5.0", {"unit_of_measurement": "°C"})
    await clock.poll()
    assert s.device.holding[R.DEU_REQUEST] == 1
    assert (
        "brine_guard_blocking"
        in (s.state("sensor", "water_check").attributes["issues"])
    )


# A display unit (overlay display_cnu2): its own room logic can start it.
@pytest.mark.parametrize("sim_options", [{"overlays": ("display_cnu2",)}])
@pytest.mark.parametrize(
    "entry_options",
    [
        {
            "has_display": True,
            "water_circuit": "brine",
            "brine_temperature_entity": BRINE,
        }
    ],
)
async def test_auto_is_a_start_for_the_brine_guard(hass, setup):
    s = setup
    await allow_operation(s)
    hass.states.async_set(BRINE, "6.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError, match="Brine temperature guard"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="auto")
    # Switching the unit on is the same start: its own logic would run.
    with pytest.raises(ServiceValidationError, match="Brine temperature guard"):
        await s.service("switch", "turn_on", "unit_on_off")
    assert s.device.holding[R.BMS_ON] == 0


@pytest.mark.parametrize("sim_options", [{"overlays": ("display_cnu2",)}])
@pytest.mark.parametrize(
    "entry_options", [{"has_display": True, "water_circuit": "brine"}]
)
async def test_brine_winter_refuses_a_unit_that_would_dehumidify_alone(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    # PU02 off (factory): no winter dehumidifying, so switching on is harmless.
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    await s.service("switch", "turn_off", "unit_on_off")
    await clock.settle()
    await s.service("select", "select_option", "winter_dehumidify", option="with_water")
    await clock.settle()
    with pytest.raises(ServiceValidationError, match="brine temperature guard"):
        await s.service("switch", "turn_on", "unit_on_off")
    assert s.device.holding[R.BMS_ON] == 0


@pytest.mark.parametrize("sim_options", [{"overlays": ("display_cnu2",)}])
@pytest.mark.parametrize(
    "entry_options", [{"has_display": True, "water_circuit": "brine"}]
)
async def test_brine_season_change_refused_for_a_unit_that_would_dehumidify_alone(
    setup, clock
):
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "winter_dehumidify", option="with_water")
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    # The same winter dehumidifying as switching on in winter, by the season.
    with pytest.raises(ServiceValidationError, match="brine temperature guard"):
        await s.service("select", "select_option", "season", option="winter")
    assert s.device.holding[R.HB04_SEASON] == R.SEASON_SUMMER


@pytest.mark.parametrize("sim_options", [{"overlays": ("display_cnu2",)}])
@pytest.mark.parametrize(
    "entry_options",
    [
        {
            "has_display": True,
            "water_circuit": "brine",
            "brine_temperature_entity": BRINE,
        }
    ],
)
async def test_refused_auto_leaves_a_running_request_alone(hass, setup, clock):
    s = setup
    await allow_operation(s)
    hass.states.async_set(BRINE, "12.0", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await set_hvac_mode(s, clock, "dry")
    hass.states.async_set(BRINE, "6.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    s.device.clear_write_log()
    with pytest.raises(ServiceValidationError, match="Brine temperature guard"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="auto")
    assert s.device.write_log == []
    assert s.device.holding[R.DEU_REQUEST] == 1


@pytest.mark.parametrize(
    "entry_options",
    [{"water_circuit": "brine", "brine_temperature_entity": BRINE}],
)
async def test_refused_dry_leaves_a_running_cool_alone(hass, setup, clock):
    s = setup
    await allow_operation(s)
    hass.states.async_set(BRINE, "12.0", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await set_hvac_mode(s, clock, "cool")
    hass.states.async_set(BRINE, "6.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    s.device.clear_write_log()
    with pytest.raises(ServiceValidationError, match="Brine temperature guard"):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    assert s.device.write_log == []
    assert s.device.holding[R.INT_REQUEST] == 1


@pytest.mark.parametrize("entry_options", [{"water_circuit": "brine"}])
async def test_brine_never_heats(setup, clock):
    s = setup
    await allow_operation(s)
    await s.service("select", "select_option", "season", option="winter")
    await clock.settle()
    assert "heat" not in s.state("climate", CLIMATE).attributes["hvac_modes"]
    # INT set at the unit: on brine it never heats, and the card never says so.
    await s.service("switch", "turn_on", "unit_on_off")
    await clock.settle()
    s.device.set_holding(R.INT_REQUEST, 1)
    await clock.poll()
    climate = s.state("climate", CLIMATE)
    assert climate.state == "off"
    assert climate.attributes["hvac_action"] == "idle"
    with pytest.raises(ServiceValidationError):
        await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
