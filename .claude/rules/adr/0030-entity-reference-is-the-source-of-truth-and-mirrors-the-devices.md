---
status: accepted
date: 2026-10-22
decision-makers: mikopp
topics: [entities, docs]
paths:
  - "custom_components/innova_hrds/const.py"
  - "custom_components/innova_hrds/entity_common.py"
  - "custom_components/innova_hrds/installer_params.py"
  - "custom_components/innova_hrds/translations/*.json"
  - "doc/entity-reference.md"
---

# ADR-0030: The entity reference is the one source of truth and mirrors the devices

## Decision

- `doc/entity-reference.md` MUST be the only place that lists entities. The
  README, `CLAUDE.md` and other docs MUST link to it and MUST NOT restate its
  rows (extends ADR-0027).
- A change that adds, removes, renames or moves an entity, changes its device
  or group (`SETUP_KEYS`, `CONFIG_KEYS`, `DIAGNOSTIC_KEYS`, `INSTALLER_KEYS`,
  `INSTALLER_DEVICE_EXTRA_KEYS`), its register, or what it shows MUST update
  the reference in the same commit.
- The reference MUST be organised like the devices: *Main device* (with
  *Operational*, *Configuration* and *Diagnostic* sections, as
  `entity_category_for` assigns them), *Setup device*, *Installer device*.
  Each device section MUST say why the device exists and why it is separate
  (ADR-0016, ADR-0017); a new device or group needs that explanation first.
- Every entity except the generated installer parameters MUST be listed exactly
  once, in a table row whose first cell is `` `platform.key` ``, under the
  device and group `device_info_for` puts it on. A row for something that is
  not an entity MUST NOT exist.
- Installer parameters (`INSTALLER_KEYS`) MUST NOT be listed one by one: they
  are generated from `installer_params.py` and listed in
  `doc/references/MODBUS_REGISTERS.md` §16.
- `tests/wiring_check.py` MUST fail when the reference and the code differ
  (missing, unknown, duplicated or misplaced entity), and when the README
  holds an entity table.

## Context

The README's entity reference was organised by platform, not by device, so
setup entities were scattered over the sensor, switch and select tables; two
entities were listed twice and one was listed under its display name instead
of its key. Nothing connected it to `const.py`. The prose (probe notes, why a
device exists) cannot be generated, but the list of entities and their device
can be checked, so the file stays hand-written and the check keeps it honest.

## Considered options

- Generate the file from `const.py` and the translations: rejected, the notes
  and the reasons per device would be lost.
- Keep the reference in the README: rejected, about 190 lines in the page that
  users also read for installation and concepts, and the German README would
  have had to carry or skip it.

## Consequences

- Good: one place to look, one place to edit; a forgotten update fails CI.
- Bad: every entity change touches a second file; a pure description change
  is not detected by the check (the rule above covers it).

## Confirmation

- `tests/wiring_check.py` "entity reference matches the code"

```sh
test -f doc/entity-reference.md
! grep -qE '^\| `(sensor|binary_sensor|switch|number|select|fan|climate|button)\.' README.md
```

## More information

Devices: ADR-0016 (setup device), ADR-0017 (installer device). One home per
topic: ADR-0027. How to add an entity: `.claude/rules/entities.md`.
