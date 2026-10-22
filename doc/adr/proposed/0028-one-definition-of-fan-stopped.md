---
status: proposed
date: 2026-10-21
decision-makers: mikopp
topics: [fan, state]
paths:
  - "custom_components/innova_hrds/{fan,climate,__init__,const}.py"
---

# ADR-0028: One definition of "the fan is stopped"

## Decision

- `const.py` MUST define the `supply_fan_status` values that mean "stopped"
  once (`FAN_STOPPED_STATUSES`), and `fan.py` (`is_on`), `climate.py`
  (`_derive_fan_mode`) and `__init__.py` (`_compute_derived`, airflow) MUST
  all use it.
- Proposed set: `{"off", "disabled", "alarm"}`. The transitional `wait_on`
  ("Starting") and `wait_off` ("Stopping") MUST NOT be judged stopped by the
  status; there the actual output (639) decides, as ADR-0008 wants.

## Context

Three places judge "fan stopped" and disagree today:

| Place | Statuses treated as stopped |
|---|---|
| `fan.py` `_FAN_STOPPED` | off, disabled, wait_off, alarm |
| `climate.py` `_derive_fan_mode` | off, disabled, wait_off |
| `__init__.py` `_compute_derived` (airflow) | off, disabled, alarm |

With `wait_off` the fan entity and `fan_mode` say off while
`sensor.supply_fan_airflow` reports m³/h; with `alarm` the fan entity is off
and the airflow 0, but `fan_mode` is derived from the output. ADR-0008 says
the fan entity, `fan_mode` and the airflow describe the same fan.
Whether the fan turns during `wait_off` (the PF03 post-run) is unverified.

## Considered options

- All four statuses stopped (as `fan.py`): would report 0 m³/h during a
  post-run in which the fan may still turn.
- Leave as is: three entities contradict each other.

## Consequences

- Good: the fan entity, the climate fan mode and the airflow agree.
- Bad: needs a hardware check of `wait_off` (record 1119 and 639 during a
  post-run); `plans/todo.md` lists it.

## Confirmation

To add with the change: a test in `tests/ha/test_fan.py` that puts the
simulated fan in `wait_off` and in `alarm` and asserts the fan entity,
`fan_mode` and airflow agree; and

```sh
test "$(grep -c 'FAN_STOPPED_STATUSES' custom_components/innova_hrds/*.py | awk -F: '{s+=$2} END {print s}')" -ge 4
```

## More information

Found while extracting ADR-0008 from the history. Accepting it means
implementing the constant and the test, then setting `status: accepted`.
