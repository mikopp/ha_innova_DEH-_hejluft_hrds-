---
name: adr
description: Records, supersedes, rejects and checks the architecture decision records (accepted in .claude/rules/adr, proposed and superseded in doc/adr, index doc/adr/README.md). Use when a change makes or reverses a design decision (a rule the code must keep following), when asked to log, write, propose, supersede or reject an ADR, when a planned change would contradict an ADR, or before opening a PR to check the diff against the ADRs that govern the changed files.
argument-hint: "new <decision> | supersede <ADR-NNNN> <decision> | reject <ADR-NNNN> | check [base]"
---

# ADRs

Rules for the format and the folders: ADR-0001 and ADR-0029 (both in
`.claude/rules/adr/`). Template: `template.md` next to this file. Validator:
`python3 tests/adr_check.py`.

Folders: accepted = `.claude/rules/adr/` (loaded by path), proposed =
`doc/adr/proposed/`, superseded/rejected/deprecated = `doc/adr/superseded/`.
**Do not open the last two** except as the revival challenge below says. Get
history with `python3 tests/adr_check.py --history [--topic T...]`.

## Is it an ADR?

Yes: a choice between options with a reason that future code must keep
honouring (a guard, a write policy, a data source, a test or CI rule).
No: a bug fix that restores an existing rule, a how-to (`.claude/rules/` or a
skill), a fact about the unit (`doc/references/UNIT_BEHAVIOUR.md`).

## new: record a decision

```
- [ ] 1. Topics: pick from .claude/rules/adr-topics.md what the decision is about
- [ ] 2. Accepted ADRs: python3 tests/adr_check.py --for <files> and --topic <topics>
        → read them; if one already covers it, edit or supersede instead
- [ ] 3. History: python3 tests/adr_check.py --history --topic <topics>
        → REVIVAL CHALLENGE below if the new decision matches anything listed
- [ ] 4. python3 tests/adr_check.py --next; cp template.md
        doc/adr/proposed/NNNN-kebab-title.md
- [ ] 5. Decision first: one RFC 2119 rule per bullet, naming code symbols
- [ ] 6. paths: the narrowest globs over the governed files; topics: every
        topic it is about (a new one only if none fits: add it to TOPICS)
- [ ] 7. Confirmation: existing test ids and/or an sh check that exits 0
- [ ] 8. Context/Consequences: a few lines; link evidence, PRs, commits
- [ ] 9. status: proposed; accepted only when the user agreed or it records
        what the code already does
- [ ] 10. python3 tests/adr_check.py --fix && python3 tests/adr_check.py
         → fix every FAIL, repeat until ALL PASS (--fix moves an accepted ADR
         into .claude/rules/adr/ and regenerates the indexes)
```

Keep an ADR under 90 lines: it loads into context whenever a governed file is
read. Never restate it in CLAUDE.md; a one-line invariant citing the id is
enough.

### Revival challenge (step 3)

The digest shows, per proposed or retired ADR, what it decided and why it was
retired. Compare each with the new decision's rules.

* No overlap: go on. Open nothing.
* The new rule re-adopts what a retired ADR dropped, or repeats a rejected
  one: **stop**. Tell the user the old id and title, what it decided, why it
  was retired, and the new decision that would undo that. Ask what changed (a
  hardware test, a PR, a premise that no longer holds). Write nothing until
  they answer.
* They give evidence: open the retired file (accept the Read prompt), then
  write the new ADR with `revives: [ADR-OLD]` in the frontmatter and a
  `## What changed since ADR-OLD` section stating the evidence. If the old
  ADR was only superseded in part, say which part.
* They give none: do not write the ADR; keep the old decision.
* A proposed ADR that overlaps: tell the user, and edit that proposal instead
  of adding a second one.

## supersede: change a decision

1. Run steps 1–3 above. Write the new ADR with `supersedes: [ADR-OLD]`.
2. In the old ADR set `status: superseded by ADR-NEW`, delete its `paths`, and
   add a `## Why it was superseded` section: what failed or changed, with
   evidence.
3. Update CLAUDE.md lines that cite the old id. `--fix` moves the old file to
   `doc/adr/superseded/`, which stops it loading; then run the validator.

## reject: a decision not taken

Write the ADR with `status: rejected` and a `## Why it was rejected` section
(who decided, why), so the next proposal of it meets the revival challenge.
`--fix` puts it in `doc/adr/superseded/`.

## check: a diff against the ADRs

1. `python3 tests/adr_check.py --for $(git diff --name-only origin/main...HEAD)`
   (another base if one was given).
2. For every file it reports as covered by no ADR path, and for logic moved
   between files, decide its topics (`.claude/rules/adr-topics.md`) and run
   `python3 tests/adr_check.py --topic <topics>`.
3. Read each listed ADR's `## Decision` and compare the diff with every rule.
4. Report each violation as `ADR-NNNN rule → file:line → what breaks it`.
   Either fix the code or propose a superseding ADR; never ignore an
   accepted rule silently.
5. A diff that makes a new decision without an ADR: propose one (`new`). A
   new file a decision should govern: add it to that ADR's `paths`.
