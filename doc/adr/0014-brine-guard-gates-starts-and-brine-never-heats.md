---
status: accepted
date: 2026-10-21
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/{config_flow,binary_sensor,climate}.py"
---

# ADR-0014: On brine nothing heats, and a guard gates every start

## Decision

- With `water_circuit = brine`, winter INT MUST always be refused and
  `allow_winter_heating` is forced off; the flows MUST refuse the two
  together (`winter_heating_on_brine`).
- On brine without a passing guard, these MUST be refused: winter DEU,
  switching the unit on in winter when it would dehumidify by itself (room
  probe logic, PU02) or on a digital-input request (1121 on, neither of
  ours), and a season change to winter in that state.
- The brine guard (options `brine_temperature_entity`,
  `brine_min_temperature`, default 8 °C), when configured, MUST pass for
  every start in every season: DEU/INT on, unit on with a request latched or
  with `auto_capable`, and enabling an enable whose request is latched. It
  passes when the sensor reads ≥ minimum (converted to °C) and its
  `last_reported` is within `BRINE_GUARD_MAX_AGE_HOURS` (24 h); unavailable,
  non-numeric or non-temperature readings block.
- The guard MUST only gate starts; it MUST NOT stop a running request.
- `update_brine_guard()` runs on the event loop before each poll, on the
  sensor's state events and inside `_check_request_allowed`.
- Once options exist they override data for these keys as a whole, so
  clearing the sensor sticks.
- `binary_sensor.brine_temperature_guard` (problem class, always available)
  is hidden when no sensor is set.

## Context

A brine circuit cannot heat, and cold brine freezes the register
(handbook 3.8.7). 8 °C sits above the unit's own AL16 frost alarm
(PA43 = 3 °C) and below PU08 (10 °C), so early-summer brine can still run
the passive cold-water path (PR #33, was 10 °C).

## Consequences

- Good: Home Assistant cannot start a freeze; a running cycle is never cut
  by a sensor hiccup.
- Bad: a dead brine sensor blocks every start until it reports again.

## Confirmation

- `tests/ha/test_headless.py::test_brine_guard_gates_starts_only`
- `tests/ha/test_headless.py::test_brine_never_heats`
- `tests/ha/test_headless.py::test_auto_is_a_start_for_the_brine_guard`
- `tests/ha/test_headless.py::test_brine_winter_refuses_a_unit_that_would_dehumidify_alone`
- `tests/ha/test_headless.py::test_brine_season_change_refused_for_a_digital_input_dehumidify`
- `tests/ha/test_config_flow.py::test_options_flow_refuses_winter_heating_on_brine`
- `tests/ha/test_restart.py::test_options_are_authoritative_after_restart`

## More information

PR #15 (brine, guard), PR #33 (8 °C), PR #36 / #37 (season change, DI
request), PR #41 (enabling as a start).
