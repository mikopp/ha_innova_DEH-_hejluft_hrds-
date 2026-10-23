---
status: accepted
date: 2026-10-23
decision-makers: mikopp
topics: [state, entities, fan]
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/const.py"
---

# ADR-0033: What the unit cannot report is derived or unknown, never a stand-in register

## Decision

- An entity whose register nothing on this installation feeds MUST read
  unknown (`None` in `hub.data`), not the register's value. The hub decides
  it once from the primed read-back in `update_hidden_keys` and applies it in
  `_blank_unfed_readings`, called from `_compute_derived` and at the end of
  `update_hidden_keys`.
- `supply_fan_rpm` (1117) MUST be unknown unless an input is allocated to the
  fan tachometer (`TACHOMETER_INPUT_CODES` 45/46 on one of
  `TACHOMETER_ALLOCATION_KEYS`: HA01, HA04–HA18, HB01, HB02, HB05–HB07).
  These are read at setup as `INSTALLER_LOGIC_KEYS` (ADR-0017), never
  polled. An allocation that was not read MUST count as a possible
  tachometer.
- `temp_probe_ok` / `humidity_probe_ok` MUST be unknown while
  `show_temperature_target` / `show_humidity_target` is false (no display,
  no room probe allocated; ADR-0011): AL28/AL34 have nothing to check.
- `recirculation_active` MUST be a `COMPUTED_BINARY_SENSORS` entry: on while
  the damper output (1134) is `on` and `supply_fan_status` (1119) is `on`,
  unknown while either is unknown, else off. `FanIntegration_Request`
  (1112) MUST NOT be presented as recirculation; it is
  `fan_integration_request` (diagnostic).
- The simulator MUST model 1117 as 0 without a tachometer allocation and
  MUST NOT drive 1112 from a request (ADR-0019).

## Context

The reference unit read 1117 = 0 with its fan running through two
dehumidify runs; its dump allocates no input to the tachometer
(`UNIT_BEHAVIOUR.md` §9.1, T16, T18, T21). 1112 stayed 0 while the damper was
open and the fan ran (T16, T18), so `recirculation_active` on 1112 never
turned on. The probe-OK sensors read "OK" on a headless unit with no probe,
where AL28/AL34 never fire (T4, T15). Each showed a value the user would
read as a fact about the unit.

## Considered options

- Hide the entities (as ADR-0011 does for setpoints): a reading that becomes
  real after an installer change would need a reload to appear; unknown is
  what an unwired probe already shows (ADR-0011).
- Judge recirculation with the running set of ADR-0028: counts the run-on
  Wait OFF, when the damper is already closed and no room air is drawn.

## Consequences

- Good: no entity claims a speed, a healthy probe or a recirculation state
  the unit did not report.
- Bad: wiring a tachometer or a probe later needs a reload; 21 more
  registers are read at setup.

## Confirmation

- `tests/ha/test_fan.py::test_fan_speed_unknown_without_a_tachometer_input`
- `tests/ha/test_fan.py::test_fan_speed_shown_with_a_tachometer_input`
- `tests/ha/test_fan.py::test_recirculation_is_damper_open_and_fan_running`
- `tests/ha/test_headless.py::test_probe_ok_is_unknown_without_a_probe`

```sh
! grep -n '"REG": 1112' -B3 custom_components/innova_hrds/const.py | grep -q 'C_RECIRCULATION_ACTIVE'
```

## More information

Evidence: `tests/devices/runs/hrds_30+_dehumidify_run_2026-10-23.json`.
Related: ADR-0005 (unknown rather than stale), ADR-0011 (no probe, no
reading), ADR-0017 (logic keys read at setup), ADR-0028 (when the fan
runs).
