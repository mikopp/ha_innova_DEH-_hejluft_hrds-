---
status: accepted
date: 2026-10-20
decision-makers: mikopp
topics: [tests]
paths:
  - "tests/**"
  - ".github/workflows/{tests,e2e}.yaml"
---

# ADR-0019: Tests run the real client against a simulated unit; e2e only for what needs a real Home Assistant

## Decision

- Tests MUST exercise the integration's own pymodbus client, block plan,
  decoding, guards and writes against `tests/sim`, a simulated HRDS+ that
  speaks Modbus TCP. MUST NOT mock the Modbus client.
- The simulator MUST NOT import the integration: addresses come from
  `MODBUS_REGISTERS.md` (`sim/registers.py`), behaviour from
  `UNIT_BEHAVIOUR.md` (`sim/device.py`), so a wrong address fails a test
  instead of being copied. Device behaviour not confirmed on hardware MUST
  be a switchable hypothesis (e.g. `fan_model`), not a guess.
- A test MUST go in `tests/ha` (real HA core in-process). It MAY go in
  `tests/e2e` only when an in-process HA cannot show it, marked
  `@pytest.mark.needs_real_ha("<reason>")` with a reason from
  `REAL_HA_REASONS` (install-path, http-surface, real-time, persistence,
  boot-order, runtime-logs, ha-drift). MUST NOT repeat an in-process
  scenario in e2e.
- The restart contract in `tests/CLAUDE.md` MUST hold in both layers.
- Coverage of the in-process run MUST stay at or above 90 %.

## Context

Projects in the survey (`plans/ci.md`) mock the client, so framing,
timeouts, exception replies and reconnects are never exercised, yet this
integration's logic depends on the unit's reactions. The first e2e layer
repeated about 34 of its 40 tests in-process and found no bug of its own;
reducing it to what needs the container cut it from 6 to 2.5 minutes.

## Considered options

- Mocked pymodbus (`AsyncMock`, as HA core `modbus`): cheap, blind to
  transport bugs; three such bugs were found by the simulator (PR #16).
- Every scenario in both layers: doubles runtime, finds nothing new.

## Consequences

- Good: transport, guards and restarts are tested as they run.
- Bad: the simulator is a model of documents and one dump; it can be wrong
  the same way the integration is.

## Confirmation

`tests/e2e/conftest.py` rejects an e2e test without a known reason; the
simulator imports nothing from the integration; the coverage gate is set:

```sh
grep -q "REAL_HA_REASONS" tests/e2e/conftest.py
! grep -rnE "^(from|import) .*(custom_components|innova_hrds)" tests/sim/
grep -q -- "--cov-fail-under=90" .github/workflows/tests.yaml
```

## More information

PR #16 (simulator, two layers), PR #23 (layering rule, restart contract).
How-to: `tests/CLAUDE.md`.
