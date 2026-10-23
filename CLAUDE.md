# ha_innova_hrds

Home Assistant custom integration for the **Innova DEH+ / hej.luft HRDS+** air
dehumidification module over **Modbus TCP**. Domain `innova_hrds`, code in
`custom_components/innova_hrds/`. Minimum Home Assistant 2026.10, `pymodbus>=3.13.1`
(ADR-0004). Architecture shared with the sibling `ha_comfoconnectpro`.

## Decisions are ADRs

Every design decision is an ADR in [`doc/adr/`](doc/adr/README.md) (index
there). The accepted ADRs that govern a file load into your context
automatically when you read that file (real files in `.claude/rules/adr/`,
path-scoped). Proposed and superseded ADRs (`doc/adr/proposed/`,
`doc/adr/superseded/`) are history: do not read, search or list them in normal
work; `/adr` gets a digest from `python3 tests/adr_check.py --history`.
For logic in a file no ADR path covers (a new module), the topic map
`.claude/rules/adr-topics.md` (loads with any code) names the ADRs per topic:
read those before the first edit. ADRs are binding: follow them, or stop and
propose a superseding ADR. Use the `/adr` skill to record a new decision
(`new`), change one (`supersede`), reject one, or check a diff before a PR
(`check`); it challenges a decision that revives a retired one (ADR-0029).
Do not restate ADR content in this file.

## Invariants (details in the cited ADR)

* All Modbus writes go through `hub.write_entity_value`; never add a periodic
  or unconditional write (ADR-0006, ADR-0023).
* The integration writes nothing on its own except the headless PH01/HA00
  sync (ADR-0010); never the PH02/PH27/PH28 Modbus enables (ADR-0022).
* Every request passes `check_write_allowed`: enables, season, brine guard,
  operation gate (ADR-0012, ADR-0013, ADR-0014).
* Verify the device before anything can write (ADR-0009).
* Entities show the unit's read-back, and unknown or unavailable rather than
  stale (ADR-0005, ADR-0006). No option may shadow a register (ADR-0008).
* The entity reference `doc/entity-reference.md` is the only list of entities
  and mirrors the devices (main / setup / installer). Change it in the same
  commit as any entity, group or device change; `wiring_check.py` fails on a
  difference (ADR-0030).
* Never merge a PR or publish a release (ADR-0020).

## Code map

| File | Role |
|---|---|
| `const.py` | `ENTITIES_DICT` (every register), `init()` classification into typed dicts, key groups (`SETUP_KEYS`, `CONFIG_KEYS`, `DIAGNOSTIC_KEYS`, `FAN_KEYS`, `OPERATIONAL_KEYS`, `PENDING_KEYS`, `MODBUS_ENABLE_FOR`), option names and defaults |
| `__init__.py` | Setup/unload, registry migrations, and `HrdsModbusHub`: poll (`_do_read_cycle`, `_read_blocks`), decode (`_decode_all`), headless sync, derived state (`active_season`, `int_effect`, `auto_capable`, `is_heating`, `is_cooling`, setup and water issues, `_compute_derived`), guards (`check_write_allowed`), writes (`write_entity_value`, `_write_registers`), pending requests, brine guard |
| `entity_common.py` | `HubBackedEntity` (availability, hub callback), `setup_platform_from_types`, device infos |
| `climate.py`, `fan.py` | Composite entities (not one register each) |
| `sensor.py` … `button.py` | Generic platforms built from the typed dicts |
| `identity.py` | FC 43 + register fingerprint check |
| `config_flow.py` | Config and options flows (host, port, unit id, model, options) |
| `installer_params.py` | Installer-menu rows (`inst_<code>` keys) |
| `tests/diagnose_hrds.py` | Read-only bring-up script for a real unit (`tests/CLAUDE.md`) |

`hub.data[key]` holds decoded values: `"on"`/`"off"` or an enum slug for
switches and selects, `float` for numbers, `None` for unknown. Entities
subscribe with `hub.async_add_my_modbus_sensor(callback)`.

## The unit in brief

* Two requests: **DEU** (`dehumidify`, 1140) and **INT**
  (`integration_request`, 1139). INT dehumidifies and cools in summer and
  heats in winter (valve and pump only, no compressor).
* Variants (type plate `HRDS+ 30 H R K DC`): size 30/50 has no register (the
  `model` option); **R** (recirculation fan + damper) shows as damper output
  1134 not `disabled` (PG01 is the fan arrangement, not this); **DC** (INT
  available) is PG02 = 1.
* Only analog registers (FC 03/04), direct PDU addresses, temperatures ×0.1,
  fan/percent ×0.01, humidity ×1.

Everything else about the unit: `doc/references/UNIT_BEHAVIOUR.md`.

## Where to find what

Each topic has one home; link to it instead of repeating it (ADR-0027).

| Topic | Home |
|-------|------|
| Why the integration is built as it is (guards, write policy, entity mapping, tests, CI) | [`doc/adr/`](doc/adr/README.md) |
| How the unit behaves, and what was tested on real hardware (evidence log `T1…`) | [`doc/references/UNIT_BEHAVIOUR.md`](doc/references/UNIT_BEHAVIOUR.md) |
| Which registers exist: addresses, encodings, values, installer table (§16) | [`doc/references/MODBUS_REGISTERS.md`](doc/references/MODBUS_REGISTERS.md) |
| Source PDFs and how to search them, technical data, airflow estimate | [`doc/references/README.md`](doc/references/README.md) |
| Every entity, by device, and why each device exists | [`doc/entity-reference.md`](doc/entity-reference.md) (ADR-0030) |
| Adding or changing an entity | `.claude/rules/entities.md` (loads with `const.py`) |
| User-facing description | [`README.md`](README.md); German summary [`README.de.md`](README.de.md) (intro, devices, quick start, what it does, and a table of contents of the English sections: change it together with the English text) |
| Which units and installations are known to work, and what was seen on each | [`doc/tested-setups.md`](doc/tested-setups.md) |
| Open hardware questions and test plans | [`plans/todo.md`](plans/todo.md) |
| Tests: layers, simulator, how to run | [`tests/CLAUDE.md`](tests/CLAUDE.md) |
| Repository settings that are not files | [`.github/REPO_SETTINGS.md`](.github/REPO_SETTINGS.md) |
| Preparing a release | `python3 scripts/release.py X.Y.Z` (owner) or the `/release-prep` skill (agent); ADR-0031 |
| Writing a CHANGELOG entry (`## Unreleased`, never a version) | `.claude/rules/changelog.md` (ADR-0032) |

## Commands

```
ruff check . && ruff format .
python3 tests/wiring_check.py   # registers, translations, platforms, groups; no HA needed
python3 tests/adr_check.py      # ADR format, scopes, folders, indexes, topic map (--fix)
python3 scripts/release.py check   # CHANGELOG under Unreleased, versions agree
pytest tests/sim tests/ha tests/test_wiring.py tests/test_release_script.py   # needs requirements_test.txt, Python 3.14
```

Run `wiring_check.py` after any entity change and `adr_check.py` after any
ADR change.

## CI

GitHub Actions in `.github/workflows/`: `lint.yaml` (Ruff, wiring check, ADR
check, changelog check), `hassfest.yaml`, `hacs.yaml`, `tests.yaml` (in-process, coverage
≥ 90 %), `e2e.yaml` (real HA container), `release-draft.yaml` (drafts the release when a release PR is merged),
`release.yaml` (version check, then all of them on the tag, then the zip). Triggers, permissions and pins: ADR-0020. Release
packaging and brand images: ADR-0031. Test layering: ADR-0019.
