---
status: accepted
date: 2026-10-21
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/translations/*.json"
---

# ADR-0026: A renamed or re-typed key is migrated in the entity registry

## Decision

- Renaming an entity key changes its unique id. The rename MUST add
  `(platform, old, new)` to `RENAMED_KEYS`; `_migrate_renamed_keys` moves
  the registry entry at setup so history is kept, and an entity id still
  carrying the old key follows the new one unless that id is taken.
- An entity that changes platform under the same unique id (e.g. HA02/HA03
  numbers → selects) MUST have its orphaned registry entry removed at setup.
- A rename that changes entity ids MUST be noted as breaking in
  `CHANGELOG.md`.

## Context

Keys follow the register they read: 1139 is the integration (INT) request,
which heats in winter, so `active_cooling` became `integration_request`
(PR #37), and PH27's switch became `enable_integration_bms` (PR #31). Without
a migration users lose history and get a duplicate entity.

## Consequences

- Good: renames keep history and most automations.
- Bad: `RENAMED_KEYS` only grows.

## Confirmation

- `tests/ha/test_restart.py::test_renamed_setup_switches_are_migrated`
- `tests/ha/test_restart.py::test_active_cooling_keys_become_integration`
- `tests/ha/test_headless.py::test_old_probe_numbers_are_removed`

## More information

PR #30 (probe numbers → selects), PR #31, PR #37.
