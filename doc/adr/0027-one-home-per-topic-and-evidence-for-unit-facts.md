---
status: accepted
date: 2026-10-21
decision-makers: mikopp
paths:
  - "doc/references/*.md"
  - "plans/*.md"
  - "README.md"
---

# ADR-0027: One home per topic; every unit fact carries its evidence

## Decision

- Each topic MUST have exactly one home (the "Where to find what" table in
  `CLAUDE.md`); other files link to it and MUST NOT restate it.
- `doc/references/UNIT_BEHAVIOUR.md` MUST describe only the unit, never the
  integration, and tag every statement: `[HB 6.3]`, `[MB p.7]`, `[V#76]` /
  `[F#79]`, `[T7]` or `[INFERRED]`.
- `doc/references/MODBUS_REGISTERS.md` MUST define registers only (no
  behaviour) in rows of the form ``| `0xHHHH` | dec | name |``, and MUST
  have a row for every `REG` in `const.py`.
- A hardware observation MUST add a `T` row to the evidence log
  (`UNIT_BEHAVIOUR.md` §13), replace the `[INFERRED]` tags it settles and
  tick the item in `plans/todo.md`.
- A factory default MUST say whose: the handbook's or the reference unit's
  (`UNIT_BEHAVIOUR.md` §15).
- Decisions MUST live in `doc/adr` (ADR-0001), not in README or CLAUDE.md
  prose.

## Context

Unit behaviour was described in four places that had started to disagree
(PC08's default, the PH10 cap, passive airflow). Code, simulator and tests
take their rules from these files (the simulator reads the register table),
so a wrong statement becomes a wrong model.

## Consequences

- Good: one edit per fact; every claim can be traced or is marked a guess.
- Bad: answering a question can take a hop through a link.

## Confirmation

- `tests/wiring_check.py` "register addresses match the reference doc"

```sh
grep -q "Only the unit" doc/references/UNIT_BEHAVIOUR.md
```

## More information

PR #40 (UNIT_BEHAVIOUR.md, `doc/references/`).
