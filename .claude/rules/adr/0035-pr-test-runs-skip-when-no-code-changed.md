---
status: accepted
date: 2026-10-23
decision-makers: mikopp
topics: [ci, tests]
paths:
  - ".github/workflows/{tests,e2e}.yaml"
  - ".github/test-paths"
---

# ADR-0035: A pull request that changes no code skips the test runs, and the checks still pass

## Decision

- On `pull_request`, `tests.yaml` and `e2e.yaml` MUST run their test steps
  only when a changed file matches a pattern in `.github/test-paths`
  (integration code, tests, scripts, test dependencies, the HA image pin,
  these two workflows and the list itself). The `changes` step decides,
  from `git diff HEAD^1 HEAD` of the PR merge commit.
- Every other event (push to `main`, `schedule`, `workflow_dispatch`,
  `workflow_call` from `release.yaml`) MUST run everything.
- The skip MUST be per step (`if: steps.changes.outputs.run == 'true'`),
  never a workflow `paths:` filter or a job-level `if:`: the jobs `pytest`
  and `e2e (pinned)` are required checks (`.github/REPO_SETTINGS.md`) and
  must report success on a skipped PR.
- A file that a test reads MUST be covered by a pattern; add it to
  `.github/test-paths` when a test starts depending on a new path.

## Context

A docs-only PR (PR #52) spent about 4 minutes on pytest and e2e that test
nothing it changed. Lint (ruff, `wiring_check.py`, `adr_check.py`, the
changelog check) still runs on every PR and covers the docs a test layer
would read (register docs, entity reference).

## Considered options

- Workflow `paths:` filter: a required check that never starts stays
  "expected" and blocks the merge.
- Job-level `if:`: a skipped matrix job reports `e2e (${{ matrix.channel }})`,
  not `e2e (pinned)`, so the required check stays pending.
- A paths-filter action: one more third-party action to pin (ADR-0020) for
  what one `git diff` does.

## Consequences

- Good: a docs-only PR is green in seconds; `main` and releases are always
  fully tested.
- Bad: a test that reads a file outside the patterns is skipped when only
  that file changes; it is caught on `main` after the merge.

## Confirmation

```sh
for f in .github/workflows/tests.yaml .github/workflows/e2e.yaml; do grep -q "grep -qEf .github/test-paths" "$f"; done
! grep -nE '^\s+paths(-ignore)?:' .github/workflows/tests.yaml .github/workflows/e2e.yaml
printf 'custom_components/innova_hrds/fan.py\n' | grep -qEf .github/test-paths
! printf 'doc/entity-reference.md\nREADME.md\nCHANGELOG.md\n' | grep -qEf .github/test-paths
```

## More information

Triggers and required checks: ADR-0020. Test layers: ADR-0019.
