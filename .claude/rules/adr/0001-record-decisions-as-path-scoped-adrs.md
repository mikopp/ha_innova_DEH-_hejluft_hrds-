---
status: accepted
date: 2026-10-21
decision-makers: mikopp
topics: [docs]
paths:
  - "doc/adr/**"
  - ".claude/**"
  - "**/CLAUDE.md"
---

# ADR-0001: Record decisions as path-scoped ADRs that agents load on demand

## Decision

- MUST record every architecture decision (a choice with a reason that code
  must keep honouring) as one file `NNNN-kebab-title.md`, from
  `.claude/adr/template.md`: MADR 4.0 frontmatter (`status`, `date`,
  `decision-makers`, optional `supersedes`) plus `paths`, the globs of the
  files the decision governs, and `topics`, what the decision is about from
  the fixed set `TOPICS` in `tests/adr_check.py`.
- MUST put the rules first: `## Decision` is a list of RFC 2119 rules
  (MUST / MUST NOT / SHOULD / MAY) naming the code symbols, so an agent can
  act without reading further. Context, options and consequences follow,
  short; evidence is linked, not repeated.
- MUST say in `## Confirmation` how the decision is checked: test ids
  (`tests/...py::test_x`) and/or an `sh` block that exits 0 while it holds.
- An accepted ADR MUST be a real file in `.claude/rules/adr/`, where Claude
  Code loads it only when it reads a file matching its `paths`. Every other
  ADR (proposed, superseded, rejected, deprecated) MUST be in `.claude/adr/`,
  which nothing loads. A status change moves the file (`--fix`). No
  symlinks. `doc/adr/README.md` is the generated index for people.
- MUST keep `.claude/rules/adr-topics.md` generated (`--fix`): topic → ADR
  ids, loaded with any code, test or CI file, so a decision also reaches
  logic in a file no `paths` glob covers yet. Code in such a file MUST
  follow the ADRs of its topics.
- MUST NOT restate an ADR in CLAUDE.md. CLAUDE.md MAY list one-line
  invariants citing the ADR id; `tests/adr_check.py` fails if a cited ADR is
  not accepted.
- A changed decision MUST be a new ADR whose `supersedes` names the old one;
  the old one's status becomes `superseded by ADR-NNNN` and its `paths` are
  dropped. Clarifications that do not change the decision MAY edit an
  accepted ADR in place (bump `date`).
- Before a change that contradicts an accepted ADR, an agent MUST stop and
  either follow the ADR or propose a superseding one (`/adr` skill).

## Context

CLAUDE.md had grown to 525 lines loaded into every session, most of it
relevant to one file. Anthropic: keep CLAUDE.md under 200 lines, move
part-specific rules to `.claude/rules/` with `paths`. actual.ai: agents given
scoped, rule-first ADRs read only the few that apply (~5 % of tokens) and
take far fewer wrong turns. Decisions were spread over commits, PR bodies
and CLAUDE.md; some reversals left no trace.

## Considered options

- Nygard prose ADRs (Anthropic's `architecture` skill): unscoped, unchecked.
- ADRs in `doc/adr` symlinked into `.claude/rules/` (the first version):
  Windows git checks symlinks out as text files, so nothing loads there.
- Generated copies in `.claude/rules/`: works everywhere, every edit twice.
- Generated copies of the rules in CLAUDE.md: always loaded, drifts.
- Broad `paths` (`custom_components/**`) for cross-cutting ADRs: reaches new
  files, but loads ~9k tokens with every code read; the topic map costs ~450.

## Consequences

- Good: CLAUDE.md stays small; the decisions for a file arrive with the
  file; superseded ideas are recorded but never loaded.
- Good: `tests/adr_check.py` (lint workflow) keeps scopes, folders, index,
  topic map, citations and confirmations honest.
- Bad: the ADR files sit in a hidden folder; the `doc/adr` index links them.

## Confirmation

`tests/adr_check.py` runs in the lint workflow:

```sh
grep -q "python3 tests/adr_check.py" .github/workflows/lint.yaml
```

## More information

Format: [MADR 4.0](https://adr.github.io/madr/) with actual.ai's agent
extensions ([ADRs for coding agents](https://actual.ai/blog/agent-optimized-adrs)):
`paths` is their `applies_to`, `## Confirmation` their "Verify". Loading:
[Claude Code memory docs](https://code.claude.com/docs/en/memory#path-specific-rules).
Verified on Claude Code 2.1.306: a rule with `paths` loads when a matching
file is read or created, and not before.
