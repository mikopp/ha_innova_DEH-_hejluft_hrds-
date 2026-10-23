---
status: accepted
date: 2026-10-23
decision-makers: mikopp
topics: [requests, state]
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/switch.py"
---

# ADR-0024: Request switches show the command until the unit confirms it

## Decision

- For `PENDING_KEYS` (unit on/off, dehumidify, integration request and the
  three Modbus enables) the hub MUST keep the commanded value in `hub.data`
  after a write (`_pending`), and keep showing it over polls that read the
  old value.
- It MUST re-read only the pending registers at `PENDING_RECHECK_SECONDS`
  (3, 6, 12, 25 s; `_async_verify_pending`, never a full cycle), drop the
  entry as soon as the read-back agrees, and after the last re-read let the
  unit's value stand and log a warning.
- Fan and climate MUST NOT be pending: they report what the unit does
  (ADR-0006, ADR-0034).
- Unload MUST cancel the pending re-reads.

## Context

A real unit mirrored a request into its register late: OFF read back as ON
for several polls and the switch flicked back. The enables are pending too
so that the offered climate modes and the write checks follow a toggle at
once (ADR-0022).

## Consequences

- Good: a switch does not flick back while the unit catches up.
- Bad: for up to 25 s a switch can show a command the unit then refuses;
  the warning and the fall-back to the unit's value cover it.

## Confirmation

- `tests/ha/test_write_lag.py::test_switch_follows_the_command_while_the_unit_lags`
- `tests/ha/test_write_lag.py::test_unconfirmed_request_falls_back_to_the_units_value`
- `tests/ha/test_write_lag.py::test_fan_is_not_pending_but_enables_are`
- `tests/ha/test_write_lag.py::test_unload_drops_a_pending_request`

## More information

PR #32; enables added in PR #41. Sizing the schedule from real lag:
`plans/todo.md` "Request read-back lag".
