# Tests: read this before adding one

Two layers run the integration against one **simulated HRDS+** (`sim/`) that
speaks real Modbus TCP. The integration's own pymodbus client, block plan,
decoding, guards and writes all run for real; only the device is fake.

| Layer | Where | What it is | Cost |
|---|---|---|---|
| **In-process** (default) | `ha/` | The real Home Assistant core inside pytest (`pytest-homeassistant-custom-component`) | about 1 min, measures coverage |
| **Real HA** | `e2e/` | The official Home Assistant container, driven over REST/websocket | about 2.5 min, needs Docker |
| Device model | `sim/test_device.py` | The simulator on its own | seconds |
| Consistency | `wiring_check.py` | Register map, translations, platforms; no HA installed | seconds |
| Release script | `test_release_script.py` | `scripts/release.py` on temporary files (ADR-0031, ADR-0032) | seconds |

## Where does my new test go?

The rule and its reasons are ADR-0019 (it loads with any file here):
in-process by default, the real container only for what it alone can show.

1. Behaviour of the integration given a unit state (entities, services, guards,
   alarms, fan, climate, flows' logic)? → `ha/`.
2. Needs a real container? → `e2e/`, marked
   `@pytest.mark.needs_real_ha("<reason>")` with a reason from
   `REAL_HA_REASONS` in `e2e/conftest.py` (each says what only the container
   shows). Never a copy of an in-process scenario.
3. Behaviour of the fake device itself? → `sim/test_device.py`.
4. Register map, translations, platforms? → `wiring_check.py`.
5. ADR format and scopes? → `adr_check.py`.

## The restart contract

The initial setup must survive a restart. After Home Assistant restarts, with
any state of the unit:

| # | Contract | In-process (`ha/test_restart.py`) | Real restart (`e2e/test_restart.py`) |
|---|---|---|---|
| 1 | What the user configured is still in force: options (a cleared brine sensor stays cleared), the *Allow operational requests* gate, registry edits (rename, enabled installer entity), entity and device ids | `test_options_are_authoritative_after_restart`, `test_gate_defaults_off_and_is_restored`, `test_restored_gate_allows_requests_straight_away`, `test_user_registry_changes_are_kept` | `test_setup_survives_restart` |
| 2 | Nothing the unit is doing is disturbed: the first poll writes only headless settings the unit lost (none, if it kept them), never on/off, requests or fan | `test_restart_leaves_a_running_unit_alone`, `test_restart_keeps_season_and_fan_band` | `test_running_unit_is_untouched_and_polling_resumes` |
| 3 | HA booting before the unit is reachable ends loaded by itself | `test_boot_before_the_unit_is_reachable` | `test_ha_booting_before_the_unit_is_reachable` |
| 4 | Restart together with a unit power cycle: the unit loses nothing, so nothing is written and control works at once | `test_restart_together_with_a_unit_power_cycle` | `test_restart_together_with_a_unit_power_cycle` |
| 5 | Derived state comes back identical (setup check, hidden setpoints, brine guard, modes) | `test_every_entity_comes_back_identical` | (ids checked in contract 1) |

"Restart" in-process means unload and set up the entry again on fresh hub
state with the same registries. That proves the code. That the state really
comes back from disk after a real boot is the e2e column.

## What no layer tests
The Home Assistant frontend (names, categories, device pages as a user sees
them), interplay with other integrations (recorder, automations), RTU/serial
gateways, and real hardware. The device model's rules come from
`doc/references/UNIT_BEHAVIOUR.md`, `doc/references/MODBUS_REGISTERS.md` and one real
dump, not from hardware: run
`tests/diagnose_hrds.py` (read-only) against a unit to check the model.

## Bring-up diagnostic (`diagnose_hrds.py`)
`python3 tests/diagnose_hrds.py <host> [--port N] [--unit N] [--json FILE]`
reads a real unit (FC 03/04/43 only, it never writes) before the integration
is installed: identification, connected probes, settings to review, and what
the integration would write on first connect. It reuses `const.py` and the
block plan; keep its `build_blocks` in sync with `_build_blocks` (ADR-0018).
Needs only `pip install 'pymodbus>=3.13.1'`. Its `--json` output is a
simulator seed (`devices/README.md`).

## Running
```
# in-process + model + consistency (fresh venv; Python 3.14)
pip install -r requirements_test.txt
pytest tests/sim tests/ha tests/test_wiring.py tests/test_release_script.py

# real HA (needs Docker; logs in tests/e2e/.artifacts/)
pip install -r tests/e2e/requirements.txt
pip install "pymodbus==<the version the image's HA ships>"   # for the simulator
pytest tests/e2e -p no:homeassistant
```
`tests/e2e/requirements.txt` does not list `pymodbus` on purpose: the simulator
on the host must run the pymodbus Home Assistant ships, so `e2e.yaml` reads it
from the image's modbus manifest and installs that. A bare `pytest` skips
`tests/e2e`. `HRDS_E2E_IMAGE` overrides the pinned HA image
(`.github/ha-versions/Dockerfile`).

## The simulator (`sim/`)
* It does **not** import `const.py`: addresses come from
  `doc/references/MODBUS_REGISTERS.md` (`sim/registers.py`) and behaviour from
  `doc/references/UNIT_BEHAVIOUR.md` (`sim/device.py`). A wrong address in the
  integration then fails a test instead of being copied. When the device docs
  change, change the model.
* **Seeds** are real-device dumps in `devices/<model>_<display|headless>_<state>.json`
  (`diagnose_hrds.py --json` output). Every file there is smoke-tested
  automatically (`ha/test_seeds.py`). **Overlays** (`sim/overlays/`) patch a seed
  for a setup without a dump yet (display with probes, non-R, no DC).
  `display_cnu2` is the display scenario: the real headless dump turned
  best-effort into a CNU2 unit with built-in room sensors. `ha/test_display.py`
  and the climate *Auto* tests run on it; nothing about a real display unit is
  verified.
* The unit keeps every register across `power_cycle()` (a real unit kept
  PH01/HA00/PH02, `doc/references/UNIT_BEHAVIOUR.md` §3.6). Modbus requests
  count only with their PH02/PH28/PH27 enable (§3.3).
* The model ORs the unit's automatic requests with the Modbus ones: DEU from
  the room humidity (PU01/PU07, a display with H or an AI3 probe) and INT from
  the room temperature (summer above SEtC + PF12, winter below SEtH − PF12 with
  SEtH clamped to PH09..PH10; a display or an AI2 probe, PG02).
* The fan runs at the unit's own manual request (PM20), clamped into the
  active band as seen on hardware (T22–T28): a raised minimum raises it, a
  lowered one leaves it, 0 when the request ends. A PM20 write is acknowledged
  and not kept; one outside the band answers exception 04. `run_on` (s, 0 by
  default) keeps a fan that was running in Wait OFF at PF26 after the request
  (T19); `set_fan_fault()` puts it in Alarm.
* `python -m tests.sim --port 5020 --control-port 8020` runs it as a process;
  the HTTP control API (`sim/control.py`) injects alarms, probe faults, a power
  cycle, offline, slow replies, rejected writes, a wrong identity.
* `HrdsSimServer.max_count` models a gateway overloaded by large reads: a read
  of more registers never gets an answer (`oversized_reads` counts them), and
  `read_log` records every read request, so a test can assert which registers
  were asked for (e.g. that the poll never touches the installer menu).

## Guards
* In-process: any test during which HA logs a deprecation naming this
  integration fails (`ha/conftest.py`), and a `DeprecationWarning` raised in
  `custom_components` is an error (`pyproject.toml`).
* Real HA: `e2e/test_zz_log_hygiene.py` reads the container log of the whole
  session, restarts included, and fails on errors, tracebacks and deprecations
  from the integration (a short allowlist covers errors the tests cause on
  purpose).
* Version alignment (`ha/test_versions.py`, ADR-0004): Dependabot bumps the
  two layers in separate PRs, so bump `requirements_test.txt` and
  `.github/ha-versions/Dockerfile` together; never `pymodbus` alone.
* Snapshots (`ha/snapshots/`): `pytest tests/ha/test_seeds.py --snapshot-update`,
  then review the diff.

## CI
`tests.yaml` runs `sim`, `ha`, `test_wiring` and `test_release_script` (coverage gate 90 %);
`e2e.yaml` runs `e2e` (nightly also against the HA `beta` image, allowed to
fail); `release.yaml` runs both on the tagged commit before packaging. Triggers
and branch protection: ADR-0020.
