---
status: accepted
date: 2026-10-19
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/climate.py"
---

# ADR-0011: No probe means no reading and no target

## Decision

- An INT16 word in `PROBE_SENTINEL_LOW..PROBE_SENTINEL_HIGH` (unwired input,
  `0x8004` seen) MUST decode to `None` in `_decode_all`: the entity is
  available and unknown, never about -3276 °C.
- The climate `current_temperature` / `current_humidity` MUST be `None`
  while the reading is `None` or its probe alarm (AL28 / AL34) is active;
  MUST NOT keep the previous value.
- Without a display or an allocated room probe (HA02 = 45 for temperature,
  HA03 = 53/54 for humidity) the setpoint entities
  (`TEMPERATURE_TARGET_KEYS`, `HUMIDITY_TARGET_KEYS`) MUST NOT be created
  and the climate entity MUST drop the matching target feature
  (`hub.update_hidden_keys`, decided from the primed read-back; a change of
  HA02/HA03 needs a reload).

## Context

The Modbus manual: setpoints act only with a display or external probes.
Headless without probes, Home Assistant decides when to request, so an
editable target would mislead. The real unit reports unwired analog inputs
as a sentinel, not 0.

## Consequences

- Good: no fake temperatures, no target that does nothing.
- Bad: wiring a probe later needs a reload to show its setpoints.

## Confirmation

- `tests/ha/test_failures.py::test_unplugged_probe_is_unknown_not_stale`
- `tests/ha/test_failures.py::test_probe_alarm_blanks_climate_reading`
- `tests/ha/test_headless.py::test_setpoints_hidden_without_room_probe`
- `tests/ha/test_display.py::test_real_room_readings`

## More information

`191763b` (probe alarms blank climate), PR #15 (sentinel, hidden setpoints).
