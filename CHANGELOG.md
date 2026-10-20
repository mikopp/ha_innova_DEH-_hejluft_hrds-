# Changelog

All notable changes to this project are documented here, newest first.

---

## Unreleased

**Changed:** the *AI2 allocation (HA02)* and *AI3 allocation (HA03)* numbers on
the setup device are now dropdowns named *T/H probe temperature input* and
*T/H probe humidity input*, with the options *Unused*, *Room temperature probe
(NTC 10 kΩ)*, and *Room humidity probe (4–20 mA / 0–10 V)* instead of raw codes.
They sort next to *T/H probe source (HA00)*. The old number entities are removed
on update; automations that set `number.*ai2_allocation` / `*ai3_allocation`
must use the new selects. A code other than the documented ones shows as
unknown, and the setup check reports `probe_input_unrecognised`.

**Changed:** the device has two requests, DEU and INT, and the setup switches
now say so. `enable_cooling_bms` (PH27, 1869) is the permission for the INT
request, not a cooling mode, and is now `switch.enable_integration_bms`
("Enable integration (INT) via Modbus (PH27)"); PH28 is labelled DEU. Existing
installs keep the entity and its entity id; only the name changes.

**Added:** the setup switches for free cooling (PG03), the display on/off
(PH01) and the three Modbus enables carry a `hint` attribute (English or
German, following the Home Assistant language) that says when to leave them on
or turn them off. Home Assistant has no tooltip for entities; the attribute
shows in the entity's *Attributes*. The README setup step lists the same advice.

**Added:** the *Setup check* sensor reads *Needs attention (see attributes)* and
has a new `to_fix` attribute: each open setup item in plain words with what to
do about it (English or German). `issues` keeps the short codes.

**Removed:** `switch.enable_integration` (PG02, 1798). PG02 is an installer
setting that says whether the unit has the integration function, already shown
read-only as `binary_sensor.active_cooling_available` (now "Unit has
integration function (PG02)"). The switch is removed from the entity registry
on the next start.

---

## 0.9.1 (2026-10-20): fix setup on real hardware, installer device opt-in

**Fixed:** 0.9.0 did not load on a real unit. The installer device added about
240 registers to the poll, so the integration read them in 120-register
blocks, which the unit / RS-485 gateway did not answer (`No valid reply to
Modbus block read (holding @ 1602+120)`). Reads are now at most 10 registers.
If a block still goes unanswered while a single register answers, the
integration halves the block size by itself instead of failing.

**Changed:** the installer device is now **opt-in** (*Installer device* in the
integration options, off by default and for new installs). Its parameters are
no longer part of the regular poll: they are read when the option is turned
on, at each start, and with the new *Refresh installer parameters* button. A
new *Installer parameters last read* sensor shows when. Turning the option off
removes the device and its entities. If you used installer entities with
0.9.0, turn the option on after updating; renamed or enabled installer
entities have to be set up again.

---

## 0.9.0 (2026-10-20): first public release (beta)

First release. The integration is usable, but it is a beta and not 1.0 yet.

**What is in:** climate and fan entities, sensors, binary sensors, switches,
numbers and selects for the whole documented register map, computed airflow
sensors, a `setup` device with a setup check and an operation gate
(*Allow operational requests*, off by default), an `installer` device with the
installer menu, headless operation (the required PH01/HA00/PH02/PH27/PH28
settings are written and re-checked every poll), device identity check before
anything is written, season and winter-heating guards, water-circuit
diagnostics, and an optional brine temperature guard. Tested in CI against a
simulated unit and in a real Home Assistant container.

**Tested on:** one HRDS+ 30 with recirculation (`R`), headless (no CNU2 display,
no external probes).

**Not yet tested outside CI / on real hardware:** HRDS+ 50, non-`R` units,
units with a display or external probes, brine circuits, winter heating, free
cooling, and the manual fan speed to actual fan output mapping. See
`plans/todo.md`.

**Support:** please attach the output of `tests/diagnose_hrds.py --json` to
every issue (see the README, *Reporting issues*).

---

## 2026-10-20 (3)

### fix: a register that stops answering goes unavailable

* When the device stopped answering for one address (its block fell back to
  per-register reads) the entity kept showing its last value forever. The
  reading is now dropped, so the entity is `unavailable` until the address
  answers again.

### fix: a re-added entry does not inherit an open operation gate

* Home Assistant restores state by entity id, and a re-added entry gets the
  same entity id as the one it replaces, so *Allow operational requests* could
  come back **on** for a brand-new entry. The gate now stores its unique id
  (which contains the config entry id) and only restores a state it owns.
* A state stored by an earlier version has no owner, so the gate is closed
  once after this update; switch it on again.

---

## 2026-10-20 (2)

### fix: setup and installer devices use `via_device_id`

* `via_device` is deprecated and stops working in Home Assistant 2027.8; HA
  2026.10 already logged a warning at every setup. The main device is now
  registered first and the setup and installer devices link to it with
  `via_device_id` (also in the `DeviceInfo` of their entities).

### test: each layer only tests what it alone can show

* `tests/e2e` (real Home Assistant) is down from 40 to 15 tests and from about
  6 to 2.5 minutes. About 34 repeated a scenario that `tests/ha` already covers
  in-process; those are gone. What stays needs a real container, and every
  test says why (`@pytest.mark.needs_real_ha("<reason>")`, enforced at
  collection): the integration installed and loaded by HA itself, flows and
  services as HTTP/JSON, the real scheduler, restarts, and the real log.
* **Restart tests.** In-process (`tests/ha/test_restart.py`): a running unit is
  left alone (only the required settings are written), season and fan setpoint
  are untouched, a unit that lost its settings gets them back, booting before
  the unit is reachable ends loaded by itself, the gate is restored, options
  stay authoritative, user registry edits are kept, every entity comes back
  identical. Real restarts (`tests/e2e/test_restart.py`, four container
  restarts): the same contract from disk, including options, a renamed entity,
  an enabled installer entity and the restored gate.
* **Deprecation guards.** In-process: a test fails when HA logs a deprecation
  naming this integration (this is what found `via_device`). Real HA: the whole
  session's container log must be free of errors, tracebacks and deprecations
  from the integration.
* The test rules are documented in `tests/CLAUDE.md` (with short
  `tests/ha/CLAUDE.md` and `tests/e2e/CLAUDE.md`); the main `CLAUDE.md` only
  points there. A bare `pytest` no longer collects `tests/e2e`.
* Removed the leftover `tests/out.json` (the dump lives in `tests/devices/`).

## 2026-10-20

### fix: entities show the primed read-back right after setup

* Setup reads the unit once before creating entities, but the entities did
  not use that read: every entity was `unknown` until the first scheduled poll
  (30 s by default). They now publish the cached values when added. Found by
  the new simulator tests.
* The *Allow operational requests* switch restores its last state before
  publishing, so it no longer flickers off on startup.

### fix: a slow gateway could show wrong values

* After a read timed out, pymodbus handed the late answer to the next
  request, so every following block decoded another block's registers (a
  running unit could show `off_by_display`). Replies must now have exactly the
  requested length; a missing or mismatched reply drops the connection and
  the entities go `unavailable` instead. A dead link now fails in seconds
  instead of retrying every register one by one.
* A write just before unload no longer leaves its refresh timer running.

### test: simulator, in-process and Docker e2e tests in CI

* `tests/sim`: a simulated HRDS+ seeded from real-device dumps
  (`tests/devices/`), serving Modbus TCP with the documented behaviour (BMS
  enables, display/OFF priority, season/AL25, setpoint clamps, request
  sequence, three fan-output hypotheses, alarms, probe faults, power cycle)
  and transport faults (offline, slow, rejected addresses/writes, identity).
* `tests/ha` (workflow `tests.yaml`): the real Home Assistant core with the
  integration's real client against the simulator; coverage gate 90 %.
* `tests/e2e` (workflow `e2e.yaml`): the integration in the official Home
  Assistant container, driven over REST/websocket; headless and display
  units, both operation modes, fan speeds, failures. Nightly also on `beta`.
* `tests/out.json` moved to `tests/devices/hrds_30+_headless_factory_state.json`.
### fix: hassfest requirement, brand images, release packaging

- **Minimum Home Assistant is now 2026.10** (`hacs.json`, README, CLAUDE.md).
  HA 2026.10 still ships `pymodbus` 3.13.1, so the requirement below is unchanged.
- **hassfest was failing** on `pymodbus==3.13.1`: it rejects an exact pin on a
  package Home Assistant itself depends on. The manifest now requires
  `pymodbus>=3.13.1`, which still resolves to the version HA ships.
- **Brand images** now ship in `custom_components/innova_hrds/brand/`
  (`icon`, `logo`, and `dark_` variants, each with an `@2x`), which Home
  Assistant 2026.3+ serves for custom integrations. The artwork is the Innova
  mark and wordmark taken from the vector logo on
  [innova.it](https://www.innova.it/en/products/vmc/active-integration/hrd/),
  recoloured to Innova green (`#00643e`) and white for dark mode. The Innova
  name and logo are their trademarks; they identify the hardware this
  integration talks to and imply no endorsement.
- **Releases are packaged by CI.** Publishing a release now also stamps the tag
  into `manifest.json` with `.github/scripts/update_hacs_manifest.py`, zips the
  integration and attaches `innova_hrds.zip`. `hacs.json` sets `zip_release` /
  `filename` so HACS installs that asset. The script now strips a leading `v`,
  refuses non-version input and keeps the manifest's key order.
- `release.yaml` runs the HACS check with `ignore: brands` like `hacs.yaml`.
- `tests/wiring_check.py` also checks the brand image sizes and that no manifest
  requirement is an exact pin.
- Removed `strings.json`: it was an exact copy of `translations/en.json`, and a
  custom integration only needs the `translations/` files (hassfest reads those).

## 2026-10-19

### feat: brine temperature guard

* New options *Brine temperature guard sensor* (any HA temperature sensor,
  e.g. the heat pump's brine reading) and *Brine guard minimum temperature*
  (default 10 °C). When set, a dehumidify / integration request (or unit on
  with one latched) only starts while the sensor reads at least the minimum
  and has reported within 24 h, in every season. Unavailable, non-numeric or
  non-temperature readings block too.
* On brine, a passing guard permits winter dehumidifying; without a guard it
  stays refused. Winter heating on brine stays refused. The PU02 setup issue
  is only raised without a guard.
* `binary_sensor.brine_temperature_guard` (problem class) is on while the
  guard blocks, with source, temperature, minimum, last report and reason as
  attributes; the water check gains `brine_guard_blocking`.

### feat: installer device, season control, winter-heating and brine guards

From the technical handbook (§2.7, §3.8, §5.1, §5.3, §6) and the Modbus
manual's full parameter table.

* **Installer device.** About 240 installer-menu parameters (PF, PE, Pb, PU,
  PS, Pr, PA, PC, PH, PG, HA-HD, PM, PT) on a linked `<name> installer` device
  (`installer_params.py`). Writable ones under Configuration, link settings /
  I/O allocation / safety bypass / test mode read-only under Diagnostic, unused
  ones disabled by default. Passwords, PH15 and PH18 are not exposed.
* **Season select** (HB04: 4 = summer, 3 = winter), replacing the read-only
  `sensor.season_input`.
* **Integration request renamed** and guarded: it heats in winter, so it is
  refused unless the unit is in summer or the new option *Allow winter
  heating* is on. Climate offers Cool only in summer and Heat only in winter
  with the option. New option *Water register connected to* (heating/cooling
  circuit or brine): on brine, winter heating and winter dehumidify are always
  refused and PU02 is flagged in the setup check.
* **Water diagnostics:** valve/pump output (1126), condenser valve (1124),
  AL03/AL04 alarms and a *Water circuit check* sensor. Read-only by design.
* **Headless setpoints hidden:** without a display or room probe the unit
  ignores PU01/SEtC/SEtH/PU07, so they are not created and the climate entity
  offers no targets.
* **PC12 is at 1894** (1879 is PE24), new setup switch. Winter setpoint range
  lowered to 5 °C (factory PH10 cap is 14 °C).

### feat: setup through the integration, operation gate, grouped device page

* **Setup check** sensor (`ok` / `attention`, `issues` attribute) computed from
  the polled read-back: pending Modbus/headless enables, remote contact open,
  scheduler/clock holds, probes allocated but not wired, time programs, free
  cooling without an outdoor probe, Fahrenheit.
* **Allow operational requests** switch (default off, restored on restart). While
  off, `write_entity_value` refuses non-zero writes to unit on/off, dehumidify,
  active cooling and the manual fan speed. OFF and configuration writes pass; the
  hub's own enable/headless writes bypass the gate.
* New read-only entities for how the unit is configured (HB03, HB04, PC11, PH05,
  HC04, HD01, PS01, remote contact) plus writable HA02/HA03 and PH03.
* **Device page:** a linked `<name> setup` device holds the setup items; post-setup
  parameters are `EntityCategory.CONFIG` and read-only extras `DIAGNOSTIC` on the
  main device, which keeps the operational surface. Unique ids are unchanged.
* README gains the device layout and a first-use checklist.

### fix: run without a display, verify the device, stop misreading PG01 and unwired probes

Driven by the first bring-up against a real HRDS+ 30 R (`tests/diagnose_hrds.py`).

**Device identity is checked** (`identity.py`). Setup and the config/options
flow now require FC 43/14 vendor `EVCO` with a product code starting `EPB9`
(the unit reports `EVCO` / `EPB9ORSINDEU` / `V01.00.09.02`) **and** the four
status registers holding documented enum values. A wrong device is refused
before any register is written (`wrong_device` / `ConfigEntryError`); an
unreachable one gives `cannot_connect` / `ConfigEntryNotReady`. Without FC 43
the register fingerprint decides alone. The product code and firmware revision
now appear in the device registry.

**Headless operation.** New option `has_display` (default **off**). While off,
the hub asserts **PH01 = 0** (display on/off) and **HA00 = 0** (T/H source
none) on every poll, next to PH02/PH27/PH28. Before this the unit reported
`off_by_display` forever, because PH01 = 1 with no display, and a Modbus ON
cannot override it. New `switch.enable_onoff_display` exposes PH01. Set
`has_display` if you do have a CNU2: the integration then leaves both alone.
`_sync_bms_enables_locked` became `_sync_required_settings_locked`.

**Unwired probes no longer read -3276.4 °C.** An unconnected analog input
returns `0x8004` (and `0x7FFA` next to it), not 0. INT16 words in
`0x7FF0..0x800F` now decode to "no value" and the entity is `unknown`. The
climate entity also stops holding the previous temperature/humidity when the
value disappears.

**PG01 was misread.** The handbook defines it as the fan arrangement (0 =
supply fan only, 1 = supply + exhaust fan), not "has a recirculation fan". An
`R` unit reads 0, so `binary_sensor.has_recirculation` wrongly said "no
recirculation". It is replaced by `sensor.machine_type`; detect `R` from the
recirculation damper output (1134, `disabled` = no damper). Docs corrected.

**Diagnostic script** now flags the sentinel instead of printing -3276.4,
reports the identity verdict, lists the PH01/HA00 writes, and takes `--display`.

---

## 2026-09-10 (2)

### refactor: fan entities report actual speed; drop the shadowed fan minimum

**`fan.hrds_supply_fan` and the climate entity's `fan_mode` now report the
ACTUAL fan output** (`outAO_SupplyFan`, reg 639) rather than the commanded
setpoint. Writing still goes to `PM20_SupplyFan_Manual` (1614) via
`fan.set_percentage`, `climate.set_fan_mode` or `number.fan_manual_speed`, so
read and write are cleanly separated: sensors and entity state tell you what the
fan is doing, the number tells you what was asked of it.

Neither entity updates optimistically on write any more — the state means
*actual*, which the unit decides. The commanded value is visible on
`number.fan_manual_speed` and the fan entity's `commanded_percent` attribute.

**Removed the `fan_min_output_pct` config option.** It duplicated device state:
the fan minimum is per-mode and register-backed (PF28 dehumidify 1853, PF27
integration 1852, PF07 VMC 1644), all writable and all exposed as `number`
entities. The integration should mirror the device, not shadow it. The m³/h
estimate now treats the fan as stopped when the device's own
`supply_fan_status` says so, instead of when output falls below a percentage of
our choosing — which previously reported 0 m³/h while the fan was really running
below 50 %.

`airflow_max_m3h` stays a config option: maximum airflow is a model property
with no register.

**New `number.fan_min_speed_vmc`** — PF07 (reg 1644), the third per-mode
minimum, completing the set.

**Documented in `references/MODBUS_REGISTERS.md` §6.1:** the technical handbook
states the manual fan request is *scaled linearly between the active mode's min
and max*, so it is a position within the band rather than an absolute
percentage. If that applies to PM20, a request of 30 at the factory 50–85 %
band yields ≈60.5 % output and a request of 0 does not stop the fan. This is
recorded as the key open hardware question in `plans/todo.md`, with a sweep that
distinguishes rescaling from clamping — it decides whether an external airflow
controller can command percent directly or must open the band first.

---

## 2026-09-10

### feat: Home Assistant 2026.9 baseline, select + fan platforms, availability

**Minimum Home Assistant is now 2026.9**; `pymodbus` is pinned to `3.13.1`, the
version HA 2026.9 ships (the code already relied on the `device_id=` kwarg,
which needs >= 3.9). `manifest.json` gains `integration_type` and `loggers`.

**Two behaviour changes worth knowing before upgrading:**

- **Entities now go `unavailable`** when a poll fails, instead of reporting the
  last good reading indefinitely. Templates and automations driving this
  integration should gate on `has_value()`.
- **Writes the unit rejects now raise** instead of appearing to succeed. In an
  automation a failed service call aborts the remaining steps, so if you issue
  several writes in sequence, put the critical one first or mark the rest
  `continue_on_error: true`.

**Fixed — the select platform was missing entirely.** `SELECT_TYPES` was built
and translations existed, but there was no `select.py` and no `Platform.SELECT`,
so `select.probe_source` was never created and the documented headless-setup
workflow could not be performed.

**New `fan.hrds_supply_fan`** — the supply/recirculation fan as a percentage
(`fan.set_percentage`, turn on/off), with actual output %, RPM and fan status as
attributes. (Superseded the same day — see the entry above: both it and the
climate `fan_mode` now report the *actual* output rather than the commanded
setpoint.)

**New registers:** exhaust (502) and evaporator (511) temperatures, display
manual fan request (1114), `PU07` dehumidify differential (1694), `PU13`/`PU14`
minimum-room-temperature interlock (1889/1890), `PF01`/`PF03` fan min-runtime
and post-run (1638/1640), `PH29`/`PH30` humidity clamps (1892/1893), `PU05`
(1692), `PG02` (1798), `PG03` (1799) and `PU02` winter dehumidification (1689).
`PU13` is the notable one: it disables dehumidification below a room
temperature, and that interlock applies to Modbus requests too, so on a unit
with no room probe it can silently block a dehumidify command.

**Other fixes:**

- Climate `turn_on`/`turn_off` were rejected outright — HA 2026.9 removed the
  backwards-compatibility shim and the feature flags were never declared.
- The "by BMS" enables were written once per hub lifetime and marked as enabled
  even when the device rejected them, so a power-cycle that cleared them left
  every later write silently doing nothing until a restart. They are now
  re-asserted each poll from the read-back.
- Block reads could span a holding register and read it with FC 04, and one bad
  address failed the whole cycle. Blocks no longer cross function codes, and a
  failed block falls back to per-register reads.
- Percentage sensors were reported as `device_class: humidity`; air quality
  paired `ppm` with `AQI`, which HA only permits with no unit.
- A write triggered an immediate full poll, so the read of the pre-write value
  clobbered optimistic entity state. Now debounced.
- Number descriptions used the fields HA type-overrides to `None`; the options
  flow used the removed `config_entry` assignment; entities were push-only but
  did not set `should_poll = False`; `close()` took a lock on the event loop.
- Target-humidity bounds follow the unit's own PH29/PH30 clamps.
- `hass.data` replaced by `entry.runtime_data`, so two entries sharing a name no
  longer clobber each other's hub.
- `strings.json` carried only `config`/`options` while `translations/en.json`
  had the whole `entity` block; regenerating would have dropped every entity
  name and enum state.

**New `tests/wiring_check.py`** — consistency checks that run without Home
Assistant installed: every entity classified, every declared platform has a
module, translations complete, every register documented, no input block
spanning a holding address, and composite entities resolving availability
correctly.

---

## 2026-06-28 (2)

### feat: alarm sensors and min-airflow doc corrections

**New alarm binary sensors** (ON = alarm active) via bitmask extraction from
`PackedAlarm_1` (reg 768) and `PackedAlarm_2` (reg 769):

- `binary_sensor.alarm_compressor_lowpressure` — AL11, reg 768 bit 10;
  compressor low-pressure / frost-thermostat. Auto-stops compressor. This is
  the effective protection against insufficient airflow (evaporator icing →
  pressure drop → alarm).
- `binary_sensor.alarm_compressor_highpressure` — AL12, reg 768 bit 11;
  compressor high-pressure switch. Auto-stops compressor.
- `binary_sensor.alarm_water_antifreeze` — AL16, reg 768 bit 15;
  water-circuit antifreeze. Stops fan.
- `binary_sensor.alarm_dirty_filter` — AL22, reg 769 bit 5; filter service
  required. Display-only; manual reset (write 0 to reg 1604).

**Documentation corrections** (`references/README.md`):
- The 130 m³/h (30) / 190 m³/h (50) figures are the **tested spec range**, not
  a firmware-enforced floor. Removed incorrect "fan never runs below 130 m³/h"
  claim.
- Fan minimum speed during DEU/INT is configurable: `PF28` / `PF27` default
  50 % but allow 0 %. The firmware floor is configurable, not fixed.
- Fan-off (passive MVHR flow) confirmed valid from multiple sources: non-R
  variant has no fan and always runs this way; Innova manual Alarm 9 ("does
  not activate fan, keeps other loads unchanged"); PF28 min = 0 % in firmware.
- Remaining open question: does firmware clamp a manual 0 % setpoint up to
  PF28 floor during active DEU on the R variant? Verify by writing 0 to reg
  1614 and reading `outAO_SupplyFan` (639).

**`CLAUDE.md`:** added reference-folder guide, bitmask pattern documentation
(including alarm bit-position table), computed-sensor pattern, and device
variant / fan-minimum notes for future sessions.

**New reference files:** `references/HRDS+_Technisches_Handbuch_DE.txt` and
`references/Innova_DEH+_H_Installation_Manual_EN.txt` (searchable text
extracted from the manufacturer PDFs).

---

## 2026-06-28

### feat: model parameter, airflow sensors, and variant detection

Required `model` field (30/50) in integration setup drives calibration defaults
for the supply-fan airflow range. Calibration is refinable via the options flow.

**New computed sensors (m³/h, not register-backed):**
- `sensor.max_total_airflow` — nominal total from model spec
- `sensor.supply_fan_min_airflow` / `supply_fan_max_airflow` — calibrated band
- `sensor.supply_fan_airflow` — live estimate from `supply_fan_output %` using the
  affinity-law formula; `0 %` → `0 m³/h`, running range clamped to `[min, max]`

**New hardware-variant read-only binary sensors:**
- `binary_sensor.has_recirculation` — `PG01_MachineType` (1797); `on` = unit has
  recirculation fan (`R` variant), `off` = dehumidifier-only
- `binary_sensor.active_cooling_available` — `PG02_EnableIntegration` (1798);
  reflects installer configuration, not hard-wired hardware identity

**New enum sensor:**
- `sensor.recirculation_damper` — `outDO_RecircDamper` (1134); motorised flap
  in the room-air return duct: `off` = closed (MVHR passive flow only),
  `on` = open (room air drawn in and blended), `disabled` = no damper wired
  (non-`R` variant without recirculation assembly)

**BMS enable fix:** `enable_cooling_bms` (PH27, reg 1869) was missing from
`BMS_ENABLE_KEYS`; added so active-cooling writes are actually unlocked.

**Documentation:** passive-airflow proof added (non-`R` variant confirms the
compressor works on MVHR flow alone by design); damper physical role documented
in `references/README.md` and `MODBUS_REGISTERS.md`; `plans/todo.md` updated to
reflect resolved items and narrow the open firmware-clamping question to the
`R` variant only.

---

## 2026-06-25

### feat: probe-source select, probe-OK sensors, and headless-mode docs

- `select.probe_source` — `HA00` (reg 1803) controls which sensor supplies room
  T/H: CNU2 display, older display variants, or `none/external` for fully
  sensorless BMS-controlled operation.
- `binary_sensor.temp_probe_ok` — AL28 decoded from `PackedAlarm_2` (769 bit 11)
- `binary_sensor.humidity_probe_ok` — AL34 decoded from `PackedAlarm_3` (770 bit 1)
- Climate entity suppresses `current_temperature`/`current_humidity` (reports
  `None`) when the respective probe-fault alarm is active.
- `BITMASK` / `BITMASK_INVERT` fields added to `ENTITIES_DICT` for single-bit
  extraction from packed alarm registers.
- `references/MODBUS_REGISTERS.md` §14: probe types, specs, alarm bits, and a
  step-by-step headless (no display, no probes) setup guide.

### feat: climate fan mode (off / low / medium / high)

Writes to `PM20_SupplyFan_Manual` (reg 1614, ×0.01):

| Mode   | Output % |
|--------|----------|
| off    | 0 %      |
| low    | 30 %     |
| medium | 55 %     |
| high   | 85 %     |

Read-back maps `outAO_SupplyFan` (639) to the nearest preset via midpoint
thresholds (42.5 % / 70.0 %). `SupplyFan_Status` (1119) = OFF overrides to `off`
regardless of the output value.

Fan mode `off` while HVAC mode is Dry or Cool relies on the central MVHR's
passive inflow — verified as architecturally correct (see 2026-06-28 entry).

### feat: fan-integration sensor and airflow mode documentation

- `binary_sensor.recirculation_active` — `FanIntegration_Request` (reg 1112);
  `on` when the unit's own fan is running and blending room air with MVHR inflow.
- Documents the three distinct airflow states (passive, fan integration, active
  cooling) and why "integration" is overloaded in the manufacturer's terminology.

### ci: harden CI and configure Dependabot

- Pin all GitHub Actions to exact commit SHAs; Dependabot configured to open
  bump PRs for `github-actions` ecosystem.
- `hassfest` reverted to `@master` per HA team recommendation.
- HACS `validate.yaml` removed (was broken and redundant with `hacs.yaml`);
  `ignore: brands` added until integration is published to `home-assistant/brands`.
- `hacs.json` minimum HA version bumped to `2026.1.0`.
- `actions/checkout` bumped 4.3.1 → 7.0.0; `actions/setup-python` bumped
  5.6.0 → 6.3.0 (Dependabot).

### Initial Innova DEH+ / hej.luft HRDS+ Modbus integration

- Composite **climate** entity: room temperature & humidity, derived HVAC action,
  HVAC mode (off / dry / cool) driving on/off + dehumidify + active-cooling
  registers; target humidity and temperature.
- Sensors, enum status sensors, binary sensors, switches, and numbers generated
  from a single `ENTITIES_DICT` register table classified at import time.
- `HrdsModbusHub`: chunked block reads for the wide/sparse address space;
  automatic enabling of the mandatory "by BMS" control registers on connect.
- EN/DE translations; config and options flow.
- Manufacturer PDFs and distilled register reference under `references/`.
- CI: Ruff lint/format, hassfest, HACS validation.

> Register addresses and scaling come from the manufacturer documentation
> and have not yet been verified against physical hardware. See `plans/todo.md`.
