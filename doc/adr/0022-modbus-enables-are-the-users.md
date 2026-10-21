---
status: accepted
date: 2026-10-21
decision-makers: mikopp
supersedes: [ADR-0003]
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/{climate,switch}.py"
---

# ADR-0022: The Modbus enables are the user's

## Decision

- The integration MUST NOT write PH02 (1778, on/off), PH28 (1870, DEU) or
  PH27 (1869, INT; key `enable_integration_bms`) on its own: not at setup,
  not on a poll. They are ordinary switches on the setup device.
- A request register counts only while its enable is on. Derived state
  (climate mode, `int_effect`, guards) MUST use `hub.modbus_enabled`,
  `hub.request_active` and `hub.unit_running`, never the raw request.
- `check_write_allowed` MUST refuse a write to a request whose enable is
  off, with the message in `MODBUS_DISABLED_MESSAGES` naming the switch.
- Turning on an enable while its request is latched MUST pass the same
  checks as starting that request (gate, brine guard, season).
- The enables are `PENDING_KEYS` (ADR-0024), so modes and checks follow a
  toggle at once.
- PG02 (1798) says whether the unit has INT at all; it MUST be shown
  read-only (`integration_available`), never written.
- Nothing is re-asserted after a power cycle: the unit keeps its settings.

## Context

The unit acts on a Modbus request only while its enable is on (handbook
6.1). Asserting the enables (ADR-0003) took the choice away from the user,
switched running display units off, and rested on a power-cycle loss the
reference unit does not show (`UNIT_BEHAVIOUR.md` §3.6, T7). With an enable
off the integration only observes that function, so it also works as a pure
monitor.

## Consequences

- Good: the user decides which functions Home Assistant may operate; adding
  the integration changes nothing on a running unit.
- Bad: after install, operating needs the enables switched on by hand (the
  README setup step 4 lists them).

## Confirmation

- `tests/ha/test_headless.py::test_modbus_enable_switched_off_stays_off`
- `tests/ha/test_headless.py::test_dehumidify_enable_off_refuses_dry_and_observes`
- `tests/ha/test_headless.py::test_request_latched_while_disabled_does_not_count`
- `tests/ha/test_headless.py::test_on_off_enable_off_keeps_the_side_the_unit_is_on`
- `tests/ha/test_headless.py::test_power_cycle_loses_nothing_and_writes_nothing`

## More information

PR #31 (PH27 is INT's enable, PG02 read-only), PR #41.
