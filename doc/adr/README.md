# Architecture decision records

Why the integration is built the way it is, one decision per file. The table
below links every accepted ADR; [ADR-0001](../../.claude/rules/adr/0001-record-decisions-as-path-scoped-adrs.md)
describes the format and how agents use it. In short:

* Each ADR starts with its rules (`## Decision`, MUST / MUST NOT / SHOULD),
  then context, consequences and how the decision is checked
  (`## Confirmation`).
* The folder follows the status. **Accepted** ADRs are real files in
  [`.claude/rules/adr/`](../../.claude/rules/adr/) (also reachable through the
  `accepted` symlink next to this file): Claude Code loads one when it reads a
  file matching the ADR's `paths`, and not otherwise. **Proposed** ADRs are in
  [`proposed/`](proposed/README.md); **superseded**, rejected and deprecated
  ones in [`superseded/`](superseded/README.md). Nothing loads those two
  folders, and agents open them only when recording an ADR (ADR-0029).
* `topics` says what a decision is about.
  [`.claude/rules/adr-topics.md`](../../.claude/rules/adr-topics.md) lists the
  ADRs per topic and loads with any code, test or CI file, so a decision also
  reaches a new file that no `paths` glob covers yet.
* A changed decision gets a new ADR that supersedes the old one, which moves
  to `superseded/` and stops loading. A decision that brings back a retired
  one needs new evidence and says so (`revives`).
* `python3 tests/adr_check.py` checks all of this (lint workflow); `--fix`
  rewrites the generated files and moves an ADR whose status changed;
  `--for FILE...` and `--topic TOPIC...` list the accepted ADRs that apply;
  `--history` digests the proposed and retired ones.
* New or changed decision: ask an agent to use the `/adr` skill, or start from
  its [template](../../.claude/skills/adr/template.md).

<!-- adr-index:start -->
| ADR | Decision | Loads for |
|---|---|---|
| [0001](../../.claude/rules/adr/0001-record-decisions-as-path-scoped-adrs.md) | Record decisions as path-scoped ADRs that agents load on demand | `doc/adr/*.md`, `.claude/skills/adr/**`, `.claude/rules/adr-topics.md`, `tests/adr_check.py`, `**/CLAUDE.md` |
| [0002](../../.claude/rules/adr/0002-one-register-table-drives-every-entity.md) | One register table drives every entity | `const.py`, `entity_common.py`, `{sensor,binary_sensor,switch,number,select,button}.py` |
| [0004](../../.claude/rules/adr/0004-home-assistant-and-pymodbus-versions-follow-home-assistant.md) | Home Assistant and pymodbus versions follow Home Assistant | `manifest.json`, `hacs.json`, `requirements_test.txt`, `tests/e2e/requirements.txt`, `.github/ha-versions/Dockerfile`, `.github/dependabot.yml` |
| [0005](../../.claude/rules/adr/0005-unavailable-rather-than-stale.md) | An entity is unavailable or unknown rather than stale | `__init__.py`, `entity_common.py` |
| [0006](../../.claude/rules/adr/0006-a-write-takes-or-raises-and-state-is-the-read-back.md) | A write takes or raises, and state is the unit's read-back | `__init__.py`, `entity_common.py`, `{switch,number,select,fan,climate}.py` |
| [0008](../../.claude/rules/adr/0008-fan-state-is-the-actual-output.md) | Fan state is the actual output; device limits stay device registers | `fan.py`, `climate.py`, `config_flow.py`, `__init__.py` |
| [0009](../../.claude/rules/adr/0009-verify-the-device-before-writing.md) | Verify the device is an HRDS+ before writing anything | `identity.py`, `config_flow.py` |
| [0010](../../.claude/rules/adr/0010-headless-by-default.md) | Headless by default; PH01 and HA00 are the only settings written unasked | `__init__.py`, `config_flow.py` |
| [0011](../../.claude/rules/adr/0011-no-probe-means-no-reading-and-no-target.md) | No probe means no reading and no target | `__init__.py`, `climate.py` |
| [0012](../../.claude/rules/adr/0012-operational-requests-need-the-users-go-ahead.md) | Operational requests need the user's go-ahead | `__init__.py`, `{switch,climate,fan}.py` |
| [0013](../../.claude/rules/adr/0013-integration-request-summer-by-default-winter-heating-opt-in.md) | The integration request cools in summer; winter heating is opt-in and the unit's own is reported | `__init__.py`, `{climate,select,binary_sensor,config_flow}.py` |
| [0014](../../.claude/rules/adr/0014-brine-guard-gates-starts-and-brine-never-heats.md) | On brine nothing heats, and a guard gates every start | `__init__.py`, `{config_flow,binary_sensor,climate}.py` |
| [0015](../../.claude/rules/adr/0015-the-unit-runs-its-water-circuit.md) | The unit runs its water circuit; the integration only watches | `__init__.py`, `installer_params.py` |
| [0016](../../.claude/rules/adr/0016-setup-lives-in-the-integration-on-child-devices.md) | Setup lives in the integration, on a linked setup device | `const.py`, `entity_common.py` |
| [0017](../../.claude/rules/adr/0017-installer-menu-opt-in-never-polled.md) | The installer menu is opt-in, never polled, and never dangerous | `installer_params.py`, `button.py`, `__init__.py`, `const.py` |
| [0018](../../.claude/rules/adr/0018-read-in-small-blocks-and-fail-fast.md) | Read in small blocks; fail the poll on a missing reply | `__init__.py`, `tests/diagnose_hrds.py`, `tests/sim/server.py` |
| [0019](../../.claude/rules/adr/0019-tests-run-the-real-client-against-a-simulated-unit.md) | Tests run the real client against a simulated unit; e2e only for what needs a real Home Assistant | `tests/**`, `.github/workflows/{tests,e2e}.yaml` |
| [0020](../../.claude/rules/adr/0020-ci-runs-once-with-least-privilege-and-only-the-owner-merges.md) | CI runs once per change with least privilege; only the owner merges or releases | `.github/**` |
| [0022](../../.claude/rules/adr/0022-modbus-enables-are-the-users.md) | The Modbus enables are the user's | `__init__.py`, `{climate,switch}.py` |
| [0023](../../.claude/rules/adr/0023-write-only-what-changes.md) | Write only what changes (EEPROM) | `__init__.py`, `{climate,fan,switch,number,select}.py` |
| [0024](../../.claude/rules/adr/0024-request-switches-show-the-command-until-confirmed.md) | Request switches show the command until the unit confirms it | `__init__.py`, `switch.py` |
| [0025](../../.claude/rules/adr/0025-climate-follows-what-the-unit-can-do-and-does.md) | The climate mode says what can make the unit act; the action says what it does | `climate.py`, `__init__.py` |
| [0026](../../.claude/rules/adr/0026-renamed-keys-are-migrated.md) | A renamed or re-typed key is migrated in the entity registry | `__init__.py`, `translations/*.json` |
| [0027](../../.claude/rules/adr/0027-one-home-per-topic-and-evidence-for-unit-facts.md) | One home per topic; every unit fact carries its evidence | `doc/references/*.md`, `plans/*.md`, `README.md` |
| [0029](../../.claude/rules/adr/0029-retired-adrs-are-history-revival-needs-new-evidence.md) | Proposed and retired ADRs are history; reviving one needs new evidence | `doc/adr/proposed/**`, `doc/adr/superseded/**`, `.claude/skills/adr/**`, `.claude/settings.json` |
| [0030](../../.claude/rules/adr/0030-entity-reference-is-the-source-of-truth-and-mirrors-the-devices.md) | The entity reference is the one source of truth and mirrors the devices | `const.py`, `entity_common.py`, `installer_params.py`, `translations/*.json`, `doc/entity-reference.md` |
| [0031](../../.claude/rules/adr/0031-release-from-a-prepared-commit.md) | Release from a prepared commit: one script prepares, CI verifies, the owner publishes a draft | `scripts/release.py`, `.github/workflows/release.yaml`, `.github/workflows/release-draft.yaml`, `.claude/skills/release-prep/**`, `hacs.json`, `manifest.json`, `brand/**` |
| [0032](../../.claude/rules/adr/0032-prs-record-changes-under-unreleased-and-never-set-a-version.md) | PRs record changes under Unreleased in release-notes shape and never set a version | `CHANGELOG.md`, `.claude/rules/changelog.md` |

Not in force and not loaded; read only when recording an ADR (ADR-0029): [proposed (1)](proposed/README.md), [superseded (3)](superseded/README.md).
<!-- adr-index:end -->
