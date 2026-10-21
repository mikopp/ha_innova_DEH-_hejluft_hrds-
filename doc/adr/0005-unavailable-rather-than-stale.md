---
status: accepted
date: 2026-10-20
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/entity_common.py"
---

# ADR-0005: An entity is unavailable or unknown rather than stale

## Decision

- Register-backed entities MUST be unavailable while the last poll failed
  (`hub.last_update_success`) and while their key is missing from
  `hub.data`. The hub MUST notify listeners after a failed poll too.
- A register that stops answering (per-register fallback) MUST be popped
  from `hub.data`, never keep its last value.
- Entities without a key in `ENTITIES_DICT` (climate, fan, computed sensors)
  MUST take availability from poll health alone (the special case in
  `HubBackedEntity.available`); without it they are unavailable forever.
- An enum value the map does not know MUST decode to `None` (unknown) with a
  warning, never to an invented option.
- Setup MUST read the unit before creating entities (`ConfigEntryNotReady`
  when it does not answer), and entities MUST publish that primed read-back
  when added.

## Context

A dead gateway used to be indistinguishable from a healthy one: the hub kept
the previous values and templates gating on `has_value()` saw stale readings.
The availability fix then made the composite climate and fan entities
permanently unavailable, and later a single silent register kept its value
forever. Entities also sat at unknown for a whole scan interval after setup.

## Consequences

- Good: automations can trust a value; a lost link is visible at once.
- Bad: a flaky gateway shows unavailable gaps in history.

## Confirmation

- `tests/ha/test_failures.py::test_offline_goes_unavailable_and_recovers`
- `tests/ha/test_failures.py::test_a_register_that_stops_answering_goes_unavailable`
- `tests/ha/test_restart.py::test_boot_before_the_unit_is_reachable`
- `tests/wiring_check.py` "composite entities resolve availability correctly"

## More information

`77f2aec`, `c169cda` (composite availability), PR #16 (primed read-back),
PR #24 (stale register). No reading from an unwired probe: ADR-0011.
