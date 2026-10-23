---
status: accepted
date: 2026-10-23
decision-makers: mikopp
topics: [requests]
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/{switch,climate}.py"
---

# ADR-0012: Operational requests need the user's go-ahead

## Decision

- A non-zero write to an `OPERATIONAL_KEYS` register (unit on/off,
  dehumidify, integration request) MUST be refused until
  `switch.allow_operational_requests` (`hub.operation_allowed`) is on. The
  gate never refuses switching something off (a disabled Modbus enable
  still can, ADR-0022).
- The gate MUST default to off. It is a `RestoreEntity` and MUST restore
  only a state stored with its own unique id (a re-added entry reuses the
  entity id); a state without an owner closes the gate once.
- Every request MUST go through `write_entity_value` → `check_write_allowed`
  (Modbus enables, request guards, gate). MUST NOT add a request path that
  skips it. A change that writes several registers MUST check every write
  before the first (ADR-0025).

## Context

After install the unit's setup is unknown (display priority, probes, time
programs, remote contact, water circuit). A request sent before the user has
reviewed the setup device can start a compressor on a misconfigured
installation. Home Assistant restores state by entity id, so a re-added
entry inherited an open gate until the owner check (PR #24).

## Consequences

- Good: nothing makes the unit act until the user says so, also after a
  re-add.
- Bad: one extra step after install; the README walks through it.

## Confirmation

- `tests/ha/test_headless.py::test_gate_refuses_requests_and_starts_nothing`
- `tests/ha/test_restart.py::test_gate_defaults_off_and_is_restored`
- `tests/ha/test_restart.py::test_gate_of_another_entry_is_not_restored`
- `tests/ha/test_restart.py::test_gate_stored_before_it_had_an_owner_is_closed`
- `tests/e2e/test_service_surface.py::test_gate_refusal_is_a_service_validation_error`

## More information

PR #15 (gate), PR #24 (owner), PR #36 / #37 (precheck of multi-write modes).
