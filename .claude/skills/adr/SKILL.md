---
name: adr
description: Records, supersedes and checks the architecture decision records in doc/adr. Use when a change makes or reverses a design decision (a rule the code must keep following), when asked to log, write or propose an ADR, when a planned change would contradict an ADR, or before opening a PR to check the diff against the ADRs that govern the changed files.
argument-hint: "new <decision> | supersede <ADR-NNNN> <decision> | check [base]"
---

# ADRs

Format and rules: `doc/adr/0001-record-decisions-as-path-scoped-adrs.md`.
Template: `doc/adr/template.md`. Validator: `python3 tests/adr_check.py`.

## Is it an ADR?

Yes: a choice between options with a reason that future code must keep
honouring (a guard, a write policy, a data source, a test or CI rule).
No: a bug fix that restores an existing rule, a how-to (`.claude/rules/` or a
skill), a fact about the unit (`doc/references/UNIT_BEHAVIOUR.md`).

## new: record a decision

```
- [ ] 1. python3 tests/adr_check.py --for <files the decision governs>
        → read those ADRs; if one already covers it, edit or supersede instead
- [ ] 2. cp doc/adr/template.md doc/adr/NNNN-kebab-title.md (next free number)
- [ ] 3. Decision first: one RFC 2119 rule per bullet, naming code symbols
- [ ] 4. paths: the narrowest globs that cover the governed files
- [ ] 5. Confirmation: existing test ids and/or an sh check that exits 0
- [ ] 6. Context/Consequences: a few lines; link evidence, PRs, commits
- [ ] 7. status: proposed (accepted only when the user agreed or it records
        what the code already does)
- [ ] 8. python3 tests/adr_check.py --fix && python3 tests/adr_check.py
        → fix every FAIL, repeat until ALL PASS
```

Keep an ADR under 90 lines: it loads into context whenever a governed file is
read. Never restate it in CLAUDE.md; a one-line invariant citing the id is
enough.

## supersede: change a decision

1. Write the new ADR as above with `supersedes: [ADR-OLD]`.
2. In the old ADR set `status: superseded by ADR-NEW`, delete its `paths`, and
   add a short "Why it was superseded" section.
3. Update CLAUDE.md lines that cite the old id; run the validator.

## check: a diff against the ADRs

1. `python3 tests/adr_check.py --for $(git diff --name-only origin/main...HEAD)`
   (another base if one was given).
2. Read each listed ADR's `## Decision` and compare the diff with every rule.
3. Report each violation as `ADR-NNNN rule → file:line → what breaks it`.
   Either fix the code or propose a superseding ADR; never ignore an
   accepted rule silently.
4. A diff that makes a new decision without an ADR: propose one (`new`).
