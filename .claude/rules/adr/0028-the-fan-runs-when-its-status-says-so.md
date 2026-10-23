---
status: accepted
date: 2026-10-23
decision-makers: mikopp
topics: [fan, state]
paths:
  - "custom_components/innova_hrds/{__init__,const,climate}.py"
---

# ADR-0028: The fan runs when its status says so: On or the run-on Wait OFF

## Decision

- Whether the fan turns MUST come only from the unit's `SupplyFan_Status`
  (1119), through the single set `FAN_RUNNING_STATUSES = {"on",
  "wait_off"}` in `const.py`. No other code MUST judge it, and none MUST
  infer it from the output (639) or a threshold of ours.
- `binary_sensor.supply_fan_running` (`_compute_derived`), the airflow
  (`sensor.supply_fan_airflow`, ADR-0034) and the climate `hvac_action`
  *fan* MUST use it. Unknown status means unknown running and airflow
  (ADR-0005), never a guess.
- `binary_sensor.recirculation_active` stays damper open **and** status
  `on` (ADR-0033): during the run-on the damper is already closed.

## Context

Two places judged the fan and disagreed: the fan entity took `wait_off` as
stopped and `wait_on` as running, the airflow the other way round. The
handbook's sequence (HB 6.2) has Wait ON as the `PS01` delay before the fan
starts and Wait OFF as the run-on at `PF26`; on the reference unit the
output read 40 % (= `PF26`) in Wait OFF (`UNIT_BEHAVIOUR.md` §9.2, T19).
That the output is 0 in Wait ON is inferred, not logged. The owner's call:
the status is the unit's own word and the only truth about on or off.

## Considered options

- Stopped = off, disabled, alarm, with the output deciding in the two wait
  states (the first draft of this ADR): a second source for the same fact.
- All non-`on` statuses stopped: 0 m³/h during a run-on at 40 %.

## Consequences

- Good: running sensor, airflow and climate action agree in every state.
- Bad: if Wait ON ever drives the fan, the sensor shows off for the PS01
  delay; check it in the history of the next run.

## Confirmation

- `tests/ha/test_fan.py::test_running_follows_the_status_through_start_and_run_on`
- `tests/ha/test_fan.py::test_alarm_stops_the_fan`
- `tests/ha/test_fan.py::test_airflow_zero_when_fan_off`
- `tests/sim/test_device.py::test_fan_runs_on_at_pf26_after_the_request`

```sh
grep -q 'FAN_RUNNING_STATUSES = frozenset({"on", "wait_off"})' custom_components/innova_hrds/const.py
grep -q "in FAN_RUNNING_STATUSES" custom_components/innova_hrds/__init__.py
! grep -rn "_FAN_STOPPED\|in (\"off\", \"disabled\", \"alarm\")" custom_components/innova_hrds/
```

## More information

Found while extracting ADR-0008 (superseded by ADR-0034) from the history;
accepted with the removal of the fan entity (ADR-0034).
