"""Real-device register dumps (seeds) and overlays for the simulator.

A *seed* is the ``--json`` output of ``tests/diagnose_hrds.py`` taken from a
real unit and stored in ``tests/devices/<model>_<display|headless>_<state>.json``.
Every file there is picked up automatically: the smoke tests run once per seed.

An *overlay* (``tests/sim/overlays/<name>.json``) patches a seed, for setups we
have no dump of yet (e.g. a unit with display and room probes)::

    {"description": "...", "input": {"499": 225}, "holding": {"1805": 45},
     "meta": {"display": true}}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEVICES_DIR = Path(__file__).resolve().parent.parent / "devices"
OVERLAYS_DIR = Path(__file__).resolve().parent / "overlays"
DEFAULT_SEED = "hrds_30+_headless_factory_state"


@dataclass
class Seed:
    """Register image and identity of one device."""

    name: str
    input: dict[int, int]
    holding: dict[int, int]
    identity: dict[int, str]
    unit: int = 1
    meta: dict = field(default_factory=dict)


def list_seeds() -> list[str]:
    """Names of all device dumps in ``tests/devices``."""
    return sorted(p.stem for p in DEVICES_DIR.glob("*.json"))


def list_overlays() -> list[str]:
    return sorted(p.stem for p in OVERLAYS_DIR.glob("*.json"))


def _int_keys(mapping: dict) -> dict[int, int]:
    return {int(k): int(v) & 0xFFFF for k, v in mapping.items()}


def load_seed(name: str = DEFAULT_SEED, overlays: tuple[str, ...] = ()) -> Seed:
    """Load a device dump and apply overlays in order."""
    path = DEVICES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"no device dump {path} (have: {list_seeds()})")
    dump = json.loads(path.read_text())

    snapshot = dump.get("snapshot", {})
    inputs = _int_keys(snapshot.get("input", {}))
    holding = _int_keys(snapshot.get("holding", {}))
    # Registers read outside the snapshot areas ("4:1583", "3:1105", ...).
    for key, raw in dump.get("registers", {}).get("_raw", {}).items():
        fc, addr = key.split(":")
        (inputs if fc == "4" else holding).setdefault(int(addr), int(raw) & 0xFFFF)

    ident = dump.get("identity", {}).get("fc43_basic") or {}
    seed = Seed(
        name=name,
        input=inputs,
        holding=holding,
        identity={int(k): str(v) for k, v in ident.items()},
        unit=int(dump.get("unit", 1)),
    )
    for overlay in overlays:
        apply_overlay(seed, overlay)
    return seed


def apply_overlay(seed: Seed, overlay: str) -> None:
    data = json.loads((OVERLAYS_DIR / f"{overlay}.json").read_text())
    seed.input.update(_int_keys(data.get("input", {})))
    seed.holding.update(_int_keys(data.get("holding", {})))
    seed.meta.update(data.get("meta", {}))
    seed.name = f"{seed.name}+{overlay}"
