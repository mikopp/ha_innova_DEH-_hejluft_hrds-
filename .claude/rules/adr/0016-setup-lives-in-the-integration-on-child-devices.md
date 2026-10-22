---
status: accepted
date: 2026-10-20
decision-makers: mikopp
topics: [entities, config]
paths:
  - "custom_components/innova_hrds/const.py"
  - "custom_components/innova_hrds/entity_common.py"
---

# ADR-0016: Setup lives in the integration, on a linked setup device

## Decision

- Setup MUST be possible from Home Assistant after connect: the
  `setup_check` sensor (`ok` / `attention`) with its issue list and `to_fix`
  attribute, derived from the read-back by `_compute_setup_issues`. Issues
  MUST be attributes of that sensor, not one entity per issue.
- Each entity key MUST be in at most one of `SETUP_KEYS` (on the `-setup`
  child device), `CONFIG_KEYS`, `DIAGNOSTIC_KEYS` (entity categories via
  `entity_category_for`); in none, it is operational on the main device.
- Child devices (`SETUP_DEVICE_SUFFIX`, `INSTALLER_DEVICE_SUFFIX`) MUST be
  registered in `async_setup_entry`, parent first, and linked with
  `via_device_id` (not the deprecated `via_device`).
- `unique_id` MUST be `<entry_id>-<key>`, so moving a key between devices
  keeps the entity and its history.

## Context

The first bring-up showed that a headless unit needs a dozen settings
reviewed (display priority, probes, enables, time programs, remote contact)
before it is safe to operate; a plain entity list buried them. Per-issue
problem sensors were tried in PR #31 and reverted to one sensor with
attributes.

## Consequences

- Good: the main device stays an operating surface; the setup device is a
  checklist.
- Bad: three devices per unit.

## Confirmation

- `tests/ha/test_config_flow.py::test_setup_and_installer_devices_hang_off_the_main_device`
- `tests/ha/test_headless.py::test_setup_check_lists_real_issues_until_fixed`
- `tests/wiring_check.py` "setup / config / operation grouping and gate"

## More information

PR #15 (setup device, gate), PR #23 (`via_device_id`), PR #31 (issues as
attributes). The gate itself: ADR-0012. The installer device: ADR-0017.
