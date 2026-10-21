---
status: accepted
date: 2026-10-20
decision-makers: mikopp
topics: [ci]
paths:
  - ".github/**"
---

# ADR-0020: CI runs once per change with least privilege; only the owner merges or releases

## Decision

- Workflows MUST trigger on `pull_request` and on `push` to `main` only
  (plus `workflow_dispatch`; hacs also daily, e2e also nightly with the
  `beta` image allowed to fail). MUST NOT use a plain `push:` trigger.
  tests and e2e MUST cancel a superseded PR run (`concurrency`).
- Every workflow MUST set `permissions: contents: read` at the top; only
  `release.yaml`'s `package` job MAY raise it to `contents: write`.
- Actions MUST be pinned to commit SHAs with a version comment (Dependabot
  bumps them). hassfest has no release tags: it is pinned to a `master`
  commit and re-pinned by hand.
- Branch protection is a GitHub setting recorded in
  `.github/REPO_SETTINGS.md`. MUST NOT add "Restrict updates" on the default
  branch, nor an app to any bypass list.
- Agents MUST NOT merge pull requests or publish releases; they open PRs
  and leave merging and releasing to the owner.

## Context

A plain `push:` ran every workflow twice for a branch with an open PR.
Mutable action tags let a compromised upstream run code in CI. "Restrict
updates" forced a bypass on every merge (PR #29). A ruleset cannot stop an
installed app from merging a green PR, so the rule is the agent's.

## Consequences

- Good: one run per change, minimal token scope, supply chain pinned.
- Bad: hassfest needs manual re-pinning.

## Confirmation

```sh
for f in .github/workflows/*.yaml; do grep -q '^permissions:' "$f"; done
! grep -hE '^\s*-?\s*uses: [^.]' .github/workflows/*.yaml | grep -vE '@[0-9a-f]{40}( |$)'
! grep -nE -A1 '^  push:' .github/workflows/*.yaml | grep -E -- '-[0-9]+-' | grep -v 'branches: \[main\]'
```

## More information

`b8bafa8` (SHA pins), PR #16 (triggers), PR #27 (permissions, pins),
PR #29 (repository settings).
