"""Run a simulated HRDS+ as a process.

    python -m tests.sim --port 5020 --control-port 8020
    python -m tests.sim --port 5021 --control-port 8021 --overlay display_with_probes
    python -m tests.sim --list

Needs only ``pymodbus==3.13.1``. Point ``tests/diagnose_hrds.py`` or Home
Assistant at ``127.0.0.1:<port>``; drive faults through the control API
(see :mod:`tests.sim.control`).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .control import ControlApi
from .device import FAN_MODELS, HrdsDevice
from .seeds import DEFAULT_SEED, list_overlays, list_seeds
from .server import HrdsSimServer


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m tests.sim", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5020)
    parser.add_argument("--control-port", type=int, default=None)
    parser.add_argument("--seed", default=DEFAULT_SEED, help="device dump name")
    parser.add_argument("--overlay", action="append", default=[], help="repeatable")
    parser.add_argument("--fan-model", choices=FAN_MODELS, default="rescale")
    parser.add_argument("--sequence-delay", type=float, default=0.0)
    parser.add_argument("--list", action="store_true", help="list seeds and overlays")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


async def _main(args: argparse.Namespace) -> None:
    device = HrdsDevice(
        args.seed,
        tuple(args.overlay),
        fan_model=args.fan_model,
        sequence_delay=args.sequence_delay,
    )
    sim = HrdsSimServer(device, host=args.host, port=args.port)
    await sim.start()
    api = None
    if args.control_port:
        api = ControlApi(sim, asyncio.get_running_loop(), args.host, args.control_port)
        api.start()
    print(
        f"HRDS+ simulator {device.seed_name} on {args.host}:{args.port}"
        + (f", control API on :{args.control_port}" if api else ""),
        flush=True,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    if api:
        api.stop()
    await sim.stop()


def main() -> None:
    args = _parse()
    if args.list:
        print("seeds:   ", ", ".join(list_seeds()))
        print("overlays:", ", ".join(list_overlays()))
        return
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
