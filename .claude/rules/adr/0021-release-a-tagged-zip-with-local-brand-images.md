---
status: accepted
date: 2026-10-20
decision-makers: mikopp
topics: [ci]
paths:
  - ".github/workflows/release.yaml"
  - ".github/scripts/**"
  - "hacs.json"
  - "custom_components/innova_hrds/manifest.json"
  - "custom_components/innova_hrds/brand/**"
  - "CHANGELOG.md"
---

# ADR-0021: Release a tagged zip; brand images ship with the integration

## Decision

- A release MUST be a normal GitHub release (not a pre-release: HACS hides
  those) whose tag is `vX.Y.Z`; `update_hacs_manifest.py` rejects anything
  else.
- `release.yaml` MUST run hassfest, hacs, tests and e2e on the tagged commit
  and only then let `package` stamp the tag into `manifest.json`, zip
  `custom_components/innova_hrds` and attach `innova_hrds.zip`
  (`hacs.json`: `zip_release`, `filename`). A release without the zip MUST
  be fixed by re-running `package`, not left.
- Before a release the manifest version, a `CHANGELOG.md` entry (its text is
  the release body), the README status banner and "Road to 1.0" MUST be
  current. Preparing that is agent work; publishing is the owner's
  (ADR-0020).
- Brand images MUST ship in `custom_components/innova_hrds/brand/`
  (`icon`, `logo`, `@2x`, `dark_*`), the Innova mark recoloured `#00643e`
  (white for dark). MUST NOT use Home Assistant branded images. `hacs.yaml`
  ignores the `brands` check.

## Context

HACS installs the release asset, so a release without the zip cannot be
installed. Home Assistant 2026.3+ prefers images in the integration over
the brands CDN, which avoids a brands-repo submission.

## Consequences

- Good: a release is installable only after every test passed on its commit.
- Bad: a failed `package` job leaves a broken release until re-run.

## Confirmation

- `tests/wiring_check.py` "manifest and brand images" (sizes, no `==` pin)

```sh
grep -q '"zip_release": true' hacs.json
grep -q 'innova_hrds.zip' .github/workflows/release.yaml
```

## More information

PR #17 (packaging, brand images), PR #25 (beta release). Steps: the
`release-prep` skill.
