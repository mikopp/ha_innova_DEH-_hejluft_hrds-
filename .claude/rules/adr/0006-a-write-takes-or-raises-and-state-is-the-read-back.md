---
status: accepted
date: 2026-10-21
decision-makers: mikopp
topics: [modbus-writes, state]
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/entity_common.py"
  - "custom_components/innova_hrds/{switch,number,select,fan,climate}.py"
---

# ADR-0006: A write takes or raises, and state is the unit's read-back

## Decision

- Every write MUST go through `hub.write_entity_value()` (entities via
  `setter_function_callback`). The only other write is the headless sync of
  ADR-0010, in `_sync_required_settings_locked`.
- `write_entity_value` MUST raise `HomeAssistantError` when the unit does not
  acknowledge a write, and `ServiceValidationError` for a read-only register
  or a refused request. A refused write MUST NOT look like success.
- After a write the hub MUST schedule the debounced refresh
  (`async_schedule_refresh`), or for an installer register read back just
  that register (ADR-0017); never an immediate full poll.
- Entity state MUST come from the read-back. Entities MUST NOT set
  optimistic state; the only exception is the pending request command of
  ADR-0024.

## Context

`_write_registers` once returned `None` on every path, so a rejected write
looked like success. An immediate poll after each write read the pre-write
value, clobbered state, and cost three full cycles per HVAC mode change.
The unit does not always adopt a value verbatim (fan, ADR-0008), so an
optimistic state would show numbers the unit never took.

## Consequences

- Good: what Home Assistant shows is what the unit holds; failures surface
  as service errors.
- Bad: a change shows up one debounce (1.5 s) or one poll later.

## Confirmation

- `tests/ha/test_failures.py::test_rejected_write_raises`
- `tests/e2e/test_service_surface.py::test_rejected_write_is_a_home_assistant_error`
- `tests/ha/test_fan.py::test_no_optimistic_update_before_poll`

Writes exist only in the hub (`_write_registers`, `_sync_required_settings_locked`):

```sh
test "$(grep -c 'write_register(' custom_components/innova_hrds/__init__.py)" -eq 2
! grep -l 'write_register(' custom_components/innova_hrds/*.py | grep -v '/__init__.py$'
```

## More information

`77f2aec` (writes raise, debounced refresh), `b1ca765` (no optimistic fan).
Write-only-what-changes: ADR-0023.
