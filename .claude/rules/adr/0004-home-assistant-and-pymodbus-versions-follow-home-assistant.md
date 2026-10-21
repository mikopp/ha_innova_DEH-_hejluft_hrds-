---
status: accepted
date: 2026-10-20
decision-makers: mikopp
topics: [dependencies]
paths:
  - "custom_components/innova_hrds/manifest.json"
  - "hacs.json"
  - "requirements_test.txt"
  - "tests/e2e/requirements.txt"
  - ".github/ha-versions/Dockerfile"
  - ".github/dependabot.yml"
---

# ADR-0004: Home Assistant and pymodbus versions follow Home Assistant

## Decision

- The minimum Home Assistant release is the one in `hacs.json`
  (`homeassistant`); code MAY use any API of that release and MUST NOT use
  one it deprecates.
- `manifest.json` MUST require `pymodbus>=X`, X being the pymodbus that
  minimum release ships; MUST NOT pin `==` (hassfest rejects an exact pin on
  a package Home Assistant depends on).
- The test layers MUST run one Home Assistant release:
  `pytest-homeassistant-custom-component` in `requirements_test.txt` and the
  image in `.github/ha-versions/Dockerfile` are bumped together, and the
  tests pin exactly the pymodbus that release ships.
- pymodbus MUST NOT be bumped on its own (Dependabot ignores it).
- A deprecation Home Assistant reports for this integration is a test
  failure, in both layers.

## Context

The integration runs on the pymodbus Home Assistant installs; testing
against another version tests something users never run. Dependabot's
pymodbus 3.16 PRs (#18, #20) were closed for that reason. A deprecated
`via_device` call only surfaced as a log warning until the deprecation guard
made it fail (PR #23).

## Consequences

- Good: CI tests exactly what users run; HA deprecations are caught before
  they break.
- Bad: raising the minimum HA is a deliberate edit to `hacs.json`, the
  manifest requirement and both test pins.

## Confirmation

- `tests/ha/test_versions.py::test_in_process_ha_matches_docker_image`
- `tests/ha/test_versions.py::test_pymodbus_matches_home_assistant`
- `tests/e2e/test_zz_log_hygiene.py::test_no_errors_or_deprecations_from_the_integration`

```sh
grep -q '"pymodbus>=' custom_components/innova_hrds/manifest.json
! grep -q '==' custom_components/innova_hrds/manifest.json
```

## More information

`77f2aec` (HA 2026.9 baseline), PR #17 (hassfest `>=`), PR #22 (version
alignment), PR #23 (deprecation guard).
