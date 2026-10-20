"""HTTP control API for a simulator process (used by the Docker e2e tests).

Stdlib only. All bodies are JSON; every POST answers with ``GET /state``.

=====================  =====================================================
``GET  /state``        device summary incl. the write log (``writes``)
``POST /reset``        back to the seed, faults cleared, write log emptied, online
``POST /power_cycle``  volatile settings back to factory values
``POST /offline``      stop answering Modbus (port closed)
``POST /online``       answer again
``POST /clear_writes`` empty the write log
``POST /alarm``        ``{"code": "AL11", "active": true}``
``POST /probe``        ``{"address": 499, "unplug": true}`` or ``{"address": 499, "raw": 225}``
``POST /set``          ``{"input": {"501": 350}, "holding": {"1825": 7}}`` (as if set on the unit)
``POST /force``        ``{"input": {"1104": 9}}`` pin an input whatever the model computes
                       (``null`` releases it)
``POST /fault``        any of ``illegal_addresses``, ``reject_writes``, ``ignore_writes``
                       (lists), ``delay`` (s), ``fc43`` (bool), ``identity``
                       (``{"0": vendor, "1": product, "2": revision}``),
                       ``pump_fault``, ``display_on`` (bool), ``fan_model``,
                       ``water_temperature`` (degC), ``sequence_delay`` (s)
=====================  =====================================================
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .server import HrdsSimServer


class ControlApi:
    """Runs the HTTP API in a thread next to the simulator's event loop."""

    def __init__(
        self, sim: HrdsSimServer, loop: asyncio.AbstractEventLoop, host: str, port: int
    ) -> None:
        self.sim = sim
        self.loop = loop
        handler = type("Handler", (_Handler,), {"api": self})
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()

    def _run(self, coro) -> None:
        asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=10)

    def handle(self, path: str, body: dict) -> dict:
        sim, dev = self.sim, self.sim.device
        if path == "/reset":
            dev.reset()
            sim.reset_faults()
            self._run(sim.start())
        elif path == "/power_cycle":
            dev.power_cycle()
        elif path == "/offline":
            self._run(sim.stop())
        elif path == "/online":
            self._run(sim.start())
        elif path == "/clear_writes":
            dev.clear_write_log()
        elif path == "/alarm":
            if body.get("active", True):
                dev.raise_alarm(body["code"])
            else:
                dev.clear_alarm(body["code"])
        elif path == "/probe":
            if body.get("unplug"):
                dev.unplug_probe(int(body["address"]))
            else:
                dev.plug_probe(int(body["address"]), int(body["raw"]))
        elif path == "/force":
            for addr, raw in body.get("input", {}).items():
                dev.force_input(int(addr), None if raw is None else int(raw))
        elif path == "/set":
            for addr, raw in body.get("input", {}).items():
                dev.set_input(int(addr), int(raw))
            for addr, raw in body.get("holding", {}).items():
                dev.set_holding(int(addr), int(raw))
        elif path == "/fault":
            self._fault(body)
        elif path != "/state":
            raise KeyError(path)
        return {**dev.state(), "online": sim.online, "requests": sim.request_count}

    def _fault(self, body: dict) -> None:
        sim, dev = self.sim, self.sim.device
        if "illegal_addresses" in body:
            sim.illegal_addresses = {int(a) for a in body["illegal_addresses"]}
        if "reject_writes" in body:
            sim.reject_writes = {int(a) for a in body["reject_writes"]}
        if "ignore_writes" in body:
            dev.ignore_writes = {int(a) for a in body["ignore_writes"]}
        if "delay" in body:
            sim.delay = float(body["delay"])
        if "fc43" in body:
            sim.fc43 = bool(body["fc43"])
            sim.apply_identity()
        if "identity" in body:
            ident = body["identity"]
            sim.identity_override = (
                {int(k): str(v) for k, v in ident.items()} if ident else None
            )
            sim.apply_identity()
        if "pump_fault" in body:
            dev.set_pump_fault(bool(body["pump_fault"]))
        if "display_on" in body:
            dev.set_display_on(bool(body["display_on"]))
        if "fan_model" in body:
            dev.set_fan_model(body["fan_model"])
        if "water_temperature" in body:
            dev.set_water_temperature(float(body["water_temperature"]))
        if "sequence_delay" in body:
            dev.sequence_delay = float(body["sequence_delay"])


class _Handler(BaseHTTPRequestHandler):
    api: ControlApi

    def log_message(self, *_args) -> None:  # keep test output quiet
        pass

    def _reply(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, body: dict) -> None:
        try:
            self._reply(200, self.api.handle(self.path, body))
        except KeyError as exc:
            self._reply(404, {"error": f"unknown {exc}"})
        except Exception as exc:  # noqa: BLE001 - report to the test
            self._reply(400, {"error": repr(exc)})

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch({})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        self._dispatch(json.loads(raw or b"{}"))
