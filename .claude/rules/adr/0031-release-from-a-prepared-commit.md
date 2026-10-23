---
status: accepted
date: 2026-10-22
decision-makers: mikopp
topics: [ci]
supersedes: [ADR-0021]
paths:
  - "scripts/release.py"
  - ".github/workflows/release.yaml"
  - ".github/workflows/release-draft.yaml"
  - ".claude/skills/release-prep/**"
  - "hacs.json"
  - "custom_components/innova_hrds/manifest.json"
  - "custom_components/innova_hrds/brand/**"
---

# ADR-0031: Release from a prepared commit: one script prepares, CI verifies, the owner publishes a draft

## Decision

- A release MUST be a normal GitHub release (not a pre-release: HACS hides
  those) whose tag is `vX.Y.Z`.
- A release MUST be prepared by `scripts/release.py <X.Y.Z | --bump …>` in
  a release PR, before the tag exists. The owner runs it locally (it
  branches, commits, pushes and opens the PR), or an agent runs it through
  the `release-prep` skill (`--no-git`). It is the only code that writes the
  version: `manifest.json`, `## Unreleased` → `## X.Y.Z (date): title` in
  `CHANGELOG.md`, the `## Release X.Y.Z` banners in `README.md` and
  `README.de.md`, and links to the English banner's anchor.
- The release process MUST NOT depend on README prose beyond the version
  banner, so it works the same before and after 1.0.
- An agent-prepared release MUST review `plans/todo.md` against the
  release's entries and carry any updates in the release PR; the local
  script reminds the owner to do the same.
- Merging a release PR MUST lead to a draft release (`release-draft.yaml`):
  title `vX.Y.Z: <changelog title>`, body `release.py notes X.Y.Z`. Only the
  owner publishes it (ADR-0020).
- `release.yaml` MUST first run `verify` (`release.py check "$TAG"`): the
  tag, the manifest, the top CHANGELOG heading and both banners name one
  version and no Unreleased section is left. hassfest, hacs, tests and e2e
  run after it, `package` only after all of them.
- `package` MUST NOT change any file: the zip of
  `custom_components/innova_hrds` equals the tagged commit. It attaches
  `innova_hrds.zip` (`hacs.json`: `zip_release`, `filename`) and fills an
  empty release body from `release.py notes`. A release without the zip
  MUST be fixed by re-running `package`, not left.
- Brand images MUST ship in `custom_components/innova_hrds/brand/`
  (`icon`, `logo`, `@2x`, `dark_*`), the Innova mark recoloured `#00643e`
  (white for dark). MUST NOT use Home Assistant branded images. `hacs.yaml`
  ignores the `brands` check.

## Context

ADR-0021 stamped the tag into the zip only, so main never reliably held
the released version and PRs guessed it (0.9.4 on main, unreleased).
Writing it back after publishing needs a bypass ADR-0020 forbids. Titles
and bodies were hand-written in differing formats. Home Assistant 2026.3+
prefers brand images in the integration over the brands CDN.

## Considered options

- Stamp on publish and push back to main: needs a bypass; the tag would
  still point at the unstamped commit.
- A workflow that opens the release PR: PRs opened by `GITHUB_TOKEN` start
  no CI, so the required checks never run.

## Consequences

- Good: repo, tag and zip agree; releasing is merge plus Publish; a
  mismatched tag fails in seconds, before the long test jobs.
- Bad: one release PR per release.

## Confirmation

- `tests/test_release_script.py::test_prepare_writes_every_version_place`
- `tests/test_release_script.py::test_release_gate_refuses_a_wrong_tag`
- `tests/wiring_check.py` "manifest and brand images" (sizes, no `==` pin)

```sh
grep -q 'release.py check "$TAG"' .github/workflows/release.yaml
! grep -q 'update_hacs_manifest' .github/workflows/release.yaml
grep -q -- '--draft' .github/workflows/release-draft.yaml
grep -q '"zip_release": true' hacs.json
grep -q 'innova_hrds.zip' .github/workflows/release.yaml
```

## More information

Supersedes ADR-0021 (PR #17 packaging and brand images, PR #25). How PRs
record changes: ADR-0032. Steps: the `release-prep` skill.
