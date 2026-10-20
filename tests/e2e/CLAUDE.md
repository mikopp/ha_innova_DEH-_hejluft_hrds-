# tests/e2e: only what needs a real Home Assistant

This directory is **deliberately small**. It runs the official Home Assistant
container with the integration installed from files, talks to it over
REST/websocket, and has simulated units on the host. Read `../CLAUDE.md` first.

## Before you add a test here
If the check can be done with `hass` inside pytest, it belongs in `../ha/`
and **not** here. Adding it here as well makes the CI slower and shows nothing
new. A test here must name what only the real container shows:

```python
@pytest.mark.needs_real_ha("persistence")  # one of the reasons in ../CLAUDE.md
def test_something(hl, restart_ha): ...
```
`conftest.py` rejects an unmarked test or an unknown reason at collection.
Start the module docstring with "Needs a real HA because: ...".

## What is here
| File | Reason | Checks |
|---|---|---|
| `test_install_and_flow.py` | `install-path`, `http-surface` | entry installed and loaded by HA, devices in the real registry, flow errors and the brine selector as JSON |
| `test_service_surface.py` | `http-surface` | service errors as codes, one real dry cycle |
| `test_real_time.py` | `real-time` | the entity follows the unit on the real scheduler |
| `test_restart.py` | `persistence`, `boot-order` | the restart contract with real container restarts |
| `test_zz_log_hygiene.py` | `runtime-logs` | the session's log is free of errors/deprecations from the integration (runs last) |

## Config
`pytest.ini` here configures `pytest tests/e2e` and replaces the root
`pyproject.toml` for this layer. The runner has neither pytest-asyncio nor the
Home Assistant plugins, so the root file's `asyncio_mode` would warn as an
unknown option. A new ini option for this layer goes in `pytest.ini`; one for the
in-process layer in `pyproject.toml`.

## How it works
* One container per session (`conftest.py::ha`), onboarded once. Two simulators
  on the host (`headless` for the main entry, `spare` for flow failures and
  throw-away entries). `hl` resets the headless unit and closes the gate before
  each test; tests must put back what they change (options, registry edits).
* `restart_ha(while_down=...)` stops and starts the container for real;
  `while_down` runs while it is stopped, so a test can change the unit without
  racing HA's polls. A restart costs 20-30 s: check as much as you can per
  restart.
* `ha_client.py` is a small REST/websocket client with a polling
  `assert_entity_state`. The sandbox has no internet, so other integrations
  HA sets up on its own log errors; the log test only looks at ours.
* `config/configuration.yaml` is minimal on purpose; `stage.py` copies it and
  `custom_components/innova_hrds` into a temporary `/config` (also used by the
  CI `check_config` step).
