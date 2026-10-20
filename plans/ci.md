# CI for innova_hrds — analysis and decision (2026-10-20)

## 1. How other integrations that steer complex devices test

| Project | CI | How the device is faked | Notes |
|---|---|---|---|
| HA core `modbus` | core CI (ruff, mypy, hassfest, pytest) | pymodbus clients patched with one `AsyncMock`; reads return fixed `registers` | time driven with `async_fire_time_changed`; parametrized error injection |
| HA core `nibe_heatpump` | core CI | hand-written stateful `MockConnection` (coil dict) | syrupy snapshots after each state change — closest to our needs |
| HA core `airzone`, `daikin` | core CI | library API patched to return JSON fixtures | `snapshot_platform` per platform |
| WillCodeForCats/solaredge-modbus-multi | `tests.yml` (py 3.14), hassfest, hacs, CodeQL; SHA-pinned actions | `SimpleNamespace` fakes + `AsyncMock` writes | ~30 focused unit-level files (flows, repairs, write errors) |
| andrew-codechimp/HA-Battery-Notes | lint, validate, tests (uv) | phcc fixtures | pins `homeassistant` and phcc together |
| alandtse/tesla, alexa_media_player | hacs, hassfest, pytest + Coveralls | library mocked | coverage reported, no threshold |
| wlcrs/huawei_solar | hacs only | tests live in the library (tmodbus) | "thin integration, tested library" |
| ludeeus/integration_blueprint | hassfest, hacs, ruff; nightly | none | template for SHA pins / nightly |
| binsentsu solaredge, mkaiser Sungrow | none useful | — | — |

Observations:

* Nobody runs a **real Modbus server**: the client is mocked, so framing,
  timeouts, exception replies and reconnects are never exercised. For this
  device the logic depends on the unit's *reaction* (enables that make writes
  stick, status that follows requests), which bare mocks cannot express.
* No project runs Home Assistant **in Docker** in CI; no maintained action exists.
* Good practice worth copying: SHA-pinned actions, `permissions: read`,
  hassfest + HACS nightly, phcc pinned to one HA release and bumped with it,
  snapshots for entity state, coverage reporting.

## 2. What the homeassistent-config repo does (read-only, borrowed patterns)

* `ha_integration_test_harness` (pinned SHA) starts **one real HA container**
  per pytest session (`docker compose up -d --wait`), onboards a user, and
  tests talk to it over REST/websocket only; `assert_entity_state` polls.
* HA version pinned via `.github/ha-versions/ha/Dockerfile` (Dependabot), the
  image pulled in the background while Python installs, `check_config` before
  the tests, `requests` default-timeout shim, `pytest-timeout
  --timeout-method=thread`, results in the job summary.
* It has **no fake devices**: integrations missing in CI are replaced by
  writing states over REST, so service calls to them do nothing.

Borrowed: everything in the second bullet, the one-HA-per-session model and the
polling assert. Not borrowed: the harness package itself (its compose file
hardcodes the image and AppDaemon and has no place for a device simulator).

## 3. Decision

A simulated HRDS+ (`tests/sim`) that speaks real Modbus TCP and reacts like the
documented device, used by two layers:

1. **`tests.yaml`** — real HA core in-process (phcc, latest HA release) +
   the integration's real pymodbus client + simulator. ~1 min, coverage ≥ 90 %.
2. **`e2e.yaml`** — the official HA container (latest release; nightly also
   `beta`), simulators as host processes steered by an HTTP control API, the
   config flow and every service call through REST/websocket.

Plus the existing `lint.yaml` (now also `wiring_check.py`), `hassfest.yaml`,
`hacs.yaml`; `release.yaml` runs both test workflows.

Scenarios: headless setup (setup writes, setup check, self-heal after power
cycle, hidden setpoints), operation gate, dehumidify, active cooling, winter
heating / refusals, brine guard, fan speeds under three firmware hypotheses,
failures (offline, slow link, bad address, rejected write, AL11/AL12/AL22/AL25,
probe faults, water circuit), and a unit with display and room probes.

## 4. Bugs the new tests found (fixed)

* Entities ignored the primed read at setup: everything was `unknown` for the
  first scan interval.
* A slow gateway made pymodbus hand late replies to the next request; blocks
  decoded each other's registers (a running unit showed `off_by_display`).
* The debounced post-write refresh survived unload.

Open (xfail in `tests/ha/test_seeds.py`): the climate entity offers COOL on a
unit without active cooling (PG02 = 0).

## 5. Layering decision (2026-10-20)

The first version ran every scenario in both layers. After it ran, the e2e
layer had found no bug of its own and about 34 of its 40 tests repeated
`tests/ha`. Decision: the in-process layer is the default; the real container
only holds what an in-process HA cannot show, and each test says why
(`needs_real_ha`, enforced at collection). Reasons: install path, HTTP/JSON
surface, real scheduler, persistence over real restarts, boot order, runtime
log. The restart contract (the initial setup survives a restart) is checked in
both layers, from different sides: the code's behaviour on a fresh start
in-process, the state coming back from disk after a real boot in e2e. Details:
`tests/CLAUDE.md`.
