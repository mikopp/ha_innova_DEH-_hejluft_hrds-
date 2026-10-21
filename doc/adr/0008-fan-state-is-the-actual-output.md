---
status: accepted
date: 2026-10-21
decision-makers: mikopp
supersedes: [ADR-0007]
paths:
  - "custom_components/innova_hrds/fan.py"
  - "custom_components/innova_hrds/climate.py"
  - "custom_components/innova_hrds/config_flow.py"
  - "custom_components/innova_hrds/__init__.py"
---

# ADR-0008: Fan state is the actual output; device limits stay device registers

## Decision

- `fan.hrds_supply_fan.percentage`, the climate `fan_mode` and
  `sensor.supply_fan_output` MUST report the actual output
  `outAO_SupplyFan` (639). `fan.set_percentage`, `climate.set_fan_mode` and
  `number.fan_manual_speed` MUST write `PM20_SupplyFan_Manual` (1614).
  Neither entity updates optimistically; the command is shown on
  `number.fan_manual_speed` and the fan's `commanded_percent` attribute.
- MUST NOT add a config option that shadows a device register. The per-mode
  fan minima are PF28 / PF27 / PF07 `number` entities. Options hold only
  what no register holds: connection settings, installation facts (model,
  `airflow_max_m3h`, `has_display`, `water_circuit`, the brine sensor) and
  the integration's own policies (`allow_winter_heating`, `installer_device`).
- `sensor.supply_fan_airflow` MUST be `output% / 100 × airflow_max_m3h`, and
  0 when the unit's own `supply_fan_status` says the fan is stopped; never a
  percentage threshold of ours.
- On a unit without the R option (damper output 1134 reads `disabled`,
  `hub.has_fan` false) the `FAN_KEYS` entities MUST NOT be created and the
  climate entity MUST drop `FAN_MODE`.
- MUST NOT code against the unconfirmed PM20 → output mapping (rescale,
  clamp or direct); the simulator models all three until hardware decides.

## Context

The handbook scales a manual fan request linearly into the active mode's
band (PF28/PF10 dehumidify, PF27/PF09 integration), so PM20 = 30 can give
about 60 % output and 0 need not stop the fan; unconfirmed on hardware
(`UNIT_BEHAVIOUR.md` §9.1). The removed `fan_min_output_pct` option reported
0 m³/h while the fan ran below it. The 130 / 190 m³/h of the technical data
are a tested range, not a firmware floor, so the old band-linear airflow
formula jumped at fan start.

## Consequences

- Good: state never claims a speed the unit did not adopt; the gap between
  commanded and actual is the diagnostic.
- Bad: a fan entity whose state differs from the value just set surprises
  users; the README explains it.

## Confirmation

- `tests/ha/test_fan.py::test_fan_percentage_during_dehumidify`
- `tests/ha/test_fan.py::test_no_optimistic_update_before_poll`
- `tests/ha/test_fan.py::test_airflow_zero_when_fan_off`
- `tests/ha/test_headless.py::test_non_r_unit_has_no_fan_entities`
- `tests/sim/test_device.py::test_fan_models_during_dehumidify`

## More information

`bb829ec` (proportional airflow), `b1ca765` (read/write split, option
removed), PR #37 (non-R). Open question: `plans/todo.md` "Rescale or clamp".
The three places that judge "fan stopped" disagree today: ADR-0028.
