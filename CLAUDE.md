# ha_innova_hrds

Home Assistant custom integration for the **Innova DEH+ / hej.luft HRDS+** air
dehumidification module via **Modbus TCP**. Minimum Home Assistant version is
**2026.10**; `pymodbus` is required as `>=3.13.1` (the version HA 2026.10 ships;
hassfest rejects an exact `==` pin on a package HA depends on). It serves a similar purpose to the
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
  gaps up to `C_MAX_GAP`). Keep the cap small: the real unit behind its RS-485
  gateway never answered a 120-register read (0.9.0 did not load), so it is
  10, which the diagnostic read the whole map with. If a block still gets no
  reply while a single register answers *promptly* (`C_PROBE_MAX_SECONDS`;
  pymodbus' retry can pick up a late answer and fake a working link), the hub
  halves the cap for its lifetime (`_shrink_blocks`); a dead link fails the
  poll instead.
* **"by BMS" enables are mandatory.** Writes are ignored unless PH02/PH27/PH28
  are set: PH02 gates on/off, PH28 gates the DEU request, PH27 gates the INT
  request (key `enable_integration_bms`; it is not a cooling mode). PG02 (1798) is
  a different thing, an installer setting saying the unit has INT at all, and is
  only shown read-only (`integration_available`). `_sync_required_settings_locked` re-asserts them **every poll**, driven
  by the polled read-back rather than a one-shot flag, so a device power-cycle
  that clears them self-heals. They are also exposed as switches — and because
  the hub re-asserts them, turning one off by hand is undone on the next poll.
* **Headless by default (`has_display` option, default off).** With no CNU2
  display the unit must have **PH01 (1777) = 0** and **HA00 (1803) = 0**, else
  it sits in `off_by_display` forever (an OFF from any source beats a Modbus ON)
  and waits for room T/H from a display that is not there. In headless mode the
  same `_sync_required_settings_locked` asserts both (`HEADLESS_SETTINGS` in
  `const.py`). With `has_display` on, they are left alone.
* **Device identity is verified before anything is written** (`identity.py`,
  called from `async_setup_entry` and from the config/options flow). FC 43/14
  must report vendor `EVCO` and a product code starting `EPB9` (a real unit
  reports `EVCO` / `EPB9ORSINDEU` / `V01.00.09.02`), and the four status
  registers must hold documented enum values. If the gateway does not forward
  FC 43 the register fingerprint alone decides. Wrong device → `ConfigEntryError`
  / form error `wrong_device`; no answer → `ConfigEntryNotReady` / `cannot_connect`.
  The identity also feeds the device registry (`model_id`, `sw_version`).
* **Unwired analog inputs read a sentinel** (`0x8004`, window
  `PROBE_SENTINEL_LOW..HIGH`), not 0. `_decode_all` stores `None` for those
  INT16 words, so the entity is `unknown` instead of -3276.4 °C. The climate
  entity must then report no current temperature/humidity (never a stale value).
* **Scaling:** temperatures/setpoints ×0.1 (`FAKTOR`), fan/percent registers
  ×0.01, humidity ×1.

## Where to find what

Each topic has one home; other files link to it instead of repeating it. Put
new knowledge in the right file, and do not restate it elsewhere.

| Topic | Home |
|-------|------|
| **How the unit behaves** (variants, states and start/stop sequences, summer/winter, display/probe setups, fan, compressor, water circuit, alarm effects, display and Modbus actions, as-delivered vs handbook defaults) and **what was tested on real hardware** (evidence log `T1…`) | [`references/UNIT_BEHAVIOUR.md`](references/UNIT_BEHAVIOUR.md) |
| **Which registers exist**: addresses, names, encodings, ranges, value meanings, write recipes, installer parameter table (§16) | [`references/MODBUS_REGISTERS.md`](references/MODBUS_REGISTERS.md) |
| Technical data, fan-speed → airflow estimate, index of the source PDFs | [`references/README.md`](references/README.md) |
| What the integration does on top of the unit (architecture, guards, entity mapping) | this file |
| User-facing description of the integration | [`README.md`](README.md) |
| Open hardware questions and test plans | [`plans/todo.md`](plans/todo.md) |
| Tests | [`tests/CLAUDE.md`](tests/CLAUDE.md) |

Rules for the references:

* `UNIT_BEHAVIOUR.md` is only about the unit, never the integration, and tags
  every statement with its evidence: a handbook section `[HB 6.3]`, a Modbus
  manual page `[MB p.7]`, a forum post `[V#76]` / `[F#79]`, a hardware test
  `[T7]`, or `[INFERRED]`.
* When something is checked on real hardware, add a `T` row to its evidence
  log (date, what was seen, source), replace the `[INFERRED]` tags it settles,
  and tick the item in `plans/todo.md`.
* `MODBUS_REGISTERS.md` defines registers and does not describe behaviour.
  `tests/wiring_check.py` reads its table rows of the form
  ``| `0xHHHH` | dec | name |``; every `REG` in `const.py` must have one.
* Factory defaults: the handbook's and the reference unit's differ (PC08, PU13,
  PS01, PG03, PH07, …); `UNIT_BEHAVIOUR.md` §15 lists both. Say which one you
  mean.

Source documents (search the `.txt`, check tables in the PDF):

| File | Use for |
|------|---------|
| `references/HRDS+_Technisches_Handbuch_DE.txt` / `.pdf` | Technical handbook (87 pp): operating modes (§2.7), terminals (§4.4–4.5), parameter list with defaults (§5.3), control logic (§6), alarms (§7), technical data (§10). |
| `references/HRDS+_Modbus_RTU_RS485_DE.pdf` | Modbus manual: source of every register address; enables, season change via HB04, setpoint validity. |
| `references/HRDS+_Benutzerhandbuch_DE.pdf` | End-user handbook (12 pp); a subset of the technical handbook. |
| `references/Innova_DEH+_H_Installation_Manual_EN.txt` | OEM original; describes an **older controller** (microswitches, fixed speeds), so only the product line and hardware apply. |

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

## Setup, operation gate and device grouping

* **Setup happens in the integration**, after connect. `_compute_setup_issues`
  (hub) derives the `setup_check` sensor and its `issues` list from the polled
  read-back.
* **Operation gate:** `OPERATIONAL_KEYS` (on/off, dehumidify, active cooling,
  manual fan) refuse non-zero writes in `write_entity_value` until
  `hub.operation_allowed` is set via `switch.allow_operational_requests`
  (`HrdsOperationSwitch`, `OPERATION_TYPES`, default off, `RestoreEntity`;
  the restored state carries the entity's unique id and is ignored when it
  belongs to another entry, since a re-added entry reuses the entity id). The
  `_sync_required_settings_locked` writes bypass the gate (they call the client
  directly). Do not add a request-type write path that skips `write_entity_value`.
* **Device grouping:** `SETUP_KEYS` entities go on the `-setup` child device
  (`SETUP_DEVICE_SUFFIX`, linked to the main one with `via_device_id`); `CONFIG_KEYS` /
  `DIAGNOSTIC_KEYS` become entity categories (`entity_category_for`). A new
  entity belongs in exactly one of the three groups, or none (operational).
  `unique_id` always uses the config entry id, so moving a key between devices
  keeps its entity. All devices are registered in `async_setup_entry`.
  `wiring_check.py` guards the sets.
* **Renaming a key** changes its unique id: add it to `RENAMED_KEYS` in
  `__init__.py`, whose `_migrate_renamed_keys` moves the registry entry (and an
  entity id still carrying the old key) at setup, so history is kept. 1139 /
  PG02 were `active_cooling` / `active_cooling_available` up to 0.9.1.
* **Installer device:** opt-in (`installer_device` option, default off, only in
  the options flow, not at first install). Its registers are **never part of
  the regular poll** (`_poll_keys` excludes `INSTALLER_KEYS`, and a block never
  spans another group's address): they are read at setup (so turning the
  option on reads them, via the reload), on `button.refresh_installer`
  (`button.py`, `BUTTON_TYPES`), and one register is read back after a write.
  `sensor.installer_last_read` (timestamp) shows the last read. With the
  option off the device is removed with its entities, and only
  `INSTALLER_LOGIC_KEYS` (PC07/PC08/PU08 for the water check and the heating
  evidence, PF12/PH09/PH10 for the unit's own heating band) are read once at
  setup. The rest of the installer menu lives in
  `installer_params.py` (one row per parameter: code, register, kind
  n/s/r, scale, range, unit, en/de name, enabled-by-default). `const.py`
  appends the rows to `ENTITIES_DICT` as `inst_<code>` keys (`INSTALLER_KEYS`),
  on the `-installer` child device; writable ones are `CONFIG`, read-only
  `DIAGNOSTIC`. Addresses come from the Modbus manual's full parameter table
  (0x0640-0x077A). Scaling was verified against raw read-back: °C / bar / rps
  ×0.1, fan/compressor/damper % ×0.01, the rest ×1. Never add passwords,
  PH15 (restore defaults) or PH18 (clear history); keep link settings, I/O
  allocation, PE05 and test mode read-only; do not poll above 1900 (unverified,
  and one bad address forces a block onto the per-register fallback). Their
  translations are generated from the table (names in the row), and
  `MODBUS_REGISTERS.md` §16 lists them.

## Operating modes, season, water circuit

* Two requests only: **DEU** (`dehumidify`, 1140) and **INT** (`integration_request`,
  1139). INT is dehumidify + cool in summer and **heating** in winter (compressor
  off, warm water through the register). INT starts the compressor only
  because PU05 (1692, factory on) couples a dehumidify request to it. With
  water below PU08 (factory 10 °C) the unit runs any summer request on cold
  water alone, compressor off (handbook §6.3, the passive path; PU09/PU10 add
  the compressor later). `references/UNIT_BEHAVIOUR.md` §6–7 documents the
  modes; README "How the unit works" summarises them for users.
* `_check_request_allowed` runs on every `write_entity_value`: INT is refused
  unless the read-back season (`operating_mode`, 1583) is summer, unless the
  `allow_winter_heating` option is on; with `water_circuit = brine` winter INT
  is always refused and winter DEU is refused unless the brine guard passes
  (handbook 3.8.7: no heating, coil freezing), and a season change to winter
  is refused while a request it would turn unsafe is active. Keep request
  writes going through `write_entity_value`.
* **Brine temperature guard** (options `brine_temperature_entity`,
  `brine_min_temperature`, default 8 °C: above the unit's AL16 frost alarm,
  PA43 = 3 °C, and below PU08 so the passive cold-water path can run): an HA
  sensor, judged by
  `update_brine_guard()` on the event loop (before each poll, on its state
  events, and inside `_check_request_allowed`). When configured, any start
  (DEU/INT on, or unit on with one latched) needs value ≥ minimum and
  `last_reported` within `BRINE_GUARD_MAX_AGE_HOURS` (24), in every season.
  It only gates starts; it never stops a running request. The indicator is
  `binary_sensor.brine_temperature_guard` (`COMPUTED_BINARY_SENSORS`,
  problem class, hidden when no sensor is set, always available). Options
  override data for these keys as a whole, so clearing the entity sticks.
* **The unit heats on its own** (handbook 6.1.2): with a room temperature
  source (display or AI2 probe) and PG02 it raises its own winter INT below
  SEtH − PF12 (off above SEtH + PF12; SEtH clamped to PH09..PH10, factory 14 °C
  both, so it heats below 13.5 °C). The INT request is not readable.
  `allow_winter_heating` cannot stop it: it only governs Home Assistant's own
  winter INT requests (and accepts the unit's). The integration reports it
  instead: `binary_sensor.automatic_heating` (`C_AUTO_HEATING`,
  `COMPUTED_BINARY_SENSORS`; on while the unit, on in winter, can heat by
  itself; attributes give the band; hidden without a temperature source or
  PG02), setup issues `unit_heats_on_its_own` (option off) /
  `unit_heats_on_its_own_on_brine` (silenced when SEtH − PF12 <
  `AUTO_HEATING_NEGLIGIBLE_BELOW`), and `winter_heating_without_integration`
  (option on, PG02 = 0). The flows refuse the option together with brine
  (`winter_heating_on_brine`); an older entry with both still forces it off.
* Season without a display: `select.season` writes HB04 (1825): 4 = summer,
  3 = winter (Modbus manual). Anything else raises AL25.
* Water valve/pump (1126, relay K5) and condenser valve (1124, K4) are
  read-only diagnostics: the unit drives its water circuit; the integration
  never overrides it (no PT test-mode writes). `_compute_water_issues` feeds
  `sensor.water_check`.
* Headless setpoints: without a display, setpoints only act with a room probe
  (HA02 = 45 / HA03 = 53/54). `hub.update_hidden_keys()` (from the primed
  read-back) drops `TEMPERATURE_TARGET_KEYS` / `HUMIDITY_TARGET_KEYS` from
  entity creation and the climate entity's target features; changing HA02/HA03
  needs a reload.

## Device variants (30 vs 50, R vs non-R, DC)

The product code on the type plate encodes the variant: `HRDS+ 30 H R K DC`.

| Field | Values | Meaning |
|-------|--------|---------|
| `30`/`50` | size | Max airflow 300 / 500 m³/h. **No register** — set `model` in config. |
| `R` | optional | Has recirculation fan + motorised damper + air filter. **No dedicated register**: detect it from the damper output `outDO_RecircDamper` (1134): `disabled` = no damper (non-R), `off`/`on` = R. `PG01_MachineType` (1797) is **not** this flag — it is the fan arrangement (0 = supply fan only, 1 = supply + exhaust) and reads `0` on an R unit (verified on an HRDS+ 30 R). |
| `DC` | optional | Has active cooling. `PG02_EnableIntegration` (1798) = `1`. |

How the variants behave (non-R runs on MVHR flow alone; on an R unit every
request opens the damper and runs the fan, and PM20 = 0 does not prevent it;
the unofficial I/O workaround; AL11 as the airflow guard) is in
[`references/UNIT_BEHAVIOUR.md`](references/UNIT_BEHAVIOUR.md) §1 and §9.3.
The fan minimum during DEU/INT is the device's own PF28/PF27 (factory 50 %,
settable to 0); the 130 / 190 m³/h in the technical data are the tested spec
range, **not** a firmware floor.

## Hub (`HrdsModbusHub` in `__init__.py`)

* Polls all registers every N seconds (default 30) via
  `async_refresh_modbus_data()`, reading input and holding blocks separately.
  Blocks never span an address belonging to the other function code. A block
  the device *rejects* (Modbus exception) is retried register-by-register so
  one bad address cannot blank every entity; a block with *no* answer, or an
  answer of the wrong length, fails the cycle and drops the connection
  (`_read`): after a timeout pymodbus hands the late answer to the next
  request, which decoded one block's registers as another's.
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
* **Request switches show the command until confirmed.** The unit mirrors a
  request into its register late (a real unit read OFF back as ON for several
  polls). For `PENDING_KEYS` (on/off, dehumidify, integration) the hub keeps
  the commanded value in `hub.data` after the write (`_pending`), re-reads just
  that register at `PENDING_RECHECK_SECONDS` (`_async_verify_pending`, never a
  full cycle) and drops the entry as soon as the read-back agrees; after the last
  re-read the unit's value stands and a warning is logged. The BMS enables are
  deliberately not pending (the hub re-asserts them from the read-back), and
  neither are fan and climate, which stay actual-only (see below).
* Entity callbacks register via `hub.async_add_my_modbus_sensor(callback)`.

## Climate entity mapping

* `current_temperature` ← `room_temperature`; `current_humidity` ← `room_humidity`.
* `hvac_mode` ∈ {OFF, AUTO or FAN_ONLY (shown as "Standby"), DRY, COOL
  (summer), HEAT (winter; offered with `allow_winter_heating` or while a winter
  INT is on, never on brine)};
  COOL/HEAT only offered when PG02 is not `off`. The unit ORs its request sources (handbook 6.1: its own
  room-probe logic, the DEU/INT digital inputs, Modbus), so the mode says what
  can make it act. Derived in order: unit off → OFF; `hub.int_effect`
  (INT on and able to act: PG02, summer → cool; winter and not brine → heat,
  whatever `allow_winter_heating` says, since the unit does not know it) →
  COOL/HEAT; DEU (1140) on → DRY; `hub.auto_capable` → AUTO;
  `dehumidify_request` (1121) on from another source → DRY; else FAN_ONLY
  ("Standby": on, but nothing can make it act). OFF only ever means the unit
  is off, so it never contradicts `switch.unit_on_off`. An INT request that
  cannot act never decides the mode. FAN_ONLY is offered only while
  `auto_capable` is false (otherwise "on, nothing requested" is AUTO).
* Season for the climate logic and the request guards is `hub.active_season`:
  the prefix of `mode_status` (1110), falling back to `operating_mode` (1583,
  which reads `auto` under PC05). Unknown counts as not summer in the guards.
* `hvac_action` is what the unit does, not what was asked. HEATING only with
  `hub.is_heating`: `int_effect == "heat"` or the unit's own winter INT
  (`auto_heating_active`, room below SEtH + PF12, not brine), valve/pump (1126) on, no AL04,
  compressor off, water ≥ PC08 (in `INSTALLER_LOGIC_KEYS`, read at setup). The
  unit has no heat source: winter INT only opens valve and pump, so only warm
  water from a heating circuit heats (never on brine). COOLING only with
  `hub.is_cooling`: `int_effect == "cool"`, compressor on, no AL03. Else
  DRYING (compressor on or 1121 on), else FAN (R unit, fan status on), else
  IDLE. The condenser valve (1124, K4)
  is not evidence: the real unit reads it ON in standby, against the handbook.
* INT writes are refused when PG02 reads `off` (`_check_request_allowed`).
* `hub.auto_capable` (`_auto_sources`): a display or allocated probe
  (`show_*_target`) with a healthy reading. Humidity also needs summer or PU02 on;
  temperature also needs PG02 (in winter the unit heats by itself, whatever
  `allow_winter_heating` says). AUTO is
  only offered while it holds. Switching the unit on while it holds counts as a
  start for the brine guard, and on brine in winter it needs a passing guard
  (the unit would dehumidify by itself).
* Setting a mode writes the request registers first (so the guard refuses
  before the unit starts), then `unit_on_off`. AUTO and FAN_ONLY clear both
  requests and turn the unit on. OFF clears both requests and always turns
  the unit off: that alone stops the unit's own logic, digital-input requests
  and a manual fan. `turn_on` = AUTO if `auto_capable` else FAN_ONLY;
  `turn_off` = OFF.
* Auto mode is tested only against the derived `display_cnu2` overlay, never on
  a real display unit; the README banner says so.
* `target_humidity` ← `humidity_setpoint`; `target_temperature` ←
  `summer_setpoint` in summer, `winter_setpoint` in winter. Both features are
  removed when the hub hides the setpoints (headless, no probe).
* `min_humidity` / `max_humidity` follow the unit's own PH29/PH30 clamps;
  `min_temp` / `max_temp` are SEtC's 15..35 °C in summer and SEtH's PH09..PH10
  clamp (within 5..35 °C) in winter.
* `current_temperature` / `current_humidity` report `None` while the matching
  probe-fault alarm is active.

## Fan entity

Only the R variant has a fan. `hub.has_fan` (from the primed read-back: damper
output 1134 not `disabled`) decides; on a non-R unit `FAN_KEYS` (fan entity,
fan speed numbers, fan sensors, 1112) are hidden and the climate entity drops
`FAN_MODE`.

Read and write are deliberately separate, because on this device they are not
the same number.

* **Read (actual):** `fan.hrds_supply_fan.percentage`, the climate entity's
  `fan_mode`, and `sensor.supply_fan_output` all report `outAO_SupplyFan`
  (639) — what the fan is *doing*. `sensor.supply_fan_airflow` converts the
  same figure to m³/h.
* **Write (commanded):** `fan.set_percentage`, `climate.set_fan_mode` and
  `number.fan_manual_speed` all write `PM20_SupplyFan_Manual` (1614).

Neither the fan nor the climate entity updates optimistically on write: the
state means *actual*, and the unit may not adopt a setpoint verbatim. Write,
then let the poll report reality. The commanded value stays visible on
`number.fan_manual_speed` and the fan entity's `commanded_percent` attribute —
the divergence between the two is the diagnostic.

**Why it may diverge:** the manual describes the fan request as *scaled linearly
across the active mode's min/max band* (PF28/PF10 dehumidify, PF27/PF09
integration, PF07 VMC), so a request of 30 at the factory 50–85 % band could
produce ≈60 % output, and 0 would not stop the fan. Unconfirmed on hardware —
see `references/UNIT_BEHAVIOUR.md` §9.1 and `plans/todo.md`.

**The per-mode minimum is device state.** All three minima are writable
registers exposed as `number` entities. The integration must not carry its own
"fan is off below X %" config option — that would shadow the registers and
misreport airflow. `_compute_derived` therefore keys its zero on the device's
own `supply_fan_status`, not on a percentage threshold. (`airflow_max_m3h`
*is* legitimately a config option: max airflow is a model property with no
register.)

## Bring-up diagnostic

`tests/diagnose_hrds.py <host> [--port N] [--unit N]` is a **read-only** script
(FC03/FC04/FC43 only, it never writes) to run against a real unit before
installing the integration. It reuses `const.py` and the integration's block
plan, reports device identification, connected probes, settings to review, and
exactly what the integration writes on first connect. Needs only
`pip install 'pymodbus>=3.13.1'`. Keep its `build_blocks` in sync with
`_build_blocks` in `__init__.py`.

The port is configurable in the integration too (`port` in the config flow and
options flow, default 502), as are the unit id (`hostid`) and model.

## Tests

Everything about the tests, including the rule for which of the two layers a
test belongs in, is in [`tests/CLAUDE.md`](tests/CLAUDE.md). Run
`python3 tests/wiring_check.py` for any entity change (see above).

## Linting

```
ruff check .
ruff format .
```

## CI

GitHub Actions (in `.github/workflows/`):
* `lint.yaml` — Ruff lint + format check (Python), wiring check.
* `hassfest.yaml` — Home Assistant manifest/translation validation.
* `hacs.yaml` — HACS repository validation (also daily); ignores `brands` (the
  images ship locally in `brand/`, see below, rather than in the HACS brands repo).
* `tests.yaml` — in-process tests + coverage (see **Tests**).
* `e2e.yaml` — the integration in a real HA container against simulators,
  only for what an in-process HA cannot show (see `tests/CLAUDE.md`); nightly
  also against the `beta` image (allowed to fail).
* **Triggers** (so nothing runs twice): lint, hassfest, hacs, tests and e2e run
  on `pull_request` and on `push` to `main` only (plus `workflow_dispatch`;
  hacs daily, e2e nightly incl. `beta`). A plain `push:` is never used, since a
  branch with an open PR would run every workflow for both events. tests and e2e
  also run from `release.yaml` (`workflow_call`) on the tagged commit before the
  zip is built. tests/e2e cancel a superseded PR run (`concurrency`).
* **Branch protection is a GitHub setting, not a file**; the intended
  settings are in [`.github/REPO_SETTINGS.md`](.github/REPO_SETTINGS.md).
  Never add a "Restrict updates" rule on the default branch (it forces a
  bypass on every merge) and never add an app to a bypass list.
* **Only the owner merges or releases; apps only branch.** Never run
  `gh pr merge` or publish a release: open the PR and leave the merge to the
  owner.
* Every workflow sets `permissions: contents: read` at the top; only
  `release.yaml`'s `package` job raises it to `contents: write`. Actions are
  pinned to commit SHAs (Dependabot bumps them), except that the hassfest pin
  tracks `master` (no release tags), so re-pin it by hand.
* `lint.yaml` also runs `tests/wiring_check.py`. Dependabot bumps the HA
  image, `requirements_test.txt`, `requirements_lint.txt` (Ruff) and
  `tests/e2e/requirements.txt`; keep the image and
  `pytest-homeassistant-custom-component` on the same HA release.
* `release.yaml` — on a published release: hassfest, hacs, the two test
  workflows above, then a `package` job (only if all pass) that stamps the tag into `manifest.json` (`.github/scripts/update_hacs_manifest.py`),
  zips `custom_components/innova_hrds` and attaches `innova_hrds.zip` to the
  release. `hacs.json` has `zip_release` + `filename` so HACS installs that asset.

Releasing: publish a GitHub release whose tag is `vX.Y.Z`. The release must carry
`innova_hrds.zip` or HACS cannot install it, so if the `package` job fails, fix it
and re-run rather than leaving the release without the asset.

The tag must be `vX.Y.Z` (the stamp script rejects `v0.9`). Publish a normal
release, not a GitHub pre-release: HACS hides pre-releases by default. Before a
release, set `manifest.json`'s version, add a `CHANGELOG.md` entry (its text is the
release body) and check the README status banner and "Road to 1.0" section; drop
the beta wording at 1.0.

### Brand images

`custom_components/innova_hrds/brand/` holds `icon.png` (256²), `icon@2x.png`
(512²), `logo.png` / `logo@2x.png` (shortest side 256 / 512) and `dark_*`
variants. Home Assistant 2026.3+ prefers them over the brands CDN. They are the
Innova mark/wordmark recoloured (`#00643e`, white for dark); never use Home
Assistant branded images in a custom integration. `wiring_check.py` verifies the
sizes.

`tests/wiring_check.py` runs without Home Assistant installed: it stubs the HA
API, imports `const.py`, and asserts that every entity is classified, every
declared platform has a module, every entity has `en`/`de` translations, every
register is documented in `references/MODBUS_REGISTERS.md`, and no input block
spans a holding address. It is not a substitute for real tests, but it catches
the failures this integration has actually had.
