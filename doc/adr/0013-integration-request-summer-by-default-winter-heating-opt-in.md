---
status: accepted
date: 2026-10-21
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/{climate,select,binary_sensor,config_flow}.py"
---

# ADR-0013: The integration request cools in summer; winter heating is opt-in and the unit's own is reported

## Decision

- Turning INT on (`integration_request`, 1139) MUST be refused unless
  `hub.active_season` is summer, or `allow_winter_heating` (default off) is
  on and the circuit is not brine (ADR-0014). Unknown season counts as not
  summer. Turning it off is never refused by these guards.
- Turning INT on MUST be refused while PG02 (`integration_available`) reads
  off; the climate entity then offers no Cool/Heat.
- A season change to winter MUST be refused while an INT request is active
  and winter heating is not allowed.
- The season MUST be written only as HB04 (1825) = 4 summer / 3 winter
  (`select.season`); other values raise AL25.
- The season for every guard and for the climate entity is
  `hub.active_season`: the prefix of `mode_status` (1110), else
  `operating_mode` (1583).
- `allow_winter_heating` governs only Home Assistant's own requests. The
  unit's own winter heating (room temperature source + PG02, below
  SEtH − PF12) MUST be reported, not hidden: `binary_sensor.automatic_heating`
  and the setup issues `unit_heats_on_its_own`,
  `unit_heats_on_its_own_on_brine`, `winter_heating_without_integration`
  (silenced below `AUTO_HEATING_NEGLIGIBLE_BELOW`). A winter INT set
  elsewhere MUST be shown as heating whatever the option says.

## Context

INT is dehumidify + cool in summer but heating in winter (valve and pump
open, compressor off); a user asking for "cool" must not get heat after a
season change. The unit knows nothing of the option, and with a room
temperature source it raises its own winter INT (handbook 6.1.2; factory
PH09/PH10 = 14 °C make it heat below 13.5 °C), so the option cannot stop it.

## Consequences

- Good: Home Assistant never heats by surprise and never hides that the
  unit does.
- Bad: the only way Home Assistant stops the unit's own heating is climate
  Off (unit off), or changing SEtH / PH10 on the unit.

## Confirmation

- `tests/ha/test_headless.py::test_cooling_refused_in_winter`
- `tests/ha/test_headless.py::test_winter_heating_when_allowed`
- `tests/ha/test_headless.py::test_season_change_refused_while_integration_runs`
- `tests/ha/test_headless.py::test_winter_int_from_elsewhere_heats`
- `tests/ha/test_headless.py::test_auto_season_follows_mode_status`
- `tests/ha/test_seeds.py::test_cool_not_offered_without_integration_function`
- `tests/ha/test_display.py::test_unit_heats_on_its_own_and_says_on_what`

## More information

PR #15 (season, opt-in), PR #34 (PG02, active season), PR #37 (own heating).
Unit behaviour: `UNIT_BEHAVIOUR.md` §6–7.
