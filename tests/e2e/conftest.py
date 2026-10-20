"""Real Home Assistant in Docker + simulated HRDS+ units as host processes.

Like the config repo's harness: one Home Assistant container for the whole
session, talked to over REST and websocket only. Three simulators run next to
it (all on the host network):

=========  =========  ======  =======  ======================================
name       address    Modbus  control  used for
=========  =========  ======  =======  ======================================
headless   127.0.0.1  5020    8020     entry ``127.0.0.1`` (no display/probes)
display    127.0.0.1  5021    8021     entry ``localhost`` (display + probes)
spare      127.0.0.2  5022    8022     config-flow failures, throw-away entry
=========  =========  ======  =======  ======================================

The config entry's unique id is the host, hence the different host strings.

Environment: ``HRDS_E2E_IMAGE`` (default: the pinned Dockerfile),
``HRDS_E2E_ARTIFACTS`` (where logs land, default ``tests/e2e/.artifacts``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import requests

from .ha_client import HomeAssistant, ServiceError
from .stage import ROOT, image_from_dockerfile, stage

DOMAIN = "innova_hrds"
CONTAINER = "hrds-e2e-ha"
ARTIFACTS = Path(os.environ.get("HRDS_E2E_ARTIFACTS", ROOT / "tests/e2e/.artifacts"))
SCAN_INTERVAL = 5  # the integration's minimum: keeps polls quick
POLL = SCAN_INTERVAL * 3 + 10  # generous wait for "after the next poll"

SIMULATORS = {
    "headless": ("127.0.0.1", 5020, 8020, []),
    "display": ("127.0.0.1", 5021, 8021, ["--overlay", "display_with_probes"]),
    "spare": ("127.0.0.2", 5022, 8022, []),
}

# Options-flow form with every field, as the UI would submit it.
BASE_OPTIONS = {
    "scan_interval": SCAN_INTERVAL,
    "hostid": 1,
    "model": "30",
    "water_circuit": "heating_cooling",
    "allow_winter_heating": False,
    "brine_min_temperature": 10.0,
    "airflow_max_m3h": 300,
}


# ---- simulator control ---------------------------------------------------------
@dataclass
class Sim:
    """A simulator process and its control API."""

    name: str
    address: str
    port: int
    control_port: int
    proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.control_port}"

    def call(self, path: str, body: dict | None = None) -> dict:
        resp = requests.post(f"{self.url}{path}", json=body or {}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def state(self) -> dict:
        return requests.get(f"{self.url}/state", timeout=15).json()

    def holding(self, address: int) -> int:
        return self.state()["holding"][str(address)]

    def input(self, address: int) -> int:
        return self.state()["input"][str(address)]

    def writes(self) -> list[tuple[int, int]]:
        return [(w["address"], w["value"]) for w in self.state()["writes"]]

    def wait_for(self, check, timeout: float = POLL, what: str = "") -> dict:
        deadline = time.monotonic() + timeout
        while True:
            state = self.state()
            if check(state):
                return state
            if time.monotonic() > deadline:
                raise AssertionError(f"{self.name}: timed out waiting for {what}")
            time.sleep(0.5)

    def fault(self, **kwargs: Any) -> dict:
        return self.call("/fault", kwargs)


def _start_sim(
    name: str, address: str, port: int, control: int, extra: list[str]
) -> Sim:
    log = open(ARTIFACTS / f"sim-{name}.log", "w")  # noqa: SIM115 - closed with proc
    command = [sys.executable, "-m", "tests.sim", "--host", address]
    command += ["--port", str(port), "--control-port", str(control), *extra]
    proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    sim = Sim(name, address, port, control, proc)
    deadline = time.monotonic() + 30
    while True:
        try:
            sim.state()
            return sim
        except requests.RequestException:
            if proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"simulator {name} did not start, see {log.name}")
            time.sleep(0.2)


@pytest.fixture(scope="session")
def sims() -> Iterator[dict[str, Sim]]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    started = {name: _start_sim(name, *spec) for name, spec in SIMULATORS.items()}
    yield started
    for sim in started.values():
        sim.proc.terminate()
        sim.proc.wait(timeout=10)


# ---- Home Assistant container -------------------------------------------------
def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check
    )


@pytest.fixture(scope="session")
def ha(sims, tmp_path_factory) -> Iterator[HomeAssistant]:
    image = os.environ.get("HRDS_E2E_IMAGE") or image_from_dockerfile()
    config = stage(tmp_path_factory.mktemp("ha") / "config")
    _docker("rm", "-f", CONTAINER, check=False)
    _docker(
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--network",
        "host",
        "-e",
        "TZ=Europe/Vienna",
        "-v",
        f"{config}:/config",
        image,
    )
    client = HomeAssistant()
    try:
        client.wait_ready()
        client.onboard()
        yield client
    finally:
        client.close()
        logs = _docker("logs", CONTAINER, check=False)
        (ARTIFACTS / "home-assistant-docker.log").write_text(logs.stdout + logs.stderr)
        ha_log = config / "home-assistant.log"
        if ha_log.exists():
            (ARTIFACTS / "home-assistant.log").write_text(ha_log.read_text())
        _docker("rm", "-f", CONTAINER, check=False)


# ---- config entries --------------------------------------------------------------
@dataclass
class Entry:
    """A set-up config entry and helpers to reach its entities."""

    ha: HomeAssistant
    sim: Sim
    entry_id: str
    host: str
    has_display: bool
    entity_ids: dict[str, str] = field(default_factory=dict)

    def refresh_entities(self) -> None:
        prefix = f"{self.entry_id}-"
        self.entity_ids = {
            e["unique_id"].removeprefix(prefix): e["entity_id"]
            for e in self.ha.entity_registry()
            if e.get("config_entry_id") == self.entry_id
        }

    def eid(self, key: str) -> str:
        if key not in self.entity_ids:
            self.refresh_entities()
        return self.entity_ids[key]

    def has(self, key: str) -> bool:
        self.refresh_entities()
        return key in self.entity_ids

    def state(self, key: str) -> dict:
        return self.ha.get_state(self.eid(key))

    def assert_state(
        self, key: str, expected, attributes=None, timeout: float = POLL
    ) -> dict:
        return self.ha.assert_entity_state(self.eid(key), expected, attributes, timeout)

    def service(self, domain: str, service: str, key: str, **data) -> None:
        self.ha.call_service(domain, service, self.eid(key), **data)

    def options(self, **changes: Any) -> None:
        """Submit the options form (triggers a reload) and wait for setup."""
        data = {
            "host": self.host,
            "port": self.sim.port,
            "has_display": self.has_display,
            **BASE_OPTIONS,
            **changes,
        }
        result = self.ha.options_flow(self.entry_id, data)
        assert result["type"] == "create_entry", result
        wait_loaded(self.ha, self.entry_id)
        self.entity_ids.clear()

    def allow_operation(self, allowed: bool = True) -> None:
        self.service(
            "switch", "turn_on" if allowed else "turn_off", "operation_allowed"
        )
        self.assert_state("operation_allowed", "on" if allowed else "off", timeout=10)


def wait_loaded(ha: HomeAssistant, entry_id: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while True:
        entry = next(e for e in ha.config_entries(DOMAIN) if e["entry_id"] == entry_id)
        if entry["state"] == "loaded":
            return
        if time.monotonic() > deadline:
            raise AssertionError(f"entry {entry_id} is {entry['state']}")
        time.sleep(0.5)


def user_input(host: str, port: int, **overrides: Any) -> dict:
    data = {
        "name": "HRDS+",
        "host": host,
        "port": port,
        "scan_interval": SCAN_INTERVAL,
        "hostid": 1,
        "model": "30",
        "has_display": False,
        "water_circuit": "heating_cooling",
        "allow_winter_heating": False,
        "brine_min_temperature": 10.0,
    }
    data.update(overrides)
    return data


def create_entry(ha: HomeAssistant, sim: Sim, host: str, **overrides: Any) -> Entry:
    flow = ha.flow_start(DOMAIN)
    assert flow["type"] == "form", flow
    result = ha.flow_configure(flow["flow_id"], user_input(host, sim.port, **overrides))
    assert result["type"] == "create_entry", result
    entry_id = result["result"]["entry_id"]
    wait_loaded(ha, entry_id)
    entry = Entry(ha, sim, entry_id, host, overrides.get("has_display", False))
    entry.refresh_entities()
    return entry


@pytest.fixture(scope="session")
def headless(ha, sims) -> Entry:
    name = "HRDS headless"
    return create_entry(ha, sims["headless"], "127.0.0.1", name=name)


@pytest.fixture(scope="session")
def display(ha, sims) -> Entry:
    return create_entry(
        ha, sims["display"], "localhost", name="HRDS display", has_display=True
    )


def _reset(entry: Entry) -> None:
    """Fresh unit, gate closed, required settings re-asserted, log cleared."""
    try:
        entry.allow_operation(False)
    except ServiceError:
        pass
    entry.sim.call("/reset")
    # Two polls: one reads the factory state, the next re-asserts settings.
    entry.sim.wait_for(
        lambda s: s["holding"]["1778"] == 1, what="BMS enable re-asserted"
    )
    entry.assert_state("unit_status", lambda s: s["state"] in ("off_by_bms", "on"))
    entry.sim.call("/clear_writes")


@pytest.fixture
def hl(headless) -> Iterator[Entry]:
    """The headless entry, reset to the factory unit before the test."""
    _reset(headless)
    yield headless
    try:
        headless.service("climate", "set_hvac_mode", "hrds_climate", hvac_mode="off")
    except ServiceError:
        pass


@pytest.fixture
def disp(display) -> Iterator[Entry]:
    """The display entry, reset before the test."""
    _reset(display)
    yield display
