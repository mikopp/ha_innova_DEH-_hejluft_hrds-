---
status: accepted
date: 2026-10-23
decision-makers: mikopp
topics: [fan, climate, state, config, modbus-writes]
supersedes: [ADR-0008]
paths:
  - "custom_components/innova_hrds/fan.py"
  - "custom_components/innova_hrds/climate.py"
  - "custom_components/innova_hrds/config_flow.py"
  - "custom_components/innova_hrds/__init__.py"
  - "tests/sim/device.py"
---

# ADR-0034: The fan speed is the unit's; Home Assistant reads it and sets only the band

## Decision

- `fan.hrds_supply_fan` MUST be read-only (`FanEntityFeature(0)`): its
  `percentage` is the actual output `outAO_SupplyFan` (639), `is_on` follows
  `supply_fan_status`. The climate entity MUST NOT offer `FAN_MODE`.
- MUST NOT write `PM20_SupplyFan_Manual` (1614) from any path.
  `fan_manual_speed` MUST be a read-only sensor (`RW: 0`) showing it, also as
  the fan's `manual_request_percent` attribute; it MUST NOT be in
  `OPERATIONAL_KEYS`. The orphaned number entity is removed at setup.
- The band registers (PF28/PF10 dehumidify, PF27/PF09 cooling, PF07) MUST
  stay ordinary `number` entities, written only when the user sets them;
  MUST NOT be written per cycle or by a control loop (ADR-0023).
- MUST NOT add a config option that shadows a device register. Options hold
  only what no register holds: connection settings, installation facts
  (model, `airflow_max_m3h`, `has_display`, `water_circuit`, the brine
  sensor) and the integration's own policies.
- `sensor.supply_fan_airflow` MUST be `output% / 100 × airflow_max_m3h`, and
  0 while `supply_fan_status` says the fan is stopped.
- On a unit without the R option (`hub.has_fan` false) the `FAN_KEYS`
  entities MUST NOT be created.
- The simulator MUST model the observed fan: the unit owns PM20, clamps it
  into the active band and drives the output at it; a PM20 write is
  acknowledged and not kept, one outside the band answers exception 04.

## Context

The unit takes no fan-speed request over Modbus. PM20 is the display's
setpoint ("via Display (read only)", handbook PM20); the unit sets it itself
(`UNIT_BEHAVIOUR.md` §9.1, T22). Without a display a write inside the band was
acknowledged and never seen at a 0.5 s read (T23, T28), one below the band was
refused with exception 04 (T27). Whether a write acts with a display is
unknown, so no path writes it. Raising the band minimum raises a running fan,
lowering it does not (T24–T26).

## Considered options

- Set a speed by writing the band (minimum to raise, maximum to lower): two
  EEPROM writes per change, lost at the end of each request, and lowering
  through the maximum is untested (`plans/fan-speed-tests.md` test G). May be
  proposed once G is run.
- Keep writing PM20 in case a display unit takes it: on the tested unit every
  write did nothing or failed, which the entity cannot tell the user.

## Consequences

- Good: no entity offers a control that does nothing; what is shown is what
  the unit does.
- Bad: breaking for users with automations on `fan.set_percentage`,
  `climate.set_fan_mode` or `number.fan_manual_speed`; the speed can only be
  raised, through the band numbers.

## Confirmation

- `tests/ha/test_fan.py::test_fan_follows_the_band_during_dehumidify`
- `tests/ha/test_fan.py::test_no_speed_control_and_nothing_written_to_pm20`
- `tests/ha/test_fan.py::test_airflow_zero_when_fan_off`
- `tests/ha/test_headless.py::test_non_r_unit_has_no_fan_entities`
- `tests/sim/test_device.py::test_fan_starts_at_the_band_minimum_and_follows_a_raised_one`
- `tests/sim/test_device.py::test_pm20_write_is_not_kept_and_outside_the_band_refused`

```sh
! grep -n "C_FAN_MANUAL" custom_components/innova_hrds/climate.py
! grep -n "write_entity_value(C_FAN_MANUAL" custom_components/innova_hrds/*.py
```

## More information

Evidence: `tests/devices/runs/hrds_30+_fan_band_2026-10-23.json`, T22–T28.
Origin of the read/write split: ADR-0008 (`b1ca765`, `bb829ec`). Related:
ADR-0006 (state is the read-back), ADR-0023 (EEPROM), ADR-0028 (proposed:
one definition of "fan stopped").
