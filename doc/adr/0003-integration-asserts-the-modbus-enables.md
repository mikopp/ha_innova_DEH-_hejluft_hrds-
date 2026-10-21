---
status: superseded by ADR-0022
date: 2026-09-10
decision-makers: mikopp
topics: [modbus-writes, requests]
---

# ADR-0003: The integration asserts the Modbus enables on every poll

## Decision

The hub wrote PH02 (1778), PH27 (1869) and PH28 (1870) to 1 at setup and,
from 2026-09-10, re-asserted them from the polled read-back on every poll,
so that a power cycle that cleared them could not leave later writes
silently ignored.

## Context

The Modbus manual makes the "by BMS" enables mandatory for Modbus requests.
The first version wrote them once per hub lifetime and marked them done even
when the writes failed; driving them from the read-back fixed that.

## Why it was superseded

- Their switches could not be turned off: the next poll switched them on
  again, so the user could not leave a function to the unit's own controls.
- Writing PH02 = 1 handed on/off to a Modbus register that read off, which
  switched a running display unit off when the integration was added.
- The premise did not hold: the unit keeps its settings across a power cycle
  (`doc/references/UNIT_BEHAVIOUR.md` §3.6, T7).

## More information

Initial commit `f6e4556`, read-back driven in `77f2aec`; replaced by
ADR-0022 in PR #41.
