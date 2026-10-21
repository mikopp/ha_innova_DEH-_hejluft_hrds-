---
status: superseded by ADR-0008
date: 2026-09-10
decision-makers: mikopp
---

# ADR-0007: The fan entity reports the commanded speed

## Decision

`fan.hrds_supply_fan` and the climate entity's `fan_mode` read back the
commanded setpoint PM20 (1614) instead of the actual output (639), so the
entity would not "chase the unit's own modulation away from the setpoint";
the actual output was an attribute.

## Context

The climate entity read 639 and the fan entity 1614, so after
`fan.set_percentage(30)` the two disagreed about the same fan. Making both
read 1614 removed the disagreement.

## Why it was superseded

The same day, the read and the write were split instead (ADR-0008): the
state shows what the fan does (639) and the command stays visible on
`number.fan_manual_speed` and the `commanded_percent` attribute. Showing the
command as the state hid exactly the divergence that tells whether the unit
rescales or clamps a manual speed into its band.

## More information

`c169cda`, replaced by `b1ca765` (PR #13).
