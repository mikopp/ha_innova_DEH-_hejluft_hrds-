# Real-device dumps (simulator seeds)

Each file here is the `--json` output of `tests/diagnose_hrds.py`, taken from
a real unit. The simulator (`tests/sim`) loads it as its register image and
FC 43 identity, and **every file is smoke-tested automatically** (setup, setup
writes, a dehumidify cycle) in `tests/ha/test_seeds.py` — no code change needed.

## Naming

`<model>_<display|headless>_<state>.json`, e.g.

* `hrds_30+_headless_factory_state.json` — HRDS+ 30 R, no display, as found
  before the integration ever wrote to it (PH01 = 1, PH02 = 0, HA00 = 2).

## Adding a device

```
pip install 'pymodbus>=3.13.1'
python3 tests/diagnose_hrds.py <host> --port <port> --unit <id> \
    --json tests/devices/hrds_50_display_running.json
```

The script is read-only (FC 03/04/43). It must cover the integration's block
plan; `tests/sim/test_device.py` fails on a dump that lacks the status
registers. Remove anything you do not want in the repository (the `host`
field holds the gateway address).

For setups without a dump yet, add an overlay in `tests/sim/overlays/`
instead. Two scenarios run today:

* **headless (real)**: the dump above, as is.
* **display (derived)**: `display_cnu2.json` patches that dump best-effort
  into a unit with a CNU2 display and its built-in room sensors (PH01 = 1,
  HA00 = 6, room readings instead of the sentinel). `tests/ha/test_display.py`
  and the climate *Auto* mode tests run on it. It is not a real dump: replace
  it with one when a display unit is available.

`display_with_probes.json` (display plus external probes on AI2/AI3) covers the
external-probe path.

## Run observations (`runs/`)

`runs/` holds what was seen while a real unit ran (timelines, delays, values
read from Home Assistant history), the data behind the `T` rows of
`doc/references/UNIT_BEHAVIOUR.md` §13. They are not register dumps, so they
live outside this folder's top level, which the seed tests load.
