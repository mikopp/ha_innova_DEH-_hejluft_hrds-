---
status: accepted
date: 2026-10-19
decision-makers: mikopp
topics: [water]
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/installer_params.py"
---

# ADR-0015: The unit runs its water circuit; the integration only watches

## Decision

- The water valve / pump output (1126, relay K5) and the condenser valve
  (1124, K4) MUST stay read-only diagnostics. The integration MUST NOT drive
  them, and MUST NOT write test-mode (PT) parameters to override them.
- Water problems MUST be reported (`sensor.water_check` from
  `_compute_water_issues`, setup issue `water_pump_output_not_configured`),
  never acted on. Temperature limits are judged only while water circulates.
- 1124 MUST NOT be used as evidence of what the unit does until its meaning
  is verified on hardware.

## Context

The unit sequences valve, pump and compressor itself (handbook 6.3/6.4,
anti-stagnation pulses); an external override could run the compressor
without water flow. The real unit reads 1124 = 1 in standby, against the
handbook, so its meaning is open (`plans/todo.md`).

## Consequences

- Good: no path where Home Assistant fights the unit's own protection.
- Bad: water faults can only be shown, not fixed, from Home Assistant.

## Confirmation

- `tests/ha/test_failures.py::test_water_circuit_problems`
- `tests/ha/test_installer.py::test_water_check_uses_pc07_without_the_installer_device`

Every PT (test mode) row is read-only:

```sh
! grep -E '\("PT[0-9]+", [0-9]+, "[ns]"' custom_components/innova_hrds/installer_params.py
```

## More information

PR #15. `hub.is_cooling` does not use 1124 (ADR-0025).
