---
status: accepted
date: 2026-10-21
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/{climate,fan,switch,number,select}.py"
---

# ADR-0023: Write only what changes (EEPROM)

## Decision

- MUST NOT add a periodic or unconditional write. The only automatic write
  is the conditional, capped headless sync of ADR-0010.
- `_write_registers` MUST read the register first and skip a write the unit
  already holds. The exception is a `PENDING_KEYS` request that is still
  pending: its read-back may lag the last command, so it is written.
- A restart, a reload or a power cycle of a unit that kept its settings
  MUST write nothing.
- SHOULD NOT toggle installer or I/O parameters (HC/HD/HA) per operating
  cycle from automations or code.

## Context

The unit keeps its parameters in EEPROM, which wears with every write; the
write-cycle limit is undocumented (`UNIT_BEHAVIOUR.md` §3.6). Before PR #39,
every service call wrote its registers even when unchanged, so an automation
repeating a mode wore the EEPROM, and every setup rewrote all required
settings.

## Consequences

- Good: steady state and restarts cost no writes.
- Bad: one extra read per write.

## Confirmation

- `tests/ha/test_headless.py::test_same_value_again_writes_nothing`
- `tests/ha/test_headless.py::test_polling_writes_nothing_while_the_unit_keeps_its_settings`
- `tests/ha/test_restart.py::test_restart_leaves_a_running_unit_alone`
- `tests/ha/test_restart.py::test_restart_together_with_a_unit_power_cycle`
- `tests/e2e/test_restart.py::test_running_unit_is_untouched_and_polling_resumes`

## More information

PR #39, merged with PR #41. Where writes may happen at all: ADR-0006.
