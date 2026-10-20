"""Minimal client for a real Home Assistant over REST and websocket.

Modelled on the ``ha_integration_test_harness`` the config repo uses (same
ideas: onboard once, poll ``assert_entity_state`` until it matches, default
timeouts on every HTTP call), but small and without its docker-compose, so a
simulated device can run next to Home Assistant.
"""

from __future__ import annotations

import itertools
import json
import threading
import time
from collections.abc import Callable
from typing import Any

import requests
import websocket

DEFAULT_TIMEOUT = 30
CLIENT_ID = "http://127.0.0.1:8123/"


class ServiceError(Exception):
    """A service call answered with an error (code + message)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class HomeAssistant:
    """One Home Assistant instance, onboarded, with a long-lived token."""

    def __init__(self, base_url: str = "http://127.0.0.1:8123") -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self._ws: websocket.WebSocket | None = None
        self._ws_lock = threading.Lock()
        self._ids = itertools.count(1)

    # ---- startup -------------------------------------------------------------
    def wait_ready(self, timeout: float = 300) -> None:
        """Wait until the API answers (401 without a token is fine)."""
        deadline = time.monotonic() + timeout
        last: object = None
        while time.monotonic() < deadline:
            try:
                resp = requests.get(f"{self.base_url}/api/", timeout=5)
                if resp.status_code in (200, 401):
                    return
                last = resp.status_code
            except requests.RequestException as exc:
                last = exc
            time.sleep(1)
        raise TimeoutError(f"Home Assistant not ready after {timeout}s: {last!r}")

    def wait_running(self, timeout: float = 300) -> None:
        """Wait until Home Assistant reports it is fully started (after a restart).

        The API answers long before that; entries are still being set up.
        """
        deadline = time.monotonic() + timeout
        last: object = None
        while time.monotonic() < deadline:
            try:
                resp = requests.get(
                    f"{self.base_url}/api/config", headers=self._headers, timeout=5
                )
                if resp.status_code == 200 and resp.json().get("state") == "RUNNING":
                    return
                last = resp.status_code
            except requests.RequestException as exc:
                last = exc
            time.sleep(1)
        raise TimeoutError(f"Home Assistant not running after {timeout}s: {last!r}")

    def onboard(self, username: str = "ci", password: str = "ci-password") -> None:
        """Create the owner user, log in and swap to a long-lived token."""
        resp = requests.post(
            f"{self.base_url}/api/onboarding/users",
            json={
                "client_id": CLIENT_ID,
                "name": "CI",
                "username": username,
                "password": password,
                "language": "en",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        code = resp.json()["auth_code"]
        resp = requests.post(
            f"{self.base_url}/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
            },
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        self.token = resp.json()["access_token"]
        for step, body in (
            ("core_config", {}),
            ("analytics", {}),
            ("integration", {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID}),
        ):
            # Finish onboarding so the instance behaves like a normal install.
            requests.post(
                f"{self.base_url}/api/onboarding/{step}",
                json=body,
                headers=self._headers,
                timeout=DEFAULT_TIMEOUT,
            )
        self.token = self.ws(
            {
                "type": "auth/long_lived_access_token",
                "client_name": "hrds-e2e",
                "lifespan": 1,
            }
        )

    # ---- REST ----------------------------------------------------------------
    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path: str) -> Any:
        resp = requests.get(
            f"{self.base_url}{path}", headers=self._headers, timeout=DEFAULT_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, body: dict | None = None) -> Any:
        resp = requests.post(
            f"{self.base_url}{path}",
            json=body or {},
            headers=self._headers,
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise requests.HTTPError(f"{resp.status_code} {path}: {resp.text}")
        return resp.json()

    def get_state(self, entity_id: str) -> dict | None:
        resp = requests.get(
            f"{self.base_url}/api/states/{entity_id}",
            headers=self._headers,
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    # ---- config entries ------------------------------------------------------
    def flow_start(self, handler: str) -> dict:
        return self.post("/api/config/config_entries/flow", {"handler": handler})

    def flow_configure(self, flow_id: str, data: dict) -> dict:
        return self.post(f"/api/config/config_entries/flow/{flow_id}", data)

    def options_flow_start(self, entry_id: str) -> dict:
        """Open the options form; the reply carries the form schema."""
        return self.post(
            "/api/config/config_entries/options/flow", {"handler": entry_id}
        )

    def options_flow_configure(self, flow_id: str, data: dict) -> dict:
        return self.post(f"/api/config/config_entries/options/flow/{flow_id}", data)

    def options_flow_abort(self, flow_id: str) -> None:
        requests.delete(
            f"{self.base_url}/api/config/config_entries/options/flow/{flow_id}",
            headers=self._headers,
            timeout=DEFAULT_TIMEOUT,
        )

    def options_flow(self, entry_id: str, data: dict) -> dict:
        flow = self.options_flow_start(entry_id)
        return self.options_flow_configure(flow["flow_id"], data)

    def reload_entry(self, entry_id: str) -> None:
        self.post(f"/api/config/config_entries/entry/{entry_id}/reload")

    def config_entries(self, domain: str) -> list[dict]:
        return self.get(f"/api/config/config_entries/entry?domain={domain}")

    def delete_entry(self, entry_id: str) -> None:
        resp = requests.delete(
            f"{self.base_url}/api/config/config_entries/entry/{entry_id}",
            headers=self._headers,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()

    # ---- websocket -----------------------------------------------------------
    def ws(self, message: dict) -> Any:
        """Send one websocket command and return its result."""
        with self._ws_lock:
            if self._ws is None:
                self._ws = self._ws_connect()
            msg_id = next(self._ids)
            self._ws.send(json.dumps({"id": msg_id, **message}))
            while True:
                reply = json.loads(self._ws.recv())
                if reply.get("id") == msg_id and reply.get("type") == "result":
                    break
        if not reply["success"]:
            err = reply.get("error", {})
            raise ServiceError(err.get("code", "unknown"), err.get("message", ""))
        return reply.get("result")

    def _ws_connect(self) -> websocket.WebSocket:
        url = self.base_url.replace("http", "ws", 1) + "/api/websocket"
        conn = websocket.create_connection(url, timeout=DEFAULT_TIMEOUT)
        json.loads(conn.recv())  # auth_required
        conn.send(json.dumps({"type": "auth", "access_token": self.token}))
        reply = json.loads(conn.recv())
        if reply.get("type") != "auth_ok":
            raise RuntimeError(f"websocket auth failed: {reply}")
        return conn

    def close(self) -> None:
        if self._ws is not None:
            self._ws.close()
            self._ws = None

    def call_service(
        self, domain: str, service: str, entity_id: str | None = None, **data
    ) -> None:
        """Call a service, raising ServiceError if Home Assistant refuses it."""
        message = {"type": "call_service", "domain": domain, "service": service}
        if data:
            message["service_data"] = data
        if entity_id:
            message["target"] = {"entity_id": entity_id}
        self.ws(message)

    def entity_registry(self) -> list[dict]:
        return self.ws({"type": "config/entity_registry/list"})

    def device_registry(self) -> list[dict]:
        return self.ws({"type": "config/device_registry/list"})

    def entity_registry_update(self, entity_id: str, **changes: Any) -> dict:
        return self.ws(
            {
                "type": "config/entity_registry/update",
                "entity_id": entity_id,
                **changes,
            }
        )

    # ---- assertions ----------------------------------------------------------
    def assert_entity_state(
        self,
        entity_id: str,
        expected: str | Callable[[dict], bool],
        attributes: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> dict:
        """Poll until the entity's state (and given attributes) match."""
        deadline = time.monotonic() + timeout
        state: dict | None = None
        while True:
            state = self.get_state(entity_id)
            if state is not None and _matches(state, expected, attributes):
                return state
            if time.monotonic() > deadline:
                shown = (
                    None
                    if state is None
                    else {
                        "state": state["state"],
                        "attributes": state["attributes"],
                    }
                )
                raise AssertionError(
                    f"{entity_id}: expected {expected!r} {attributes or ''} "
                    f"within {timeout}s, last {shown}"
                )
            time.sleep(0.5)


def _matches(state: dict, expected, attributes) -> bool:
    ok = expected(state) if callable(expected) else state["state"] == expected
    for key, value in (attributes or {}).items():
        ok = ok and state["attributes"].get(key) == value
    return ok
