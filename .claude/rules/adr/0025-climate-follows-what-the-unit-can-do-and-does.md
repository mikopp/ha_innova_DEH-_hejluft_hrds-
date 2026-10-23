---
status: accepted
date: 2026-10-23
decision-makers: mikopp
topics: [climate, requests, fan]
paths:
  - "custom_components/innova_hrds/climate.py"
  - "custom_components/innova_hrds/__init__.py"
---

# ADR-0025: The climate mode says what can make the unit act; the action says what it does

## Decision

- `hvac_mode` MUST be derived in this order (`_derive_mode`): unit not
  running → OFF; `hub.int_effect` cool/heat → COOL/HEAT; DEU active → DRY;
  `hub.auto_capable` → AUTO; `dehumidify_request` (1121) on from another
  source → DRY; else FAN_ONLY, labelled "Standby". OFF MUST only ever mean
  the unit is off, so the mode never contradicts `switch.unit_on_off`. A
  request that cannot act (PG02 off, enable off, winter INT on brine) MUST
  NOT decide the mode.
- Offered modes (`_modes_for`): AUTO only while `auto_capable`, else
  FAN_ONLY; no DRY without PH28; COOL in summer and HEAT in winter only with
  PG02 and PH27 (HEAT with `allow_winter_heating` or while a winter INT
  heats); without PH02 only the modes on the side of on/off the unit is on.
  The current mode is always listed.
- `hvac_action` MUST come from evidence, not from the request: HEATING only
  if `hub.is_heating` (heating INT, valve/pump on, no AL04, compressor off,
  water ≥ PC08); COOLING only if `hub.is_cooling` (cooling INT, compressor
  on, no AL03); else DRYING (compressor or 1121 on); else FAN (R unit, fan
  running, ADR-0028); else IDLE. The condenser valve (1124) MUST NOT be evidence (ADR-0015).
- Setting a mode MUST check every write (`check_write_allowed`) before the
  first, then write the requests before `unit_on_off`. OFF clears both
  requests and switches the unit off (offered only where PH02 allows it);
  if clearing fails it still switches off and re-raises the first error. AUTO and FAN_ONLY clear both
  requests and switch on; COOL sets INT and DEU, HEAT sets INT and clears
  DEU, DRY sets DEU and clears INT. `turn_on` = AUTO if `auto_capable` else FAN_ONLY; `turn_off` = OFF.
  `_usable` drops writes a disabled enable makes pointless.
- The climate entity MUST NOT show a fan: no `FAN_MODE` feature, no
  `fan_mode` / `fan_modes`, now or later, because the unit takes no
  fan-speed request over Modbus, so a fan mode could never be set
  (ADR-0034). FAN_ONLY is only Standby renamed and MUST NOT write any fan
  register. The FAN action stays: it reports what the unit does.
- Targets: humidity ← `humidity_setpoint` within PH29/PH30; temperature ←
  SEtC (15–35 °C) in summer, SEtH clamped to PH09..PH10 in winter.

## Context

The unit ORs its request sources (its own room logic, the DEU/INT digital
inputs, Modbus; handbook 6.1). A headless unit switched on with nothing
requested never acts, yet was shown as Dry; any winter INT was shown as
Heating although the unit has no heat source and only warm water heats. A
refused Dry used to clear a running Cool before being refused.

## Consequences

- Good: the card is honest about what the unit will and does do.
- Bad: Auto is verified only on the derived `display_cnu2` overlay, not on a
  real display unit (README banner).

## Confirmation

- `tests/ha/test_headless.py::test_unit_on_without_request_is_standby`
- `tests/ha/test_headless.py::test_turn_on_goes_to_standby_and_turn_off_switches_off`
- `tests/ha/test_headless.py::test_dehumidify_request_from_another_source_shows_dry`
- `tests/ha/test_headless.py::test_heating_needs_warm_water`
- `tests/ha/test_headless.py::test_summer_int_blocked_by_al03_is_drying`
- `tests/ha/test_headless.py::test_refused_dry_leaves_a_running_cool_alone`
- `tests/ha/test_failures.py::test_off_switches_the_unit_off_when_a_request_cannot_be_cleared`
- `tests/ha/test_display.py::test_auto_lets_the_unit_dehumidify_on_its_own`
- `tests/ha/test_display.py::test_target_temperature_range_follows_the_season`
- `tests/ha/test_fan.py::test_no_fan_control_and_nothing_written_to_pm20`

```sh
! grep -nE "FAN_MODE|fan_mode" custom_components/innova_hrds/climate.py
```

## More information

PR #34 (Off/Auto, evidence), PR #36 / #37 (precheck, Standby, Off is off),
PR #41 (enables trim modes).
