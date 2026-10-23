---
name: release-prep
description: Prepares a vX.Y.Z release of the integration for the owner to publish, with scripts/release.py (version, changelog heading, README banners) plus a review of plans/todo.md. Use only when asked to prepare a release.
disable-model-invocation: true
argument-hint: "[X.Y.Z | patch | minor | major]"
---

# Prepare release $ARGUMENTS

Rules: ADR-0031 (how a release is made), ADR-0032 (the CHANGELOG), ADR-0020
(only the owner merges and publishes). The script does the same as when the
owner runs it locally; this skill adds the parts that need judgement.

```
- [ ] 1. Version: $ARGUMENTS if it is X.Y.Z; otherwise bump the manifest
        version (`patch` by default; propose `minor` when Unreleased has
        Breaking changes, and ask). `python3 scripts/release.py check` first.
- [ ] 2. Read `## Unreleased` in CHANGELOG.md. Tighten bullets that break
        .claude/rules/changelog.md (user-facing, bold lead, short); do not
        drop content. Pick a short title (a few words naming the main
        changes, like the existing headings).
- [ ] 3. plans/todo.md against the Unreleased entries:
        * tick or remove items this release resolves (with the evidence
          the item asks for: a T row in UNIT_BEHAVIOUR.md, ADR-0027);
        * note items this release makes possible or more urgent;
        * change nothing that is not backed by an entry or evidence.
        List every change for the PR body.
- [ ] 4. python3 scripts/release.py <X.Y.Z> --no-git --title "<title>"
        (it runs ruff, wiring_check and adr_check; fix any failure)
- [ ] 5. python3 scripts/release.py notes <X.Y.Z>: read it as a user would.
- [ ] 6. Commit, push, open a PR "Release vX.Y.Z: <title>" whose body has
        the todo changes and the notes preview. Tell the owner: merge it;
        release-draft.yaml then drafts vX.Y.Z with these notes; review the
        draft and Publish it (normal release, not a pre-release); check
        that innova_hrds.zip is attached, re-run `package` if not.
```

The README's "Road to 1.0" is information for users, not a release step.
Never publish the release or merge the PR yourself.
