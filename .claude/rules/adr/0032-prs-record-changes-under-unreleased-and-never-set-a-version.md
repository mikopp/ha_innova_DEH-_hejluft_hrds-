---
status: accepted
date: 2026-10-22
decision-makers: mikopp
topics: [docs, ci]
paths:
  - "CHANGELOG.md"
  - ".claude/rules/changelog.md"
---

# ADR-0032: PRs record changes under Unreleased in release-notes shape and never set a version

## Decision

- A PR with a user-visible change MUST add its entries under
  `## Unreleased`, the first section of `CHANGELOG.md` (created if missing).
- Entries MUST sit only under these subsections, in this order, empty ones
  left out (`SUBSECTIONS` in `scripts/release.py`): `### ⚠️ Breaking
  changes`, `### ✨ Highlights`, `### 🛠️ Fixes and other changes`,
  `### 📚 Documentation`, `### 🧪 Tests and CI`.
- Entries MUST be written for a user: one bullet per change, a bold lead
  sentence and at most two more lines; sub-bullets only for steps the user
  must take; renamed ids as an old → new table under Breaking. Details:
  `.claude/rules/changelog.md`.
- A PR MUST NOT add a version heading or change the version in
  `manifest.json` or the README banners; only the release script does
  (ADR-0031).
- `scripts/release.py check` MUST run in `lint.yaml` on every PR.
- Sections released before 0.9.4 MAY keep their free-form style; only the
  top section is checked.

## Context

PRs guessed the next version (`## 0.9.4`, manifest and banner on main
before any release), and the CHANGELOG was developer prose that the owner
rewrote by hand into the v0.9.3 release notes (Breaking, themed sections,
docs, tests). Writing the entries in release-notes shape when the change is
made lets the notes be cut from the file without an LLM, so the same
script works locally, for an agent and in CI.

## Consequences

- Good: the release notes cost nothing at release time; a PR cannot break
  the versioning; Breaking changes are always at the top.
- Bad: PR authors write the entry a little more carefully.

## Confirmation

- `tests/test_release_script.py::test_lint_refuses_a_guessed_version`
- `tests/test_release_script.py::test_lint_refuses_a_broken_structure`
- `tests/test_release_script.py::test_notes_keep_user_parts_and_fold_docs`

```sh
python3 scripts/release.py check
grep -q 'scripts/release.py check' .github/workflows/lint.yaml
```

## More information

Release side: ADR-0031. Format of the v0.9.3 notes this mirrors: the
GitHub release v0.9.3.
