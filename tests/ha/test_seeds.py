"""Smoke test over every real-device dump in tests/devices (x variants).

Dropping a new ``diagnose_hrds.py --json`` dump into ``tests/devices`` adds it
here with no code change.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.innova_hrds.const import DOMAIN
from tests.sim import HrdsDevice, HrdsSimServer, list_seeds
from tests.sim import registers as R

from .conftest import CLIMATE, add_entry, allow_operation, set_hvac_mode

VARIANTS = {
    "as_dumped": ((), {}),
    "display": (("display_with_probes",), {"has_display": True}),
    "non_r": (("non_r",), {}),
}


@pytest.fixture(params=list_seeds())
def seed(request) -> str:
    return request.param


@pytest.mark.parametrize("variant", list(VARIANTS))
async def test_seed_sets_up_and_dehumidifies(hass, clock, seed, variant):
    overlays, options = VARIANTS[variant]
    server = HrdsSimServer(HrdsDevice(seed, overlays))
    await server.start()
    try:
        s = await add_entry(hass, server, **options)
        assert s.entry.state is ConfigEntryState.LOADED
        assert s.state("sensor", "unit_status").state in ("off_by_bms", "on")
        await allow_operation(s)
        await set_hvac_mode(s, clock, "dry")
        assert s.state("climate", CLIMATE).attributes["hvac_action"] == "drying"
        damper = s.state("sensor", "recirculation_damper").state
        assert damper == ("disabled" if variant == "non_r" else "on")
        await hass.config_entries.async_unload(s.entry.entry_id)
        await hass.async_block_till_done()
    finally:
        await server.stop()


async def test_cool_not_offered_without_active_cooling(hass, clock):
    """PG02 = 0: the unit has no integration function and ignores INT."""
    server = HrdsSimServer(HrdsDevice(overlays=("no_dc",)))
    await server.start()
    try:
        s = await add_entry(hass, server)
        assert s.state("binary_sensor", "active_cooling_available").state == "off"
        modes = s.state("climate", CLIMATE).attributes["hvac_modes"]
        await allow_operation(s)
        with pytest.raises(ServiceValidationError, match="PG02"):
            await s.service("switch", "turn_on", "active_cooling")
        refused_write = server.device.holding[R.INT_REQUEST]
        await hass.config_entries.async_unload(s.entry.entry_id)
        await hass.async_block_till_done()
    finally:
        await server.stop()
    assert "cool" not in modes
    assert refused_write == 0


@pytest.mark.parametrize(
    ("overlays", "options"),
    [((), {}), (("display_with_probes",), {"has_display": True})],
    ids=["headless", "display"],
)
async def test_entity_states_snapshot(hass, clock, snapshot, overlays, options):
    """Every enabled entity's state after setup, per profile.

    Update with ``pytest tests/ha/test_seeds.py --snapshot-update`` after an
    intended change and review the diff.
    """
    server = HrdsSimServer(HrdsDevice(overlays=overlays))
    await server.start()
    try:
        s = await add_entry(hass, server, **options)
        await clock.poll()
        registry = er.async_get(hass)
        states = {}
        for entry in er.async_entries_for_config_entry(registry, s.entry.entry_id):
            state = hass.states.get(entry.entity_id)
            if state is None:  # disabled by default
                continue
            key = entry.unique_id.removeprefix(f"{s.entry.entry_id}-")
            states[f"{entry.domain}.{key}"] = state.state
        assert entry.platform == DOMAIN
        assert dict(sorted(states.items())) == snapshot
        await hass.config_entries.async_unload(s.entry.entry_id)
        await hass.async_block_till_done()
    finally:
        await server.stop()
