# ha_innova_hrds

Home Assistant custom integration for the **Innova DEH+ / hej.luft HRDS+** air
dehumidification module via **Modbus TCP**. It serves a similar purpose to the
sibling `ha_comfoconnectpro` integration and shares its architecture.

The integration domain is `innova_hrds`; the component lives in
`custom_components/innova_hrds/`.

## Architecture

All Modbus registers are declared once in `ENTITIES_DICT` in `const.py`. The
`init()` function (called at import time) classifies each entry into typed dicts
— `SENSOR_TYPES`, `BINARYSENSOR_TYPES`, `BINARY_TYPES`, `NUMBER_TYPES`,
`SELECT_TYPES` — based on register type and data shape. Each platform file
(`sensor.py`, `switch.py`, …) calls `setup_platform_from_types()` from
`entity_common.py`, which instantiates the appropriate `HubBackedEntity`
subclass for every entry in its dict.

The **climate entity** is the exception: it is a composite entity not backed by
a single register. It is created manually in `climate.py:async_setup_entry`
using `get_hub_and_device_info()` and aggregates several status registers.

## Device specifics (important — differ from comfoconnectpro)

* **Only analog registers exist.** The HRDS+ has no Modbus coils or discrete
  inputs; even 0/1 flags are analog. So there are exactly two register types:
  * `C_REG_TYPE_INPUT_REGISTERS` (FC 04, read-only)
  * `C_REG_TYPE_HOLDING_REGISTERS` (FC 03/06/16, read-write)
* **Addresses are direct PDU addresses** (the `Addr DEC` column in the PDF) —
  do **not** subtract 1.
* **The address space is wide and sparse** (~0x0100–0x077A). A single block read
  would exceed Modbus' 125-register limit, so the hub reads in **contiguous
  chunks** (`_build_blocks` in `__init__.py`, capped at `C_MAX_BLOCK`, merging
  gaps up to `C_MAX_GAP`).
* **"by BMS" enables are mandatory.** Writes are ignored unless PH02/PH27/PH28
  are set. The hub writes these once per connection (`_enable_bms_control_locked`,
  driven by `BMS_ENABLE_KEYS`); they are also exposed as switches.
* **Scaling:** temperatures/setpoints ×0.1 (`FAKTOR`), fan/percent registers
  ×0.01, humidity ×1.

The full register documentation is in
[`references/MODBUS_REGISTERS.md`](references/MODBUS_REGISTERS.md), distilled
from the manufacturer PDFs in `references/`.

## Adding or modifying an entity

1. Add/edit the entry in `ENTITIES_DICT` in `const.py`.
2. Register fields: `RT` (register type), `REG` (decimal address), `DT`
   (`C_DT_INT16`/`C_DT_UINT16`), `NAME`, and optionally `UNIT`, `FAKTOR`, `MIN`,
   `MAX`, `STEP`, `VALUES` (enum/select), `SWITCH` (0/1 flag), `PF` (platform
   override).
3. Add translation strings to `translations/en.json` and `translations/de.json`
   under the matching platform key (and `state` slugs for enums).
4. No platform code changes are needed unless you add a new platform.

Classification rules (`_classify` in `const.py`):

| Register type | + shape | → entity |
|---------------|---------|----------|
| input (R/O)   | plain numeric | sensor |
| input (R/O)   | `VALUES`      | enum sensor |
| input (R/O)   | `SWITCH`      | binary_sensor |
| holding (R/W) | `SWITCH`      | switch |
| holding (R/W) | `VALUES`      | select |
| holding (R/W) | temp unit, no `PF` | climate (avoid: set `PF=Platform.NUMBER`) |
| holding (R/W) | otherwise     | number |

## Hub (`HrdsModbusHub` in `__init__.py`)

* Polls all registers every N seconds (default 30) via
  `async_refresh_modbus_data()`, reading input and holding blocks separately.
* Decoded values are stored in `hub.data[entity_key]` as Python-native types
  (`str` for selects/switches → `"on"`/`"off"` or slug, `float` for numerics).
* Write via `hub.write_entity_value(entity_key, value)` — encodes, writes, and
  triggers a refresh. `setter_function_callback` is the entity-facing wrapper.
* Entity callbacks register via `hub.async_add_my_modbus_sensor(callback)`.

## Climate entity mapping

* `current_temperature` ← `room_temperature`; `current_humidity` ← `room_humidity`.
* `hvac_mode` ∈ {OFF, DRY, COOL}; setting it writes `unit_on_off` +
  `dehumidify` + `active_cooling`.
* `hvac_action` derived from `unit_status` / `compressor_status` /
  `dehumidify_request`.
* `target_humidity` ← `humidity_setpoint`; `target_temperature` ← `summer_setpoint`.

## Linting

```
ruff check .
ruff format .
```

## CI

GitHub Actions (in `.github/workflows/`):
* `lint.yaml` — Ruff lint + format check (Python).
* `hassfest.yaml` — Home Assistant manifest/translation validation.
* `hacs.yaml` — HACS repository validation (also daily); ignores `brands` (not yet in the HACS brands repo).
* `release.yaml` — re-runs hassfest + hacs when a release is published.

No unit tests yet.
