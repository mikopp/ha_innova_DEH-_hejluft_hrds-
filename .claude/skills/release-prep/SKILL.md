---
name: release-prep
description: Prepares a vX.Y.Z release of the integration for the owner to publish (manifest version, changelog, README banner). Use only when asked to prepare a release.
disable-model-invocation: true
argument-hint: "<X.Y.Z>"
---

# Prepare release v$ARGUMENTS

Rules: ADR-0021 (packaging) and ADR-0020 (only the owner publishes).

```
- [ ] 1. custom_components/innova_hrds/manifest.json "version": "$ARGUMENTS"
- [ ] 2. CHANGELOG.md: "## $ARGUMENTS (date): summary" from "Unreleased";
        its text becomes the release body
- [ ] 3. README.md: status banner and "Road to 1.0" still true
        (drop the beta wording at 1.0)
- [ ] 4. ruff check . && ruff format --check . && python3 tests/wiring_check.py
        && python3 tests/adr_check.py
- [ ] 5. Open a PR. Tell the owner: publish a normal release (not a
        pre-release) with tag v$ARGUMENTS; check that innova_hrds.zip is
        attached, and re-run the package job if it is not.
```

Never publish the release or merge the PR yourself.
