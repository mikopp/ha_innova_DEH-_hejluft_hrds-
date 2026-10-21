"""Needs a real HA because: a restart proves what the integration cannot show
in-process, namely that the setup really comes back from Home Assistant's disk
storage after a real boot (``persistence``) and that booting before the unit is
reachable ends loaded by itself (``boot-order``).

The code paths behind these (what a fresh start does given the unit's state,
options, gate restore) are tested in-process in tests/ha/test_restart.py; the
restart contract is listed in tests/CLAUDE.md. Each restart costs 20-30 s, so
there are four, and each checks as much of the contract as it can.
"""

from __future__ import annotations

import time

import pytest

from .conftest import DOMAIN, wait_loaded
from .ha_client import ServiceError

CLIMATE = "hrds_climate"
BRINE_SENSOR = "sensor.brine_supply"
BRINE_INPUT = "input_number.brine_temperature"


def _unique_ids(entry) -> dict[str, str]:
    """unique id (without the entry id) -> entity id, from the real registry."""
    prefix = f"{entry.entry_id}-"
    return {
        e["unique_id"].removeprefix(prefix): e["entity_id"]
        for e in entry.ha.entity_registry()
        if e.get("config_entry_id") == entry.entry_id
    }


def _device_ids(entry) -> set[str]:
    return {
        d["id"]
        for d in entry.ha.device_registry()
        if entry.entry_id in d["config_entries"]
    }


def _form_values(form: dict) -> dict:
    """The values an options form would show (suggested value or default)."""
    return {
        f["name"]: f.get("description", {}).get("suggested_value", f.get("default"))
        for f in form["data_schema"]
    }


def _booted(entry, restart_ha, while_down=None) -> None:
    restart_ha(while_down)
    wait_loaded(entry.ha, entry.entry_id, timeout=120)
    entry.entity_ids.clear()


@pytest.mark.needs_real_ha("persistence")
def test_setup_survives_restart(hl, restart_ha):
    """Contract 1: what the user configured is still there and in force."""
    ha = hl.ha
    ha.call_service("input_number", "set_value", BRINE_INPUT, value=15)
    hl.options(
        water_circuit="brine",
        brine_temperature_entity=BRINE_SENSOR,
        brine_min_temperature=12.0,
        installer_device=True,
    )
    renamed = hl.eid("unit_status")
    disabled = next(
        e
        for e in ha.entity_registry()
        if e.get("config_entry_id") == hl.entry_id
        and e.get("disabled_by") == "integration"
    )
    try:
        # What a user does in the UI: rename an entity, enable an installer one.
        ha.entity_registry_update(renamed, name="Unit state (mine)")
        ha.entity_registry_update(disabled["entity_id"], disabled_by=None)
        ha.reload_entry(hl.entry_id)
        wait_loaded(ha, hl.entry_id)
        ha.assert_entity_state(disabled["entity_id"], lambda s: True)
        hl.entity_ids.clear()
        hl.allow_operation()
        entities, devices = _unique_ids(hl), _device_ids(hl)

        _booted(hl, restart_ha)

        assert _unique_ids(hl) == entities, "entity ids are stable"
        assert _device_ids(hl) == devices, "device ids are stable"
        registry = {e["entity_id"]: e for e in ha.entity_registry()}
        assert registry[renamed]["name"] == "Unit state (mine)"
        assert registry[disabled["entity_id"]]["disabled_by"] is None
        assert ha.get_state(disabled["entity_id"]) is not None
        hl.assert_state("operation_allowed", "on")  # the gate was restored

        form = ha.options_flow_start(hl.entry_id)
        try:
            values = _form_values(form)
        finally:
            ha.options_flow_abort(form["flow_id"])
        assert values["water_circuit"] == "brine"
        assert values["brine_temperature_entity"] == BRINE_SENSOR
        assert values["brine_min_temperature"] == 12.0
        assert values["installer_device"] is True

        # ... and still in force: a cold brine sensor refuses the start.
        ha.call_service("input_number", "set_value", BRINE_INPUT, value=6)
        hl.assert_state("brine_temperature_guard", "on")
        with pytest.raises(ServiceError) as err:
            hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
        assert "Brine temperature guard" in err.value.message
    finally:
        ha.call_service("input_number", "set_value", BRINE_INPUT, value=15)
        hl.options()
        ha.entity_registry_update(renamed, name=None)
        ha.entity_registry_update(disabled["entity_id"], disabled_by="user")


@pytest.mark.needs_real_ha("persistence")
def test_running_unit_is_untouched_and_polling_resumes(hl, restart_ha):
    """Contract 2: nothing the unit is doing is disturbed by a restart."""
    hl.allow_operation()
    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    hl.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})
    hl.sim.call("/clear_writes")

    _booted(hl, restart_ha)

    # The unit still holds every required setting: nothing at all is written.
    assert hl.sim.writes() == []
    state = hl.sim.state()
    assert state["unit_status"] == 5 and state["compressor_status"] == 4
    hl.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})

    # The real scheduler is polling again after the real boot.
    hl.sim.call("/alarm", {"code": "AL22"})
    hl.assert_state("alarm_dirty_filter", "on")
    hl.sim.call("/alarm", {"code": "AL22", "active": False})


@pytest.mark.needs_real_ha("boot-order")
def test_ha_booting_before_the_unit_is_reachable(hl, restart_ha):
    """Contract 3: the unit not being reachable at boot does not matter."""
    ha = hl.ha
    restart_ha(while_down=lambda: hl.sim.call("/offline"))
    try:
        deadline = time.monotonic() + 90
        while True:
            entry = next(
                e for e in ha.config_entries(DOMAIN) if e["entry_id"] == hl.entry_id
            )
            if entry["state"] == "setup_retry":
                break
            assert time.monotonic() < deadline, f"entry is {entry['state']}"
            time.sleep(1)
    finally:
        hl.sim.call("/online")
    wait_loaded(ha, hl.entry_id, timeout=150)  # HA's own retry, nobody helps
    hl.entity_ids.clear()
    hl.assert_state("unit_status", lambda s: s["state"] in ("off_by_bms", "on"))
    hl.assert_state(CLIMATE, "off")


@pytest.mark.needs_real_ha("persistence")
def test_restart_together_with_a_unit_power_cycle(hl, restart_ha):
    """Contract 4: a unit that lost its settings gets them back."""
    _booted(hl, restart_ha, while_down=lambda: hl.sim.call("/power_cycle"))

    hl.sim.wait_for(
        lambda s: (
            s["holding"]["1778"] == 1
            and s["holding"]["1777"] == 0
            and s["holding"]["1803"] == 0
        ),
        what="required settings restored",
    )
    hl.assert_state("unit_status", "off_by_bms")
    hl.allow_operation()
    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    hl.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})
