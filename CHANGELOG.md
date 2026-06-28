# Changelog

All notable changes to this project are documented here, newest first.

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
