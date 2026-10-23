---
status: proposed
date: 2026-10-23
decision-makers: mikopp
topics: [fan, state]
paths:
  - "custom_components/innova_hrds/{fan,__init__,const}.py"
---

# ADR-0028: One definition of "the fan is stopped"

## Decision

- `const.py` MUST define the `supply_fan_status` values that mean "stopped"
  once (`FAN_STOPPED_STATUSES`), and `fan.py` (`is_on`) and `__init__.py`
  (`_compute_derived`, airflow) MUST both use it.
- Proposed set: `{"off", "disabled", "alarm"}`. The transitional `wait_on`
  ("Starting") and `wait_off` ("Stopping") MUST NOT be judged stopped by the
  status; there the actual output (639) decides, as ADR-0034 wants.

## Context

Two places judge "fan stopped" and disagree today (the climate fan mode,
a third, went with ADR-0034):

| Place | Statuses treated as stopped |
|---|---|
| `fan.py` `_FAN_STOPPED` | off, disabled, wait_off, alarm |
| `__init__.py` `_compute_derived` (airflow) | off, disabled, alarm |

With `wait_off` the fan entity says off while `sensor.supply_fan_airflow`
reports m³/h. ADR-0034 says the fan entity and the airflow describe the same
fan. On the reference unit the output read 40 % (`PF26`) during `wait_off`
after a dehumidify stop (`UNIT_BEHAVIOUR.md` T19), so the fan most likely
turns then; whether it does was not checked by eye.

## Considered options

- All four statuses stopped (as `fan.py`): would report 0 m³/h during a
  post-run in which the fan may still turn.
- Leave as is: three entities contradict each other.

## Consequences

- Good: the fan entity and the airflow agree.
- Bad: the fan entity shows on for the post-run, which T19 suggests is right
  but nobody has watched.

## Confirmation

To add with the change: a test in `tests/ha/test_fan.py` that puts the
simulated fan in `wait_off` and in `alarm` and asserts the fan entity and
the airflow agree; and

```sh
test "$(grep -c 'FAN_STOPPED_STATUSES' custom_components/innova_hrds/*.py | awk -F: '{s+=$2} END {print s}')" -ge 3
```

## More information

Found while extracting ADR-0008 (superseded by ADR-0034) from the history. Accepting it means
implementing the constant and the test, then setting `status: accepted`.
