---
status: accepted
date: 2026-10-22
decision-makers: mikopp
topics: [docs]
paths:
  - "doc/adr/proposed/**"
  - "doc/adr/superseded/**"
  - ".claude/skills/adr/**"
  - ".claude/settings.json"
---

# ADR-0029: Proposed and retired ADRs are history; reviving one needs new evidence

## Decision

- Proposed ADRs MUST be in `doc/adr/proposed/`; superseded, rejected and
  deprecated ones in `doc/adr/superseded/`. Both are outside `.claude/`, so
  nothing loads them. A retired ADR is never deleted.
- Agents MUST NOT read, search or list those two folders while implementing,
  reviewing or debugging. They MAY only when recording, superseding or
  rejecting an ADR (`/adr`), or when the user asks about a decision's history.
- Agents MUST get history from `python3 tests/adr_check.py --history
  [--topic T...]` (id, status, what was decided, why it was retired, file),
  and open a file only if the new decision overlaps what it shows.
  `.claude/settings.json` MUST keep `ask` rules on `Read` for both folders.
- Before recording an ADR the agent MUST run `--history` for its topics. If
  the new decision re-adopts a rule a retired ADR dropped, or repeats a
  rejected one, the agent MUST stop, tell the user the old id and its reason,
  and write nothing until the user names what changed.
- A revival MUST declare `revives: [ADR-NNNN]` and carry a
  `## What changed since ADR-NNNN` section citing the new evidence (hardware
  test, PR, changed premise). `tests/adr_check.py` rejects one without it.
- A retired ADR MUST say `## Why it was superseded` (or rejected, deprecated).

## Context

Superseded decisions go wrong again when nobody remembers why they were
dropped: asserting the Modbus enables (ADR-0003) and showing the commanded fan
speed (ADR-0007) were each reasonable and each reversed after a failure. But
history files read during normal work cost tokens and invite following a
retired rule. Reading is cheap only when it is a digest on demand.

## Considered options

- Retired ADRs under `.claude/` with `paths` removed: any `.md` there loads.
- Hard `deny` on both folders: also blocks the recording flow; `ask` leaves
  the user in control.
- Auto-detecting revival: topics overlap too often (successors, siblings);
  the challenge stays a skill step with a checked record.

## Consequences

- Good: history costs nothing in normal work and cannot be silently undone.
- Bad: `ask` covers the Read tool only; Grep, Glob and Bash are not gated
  (checked), so the rule above is what holds there.

## Confirmation

```sh
python3 -c "import json; a=json.load(open('.claude/settings.json'))['permissions']['ask']; assert any('adr/proposed' in r for r in a) and any('adr/superseded' in r for r in a)"
python3 tests/adr_check.py --history --topic modbus-writes | grep -q "ADR-0003"
```

## More information

Superseding flow and the challenge wording: `.claude/skills/adr/SKILL.md`.
Layout: ADR-0001.
