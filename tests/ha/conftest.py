"""Fixtures for the in-process layer: real Home Assistant core (via
pytest-homeassistant-custom-component) + the integration's real pymodbus
client + the simulated HRDS+ over a real TCP socket on 127.0.0.1.

Time is not frozen: the sync Modbus client measures its own timeouts with the
real clock. Polls are driven by firing the time listeners a growing offset into
the future instead (:class:`Clock`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.syrupy import (
    HomeAssistantSnapshotExtension,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.innova_hrds.const import (
    CONF_HAS_DISPLAY,
    CONF_HOSTID,
    CONF_MODEL,
    CONF_WATER_CIRCUIT,
    DOMAIN,
)
from tests.sim import HrdsDevice, HrdsSimServer


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Snapshots in ``snapshots/`` next to the test (Home Assistant's layout).

    phcc and syrupy both define ``snapshot``; which one wins depends on the
    order pytest loads the plugins, and that differs between machines (on
    GitHub's runner syrupy's plain fixture won and looked in ``__snapshots__``).
    A conftest fixture beats both, so the extension is applied explicitly.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/innova_hrds in every test."""
    return


@pytest.fixture(autouse=True)
def _allow_local_sockets(socket_enabled):
    """HA's test setup blocks sockets; the simulator needs 127.0.0.1."""
    return


class Clock:
    """Fire HA time listeners as if time had moved on, without freezing it."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.offset = timedelta()

    async def advance(self, seconds: float) -> None:
        self.offset += timedelta(seconds=seconds)
        async_fire_time_changed(self.hass, dt_util.utcnow() + self.offset)
        # Interval jobs run as background tasks.
        await self.hass.async_block_till_done(wait_background_tasks=True)

    async def poll(self) -> None:
        """One full scan interval (30 s default)."""
        await self.advance(31)

    async def settle(self) -> None:
        """Let the debounced post-write refresh (1.5 s) run."""
        await self.advance(2)


@pytest.fixture
def clock(hass: HomeAssistant) -> Clock:
    return Clock(hass)


@pytest.fixture
def sim_options() -> dict[str, Any]:
    """Override in a module to change the simulated unit."""
    return {}


@pytest.fixture
async def sim(hass: HomeAssistant, sim_options) -> AsyncIterator[HrdsSimServer]:
    """A running simulator (headless factory seed unless overridden)."""
    device = HrdsDevice(**sim_options)
    server = HrdsSimServer(device)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


def entry_data(sim: HrdsSimServer, **overrides: Any) -> dict[str, Any]:
    data = {
        CONF_NAME: "HRDS+",
        CONF_HOST: sim.host,
        CONF_PORT: sim.port,
        CONF_SCAN_INTERVAL: 30,
        CONF_HOSTID: 1,
        CONF_MODEL: "30",
        CONF_HAS_DISPLAY: False,
        CONF_WATER_CIRCUIT: "heating_cooling",
    }
    data.update(overrides)
    return data


@dataclass
class Setup:
    """A set-up config entry plus helpers to find its entities."""

    hass: HomeAssistant
    entry: MockConfigEntry
    sim: HrdsSimServer

    @property
    def device(self) -> HrdsDevice:
        return self.sim.device

    def entity_id(self, platform: str, key: str) -> str | None:
        return er.async_get(self.hass).async_get_entity_id(
            platform, DOMAIN, f"{self.entry.entry_id}-{key}"
        )

    def state(self, platform: str, key: str):
        entity_id = self.entity_id(platform, key)
        assert entity_id, f"no {platform} entity for {key}"
        return self.hass.states.get(entity_id)

    async def service(self, domain: str, service: str, key: str, **data: Any) -> None:
        await self.hass.services.async_call(
            domain,
            service,
            {"entity_id": self.entity_id(domain, key), **data},
            blocking=True,
        )


@pytest.fixture
def entry_options() -> dict[str, Any]:
    """Override in a module to change the config entry data."""
    return {}


async def add_entry(hass: HomeAssistant, sim: HrdsSimServer, **data: Any) -> Setup:
    """Create and set up a config entry pointing at ``sim``."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="HRDS+",
        data=entry_data(sim, **data),
        unique_id=sim.host,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return Setup(hass, entry, sim)


@pytest.fixture
async def setup(
    hass: HomeAssistant, sim: HrdsSimServer, entry_options
) -> AsyncIterator[Setup]:
    s = await add_entry(hass, sim, **entry_options)
    assert s.entry.state is ConfigEntryState.LOADED
    yield s
    # Unload like Home Assistant does on shutdown, so pending timers are
    # cancelled by the integration itself (verify_cleanup checks that).
    if s.entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(s.entry.entry_id)
        await hass.async_block_till_done()


async def allow_operation(s: Setup) -> None:
    await s.service("switch", "turn_on", "operation_allowed")


CLIMATE = "hrds_climate"
FAN = "hrds_supply_fan"


async def set_hvac_mode(s: Setup, clock: Clock, mode: str) -> None:
    await s.service("climate", "set_hvac_mode", CLIMATE, hvac_mode=mode)
    await clock.settle()
