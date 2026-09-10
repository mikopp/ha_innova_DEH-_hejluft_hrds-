# ha_innova_hrds

Home Assistant custom integration for the **Innova DEH+ / hej.luft HRDS+** air
dehumidification module via **Modbus TCP**. Minimum Home Assistant version is
**2026.9**; `pymodbus` is pinned to `3.13.1`, the version HA 2026.9 ships. It serves a similar purpose to the
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

The **climate** and **fan** entities are the exceptions: they are composite,
not backed by a single register, and are declared directly in `init()`
(`CLIMATE_TYPES` / `FAN_TYPES`) rather than derived from `ENTITIES_DICT`.

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
  are set. `_sync_bms_enables_locked` re-asserts them **every poll**, driven by
  the polled read-back rather than a one-shot flag, so a device power-cycle that
  clears them self-heals. They are also exposed as switches — and because the
  hub re-asserts them, turning one off by hand is undone on the next poll.
* **Scaling:** temperatures/setpoints ×0.1 (`FAKTOR`), fan/percent registers
  ×0.01, humidity ×1.

The full register documentation is in
[`references/MODBUS_REGISTERS.md`](references/MODBUS_REGISTERS.md), distilled
from the manufacturer PDFs in `references/`.

## Reference material

| File | Use for |
|------|---------|
| `references/MODBUS_REGISTERS.md` | **Start here.** Register addresses, alarm bit map, alarm code table, cookbook for common operations. |
| `references/README.md` | Implementation notes: airflow / passive flow / fan-integration / active-cooling distinction; variant detection (30/50, R/non-R, DC); fan-speed-to-airflow formula; probe wiring; alarm interpretation. |
| `references/HRDS+_Technisches_Handbuch_DE.txt` | Full text of the 87-page German technical handbook (searchable). Firmware parameters (PF27/PF28 fan min %, PG01 machine type, BMS enable, etc.), performance tables, wiring diagrams. |
| `references/Innova_DEH+_H_Installation_Manual_EN.txt` | Innova DEH+ H installation manual EN — the Italian OEM original of the HRDS+. Alarm table (with effect descriptions), microswitch DIP settings, VMC wiring. |
| `references/HRDS+_Modbus_RTU_RS485_DE.pdf` | Modbus RTU/RS-485 connection manual — original source of the register table in MODBUS_REGISTERS.md. |
| `references/HRDS+_Technisches_Handbuch_DE.pdf` | Original German technical handbook PDF (87 pp). |
| `references/HRDS+_Benutzerhandbuch_DE.pdf` | End-user handbook DE (12 pp). |

## Adding or modifying an entity

1. Add/edit the entry in `ENTITIES_DICT` in `const.py`.
2. Register fields: `RT` (register type), `REG` (decimal address), `DT`
   (`C_DT_INT16`/`C_DT_UINT16`), `NAME`, and optionally `UNIT`, `FAKTOR`, `MIN`,
   `MAX`, `STEP`, `VALUES` (enum/select), `DEFAULT` (default raw value for a
   select), `DC` (explicit sensor device class, overriding the `UNIT`-derived
   default), `SWITCH` (0/1 flag), `BITMASK`/`BITMASK_INVERT` (extract one bit
   from a packed register), `PF` (platform override).
3. Add translation strings to `translations/en.json` and `translations/de.json`
   under the matching platform key (and `state` slugs for enums).
4. No platform code changes are needed unless you add a new platform. If you do
   add one, it needs **both** a module and an entry in `PLATFORMS` — a typed
   dict with no platform file produces no entities at all, silently.
5. Run `python3 tests/wiring_check.py`, which catches exactly that mistake plus
   missing translations and undocumented registers.

### Bitmask binary sensors (alarm / packed-register bits)

Add `BITMASK: N` to extract bit N (0-indexed) from a packed register. Combine
with `SWITCH: {"off": 0, "on": 1}` (triggers binary_sensor classification).
- Without `BITMASK_INVERT`: bit set → `"on"`. Use for alarm sensors (alarm active = ON).
- With `BITMASK_INVERT: True`: bit set → `"off"`. Use for "probe OK" sensors (alarm set = probe NOT OK).

Alarm bit positions (§9.1 in `MODBUS_REGISTERS.md`):
- `PackedAlarm_1` (reg 768): bit N = AL(N+1). e.g. AL11 = bit 10, AL12 = bit 11, AL16 = bit 15.
- `PackedAlarm_2` (reg 769): bit N = AL(N+17). e.g. AL22 = bit 5, AL28 = bit 11, AL30 = bit 13.
- `PackedAlarm_3` (reg 770): bit 0=AL33, bit 1=AL34, bit 2=AL35, bit 6=AL39.

### Computed (non-register-backed) sensors

Declare in `COMPUTED_SENSORS` dict in `const.py` (key + NAME + UNIT). `init()`
registers them into `SENSOR_TYPES`. The hub writes their values in
`_compute_derived()` after each poll. See airflow sensors (`C_SUPPLY_FAN_AIRFLOW`
etc.) for the pattern.

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

## Device variants (30 vs 50, R vs non-R, DC)

The product code on the type plate encodes the variant: `HRDS+ 30 H R K DC`.

| Field | Values | Meaning |
|-------|--------|---------|
| `30`/`50` | size | Max airflow 300 / 500 m³/h. **No register** — set `model` in config. |
| `R` | optional | Has recirculation fan + motorised damper + air filter. `PG01_MachineType` (1797) = `1` (VMC). Non-R = `0`. |
| `DC` | optional | Has active cooling. `PG02_EnableIntegration` (1798) = `1`. |

**Non-R variant always runs on passive MVHR airflow** — no recirculation fan at all.
This proves the compressor can operate without the unit's own fan running. The R
variant can also run fan-off (passive flow only): write 0 to `PM20_SupplyFan_Manual`
(1614). Compressor self-protects via **AL11** (low-pressure / frost-thermostat, reg
768 bit 10) if airflow is insufficient.

Fan minimum speed during DEU/INT is configurable: **PF28** (dehumidify) and **PF27**
(integration) default 50 % but can be set 0–PF10. The 130 m³/h (30) / 190 m³/h (50)
figures in the technical data are the tested spec range, **not** a firmware floor.

## Hub (`HrdsModbusHub` in `__init__.py`)

* Polls all registers every N seconds (default 30) via
  `async_refresh_modbus_data()`, reading input and holding blocks separately.
  Blocks never span an address belonging to the other function code, and a
  failed block is retried register-by-register so one bad address cannot blank
  every entity.
* `last_update_success` drives `HubBackedEntity.available`. Listeners are
  notified on failure too — that is what moves entities to `unavailable`
  instead of leaving them showing stale readings.
  **Careful:** register-backed entities are additionally gated on their key
  being present in `hub.data`, but `hub.data` only ever holds `ENTITIES_DICT`
  keys. Composite entities (climate, fan) have no key of their own, so
  `available` special-cases anything not in `ENTITIES_DICT` — without that they
  are permanently unavailable. Computed sensors (`COMPUTED_SENSORS`) take the
  same branch. `tests/wiring_check.py` guards this.
* Decoded values are stored in `hub.data[entity_key]` as Python-native types
  (`str` for selects/switches → `"on"`/`"off"` or slug, `float` for numerics).
* Write via `hub.write_entity_value(entity_key, value)` — encodes, writes, and
  schedules a **debounced** refresh. It raises `HomeAssistantError` if the write
  did not take, so a rejected write is not silently reported as success.
  `setter_function_callback` is the entity-facing wrapper.
* Entity callbacks register via `hub.async_add_my_modbus_sensor(callback)`.

## Climate entity mapping

* `current_temperature` ← `room_temperature`; `current_humidity` ← `room_humidity`.
* `hvac_mode` ∈ {OFF, DRY, COOL}; setting it writes `unit_on_off` +
  `dehumidify` + `active_cooling`.
* `hvac_action` derived from `unit_status` / `compressor_status` /
  `dehumidify_request`.
* `target_humidity` ← `humidity_setpoint`; `target_temperature` ← `summer_setpoint`.
* `min_humidity` / `max_humidity` follow the unit's own PH29/PH30 clamps.
* `current_temperature` / `current_humidity` report `None` while the matching
  probe-fault alarm is active.

## Fan entity

`fan.py` exposes the recirculation fan as a percentage. It reports the
**commanded** speed (holding register 1614, which is also polled), not
`outAO_SupplyFan` (639) — reading back the modulated output would make the
entity chase the unit's own modulation away from the setpoint. Actual output
and RPM are exposed as state attributes instead.

The climate entity's `fan_mode` derives from the **same** register 1614, so the
two entities cannot contradict each other about one fan. Both write 1614; that
is fine, last writer wins. If you ever change one read-back source, change the
other.

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

`tests/wiring_check.py` runs without Home Assistant installed: it stubs the HA
API, imports `const.py`, and asserts that every entity is classified, every
declared platform has a module, every entity has `en`/`de` translations, every
register is documented in `references/MODBUS_REGISTERS.md`, and no input block
spans a holding address. It is not a substitute for real tests, but it catches
the failures this integration has actually had.
