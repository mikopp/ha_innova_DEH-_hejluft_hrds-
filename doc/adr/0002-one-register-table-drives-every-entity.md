---
status: accepted
date: 2026-09-10
decision-makers: mikopp
topics: [entities]
paths:
  - "custom_components/innova_hrds/const.py"
  - "custom_components/innova_hrds/entity_common.py"
  - "custom_components/innova_hrds/{sensor,binary_sensor,switch,number,select,button}.py"
---

# ADR-0002: One register table drives every entity

## Decision

- MUST declare every Modbus-backed entity once, in `ENTITIES_DICT`
  (`const.py`). `init()` classifies the entries into the typed dicts
  (`SENSOR_TYPES`, `BINARY_TYPES`, ...); platform modules MUST build their
  entities from those dicts via `setup_platform_from_types()` and MUST NOT
  keep register lists of their own.
- MUST use the Modbus manual's `Addr DEC` (the PDU address) as `REG`;
  MUST NOT subtract 1.
- MUST use only `C_REG_TYPE_INPUT_REGISTERS` (FC 04) and
  `C_REG_TYPE_HOLDING_REGISTERS` (FC 03/06/16): the unit has no coils or
  discrete inputs, even 0/1 flags are analog registers.
- Composite entities (climate, fan) are declared in `init()`
  (`CLIMATE_TYPES` / `FAN_TYPES`); values not backed by a register go in
  `COMPUTED_SENSORS` / `COMPUTED_BINARY_SENSORS` and are written by the hub
  in `_compute_derived()`.
- A new platform MUST have both a module and an entry in `PLATFORMS`.
- Every `REG` MUST have a row in `doc/references/MODBUS_REGISTERS.md` and
  every key `en` and `de` translations.
- Per-entry state MUST live in `entry.runtime_data`, never in `hass.data`.

## Context

The HRDS+ exposes ~250 sparse analog registers. The sibling
`ha_comfoconnectpro` integration showed that one declarative table keeps
platforms generic. The failures this table has had: a `select` platform
declared without `select.py` produced no entities at all (fixed in the HA
2026.9 baseline), and `hass.data` keyed by the user-chosen name let two
entries clobber each other's hub.

## Consequences

- Good: an entity change is a table edit plus translations; no platform code.
- Bad: classification is implicit (`_classify`); a mis-shaped entry is
  silently another entity type unless the wiring check catches it.

## Confirmation

```sh
python3 tests/wiring_check.py
```

## More information

Initial commit `f6e4556`; select platform and `runtime_data`: `77f2aec`,
`c169cda`. How to add an entity: `.claude/rules/entities.md`.
