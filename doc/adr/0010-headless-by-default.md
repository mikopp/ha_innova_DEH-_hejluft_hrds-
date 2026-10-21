---
status: accepted
date: 2026-10-21
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/config_flow.py"
---

# ADR-0010: Headless by default; PH01 and HA00 are the only settings written unasked

## Decision

- The `has_display` option (default off) says whether a CNU2 display is
  fitted; no register reports that.
- Without a display the hub MUST keep PH01 (1777) = 0 and HA00 (1803) = 0
  (`HEADLESS_SETTINGS`). These are the only registers the integration
  writes on its own. With `has_display` on it MUST leave them alone.
- `_sync_required_settings_locked` MUST judge them on the same poll's
  read-back, write only one that was read and reads wrong, read the poll
  again after a write, and stop after `REQUIRED_SETTING_MAX_WRITES` (3)
  polls in a row until it reads back right or the entry reloads.
- The sync is configuration, not a request: it writes through the client
  directly and is not subject to the operation gate (ADR-0012).
- A headless unit that still reads `off_by_display` after the settings hold
  MUST be reported (`unit_waiting_for_first_on`), not written to.

## Context

Without a display, PH01 = 1 keeps the unit OFF by display forever (an OFF
from any source beats a Modbus ON), and HA00 ≠ 0 makes it wait for room T/H
from a display that is not there (handbook 5.1). The unit keeps both across
a power cycle (`UNIT_BEHAVIOUR.md` §3.6, T7), so in steady state the sync
writes nothing; it only repairs a setting changed elsewhere. After PH01 = 0
the real unit still read `off_by_display` until the first Modbus ON (T7).

## Consequences

- Good: a headless unit works without the user knowing PH01/HA00.
- Bad: a user who sets PH01 = 1 on a headless unit has it reset; the
  matching setup switch says so.

## Confirmation

- `tests/ha/test_headless.py::test_first_connect_writes_required_settings`
- `tests/ha/test_headless.py::test_headless_setting_the_unit_does_not_keep`
- `tests/ha/test_headless.py::test_polling_writes_nothing_while_the_unit_keeps_its_settings`
- `tests/ha/test_headless.py::test_headless_unit_stuck_off_by_display_says_how_to_start_it`
- `tests/ha/test_display.py::test_display_settings_left_alone`

## More information

PR #15 (headless), PR #31 (`unit_waiting_for_first_on`), PR #39 / #41
(same-poll judgement, cap). Write budget: ADR-0023. Enables: ADR-0022.
