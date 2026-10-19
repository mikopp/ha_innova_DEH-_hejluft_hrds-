**ATTENTION** This is not done yet, use at your own risk

# Innova DEH+ / hej.luft HRDS+ — Home Assistant integration

Home Assistant custom integration for the **Innova DEH+** air dehumidification
module (sold in Austria by https://www.hejluft.at/ as the **HRDS+**) over **Modbus TCP**.

## Build status

[![Lint](https://github.com/mikopp/ha_innova_deh-_hejluft_hrds-/actions/workflows/lint.yaml/badge.svg)](https://github.com/mikopp/ha_innova_deh-_hejluft_hrds-/actions/workflows/lint.yaml)
[![hassfest](https://github.com/mikopp/ha_innova_deh-_hejluft_hrds-/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/mikopp/ha_innova_deh-_hejluft_hrds-/actions/workflows/hassfest.yaml)
[![HACS](https://github.com/mikopp/ha_innova_deh-_hejluft_hrds-/actions/workflows/hacs.yaml/badge.svg)](https://github.com/mikopp/ha_innova_deh-_hejluft_hrds-/actions/workflows/hacs.yaml)

> **Status: early / initial.** The register map is taken directly from the
> manufacturer's Modbus manual (see [`references/`](references/)) but has **not
> yet been verified against physical hardware**. Treat addresses and scaling as
> "documented, untested". Feedback from real units is very welcome.

## What it does

The integration talks to the unit's control board via Modbus TCP and exposes:

* A **climate entity** showing room temperature & humidity, with the current
  HVAC action (off / idle / drying / cooling) and an HVAC mode you can set to
  pick the operating mode:
  * **Off** — turns the unit off
  * **Dry** — dehumidification (fan runs, compressor condenses moisture)
  * **Cool** — active cooling (the unit's "integration" function, summer only)
  * Target humidity and target temperature are settable.
  * Fan mode is selectable: **off** / **low** / **medium** / **high** — writes
    the manual fan speed register. The shown mode is what the fan is *actually*
    doing. **"off" does not make Dry/Cool run on passive airflow**: on an `R`
    unit every dehumidify or cooling request opens the recirculation damper and
    starts the fan (see [Fan mode and recirculation](#fan-mode-and-recirculation)).
* **Sensors** — see entity table below, including four computed airflow
  sensors derived from your model's calibration data.
* **Binary sensors** — dehumidify requested, recirculation active, probe
  health, overall alarm active, four individual alarm sensors (compressor
  low/high pressure, antifreeze, dirty filter), and a variant-detection sensor
  (active cooling available).
* **Switches** — unit on/off, dehumidify, active cooling, plus the three
  "enable control via Modbus" registers.
* **Numbers** — humidity setpoint, summer/winter temperature setpoints, and the
  per-mode fan speed bands.
* **Select** — T/H probe source (HA00), winter dehumidification mode (PU02).
* **Fan** — the supply/recirculation fan as a settable percentage.

See [`references/README.md`](references/README.md) for the full capability list
and [`references/MODBUS_REGISTERS.md`](references/MODBUS_REGISTERS.md) for the
register-level detail.

## Entity reference

Entities marked **¹** are only meaningful when a room temperature probe is
present (CNU2 display or external NTC). Entities marked **²** require a room
humidity probe. Entities marked **³** are built into the unit's control board
and are always available. See [probe requirements](#probe-requirements) below
and [`references/README.md` — Probes](references/README.md#probes-built-in-display-and-external-sensors)
for full detail.

### Climate

| Entity | What it shows / does |
|--------|---------------------|
| `climate.hrds_climate` | HVAC mode (Off/Dry/Cool), action, fan mode, target T & RH. `current_temperature`¹ and `current_humidity`² are suppressed when the corresponding probe is absent. Target-humidity bounds follow the unit's own PH29/PH30 clamps. |

### Sensors

| Entity | Unit | Probe needed | Notes |
|--------|------|-------------|-------|
| `sensor.room_temperature` | °C | ¹ Display or external NTC | Read from reg 499; used for automatic cooling trigger |
| `sensor.room_humidity` | %RH | ² Display or external humidity sensor | Read from reg 505; used for automatic dehumidify trigger |
| `sensor.outdoor_temperature` | °C | External NTC (IP65) | Reg 500; only drives Free-Cooling/Heating (PG03). Display-only otherwise. |
| `sensor.water_temperature` | °C | ³ Built-in | Reg 501; over-temperature protection |
| `sensor.supply_temperature` | °C | External NTC | Reg 503; monitoring only |
| `sensor.air_quality` | ppm | External IAQ sensor | Reg 506; monitoring only |
| `sensor.actual_setpoint` | °C | — | Reg 1111; active room setpoint in use |
| `sensor.supply_fan_output` | % | ³ Built-in | Reg 639 (×0.01 %); actual fan analog output |
| `sensor.compressor_output` | % | ³ Built-in | Reg 641 (×0.01 %); compressor modulation level |
| `sensor.supply_fan_rpm` | rpm | ³ Built-in | Reg 1117 |
| `sensor.exhaust_temperature` | °C | External NTC | Reg 502; monitoring only |
| `sensor.evaporator_temperature` | °C | ³ Built-in | Reg 511; drives compressor modulation, works on a headless unit |
| `sensor.fan_manual_request` | % | ³ Built-in | Reg 1114; the **display's** manual request, not ours — diagnostic |
| `sensor.recirculation_damper` | enum | ³ Built-in | Reg 1134; Open confirms room air is being recirculated across the coil |
| `sensor.unit_status` | enum | ³ Built-in | OFF by display/DI/BMS/scheduler/clock, or ON |
| `sensor.mode_status` | enum | ³ Built-in | Summer/Winter × manual/auto/DI |
| `sensor.supply_fan_status` | enum | ³ Built-in | Off/Starting/On/Stopping/Alarm |
| `sensor.compressor_status` | enum | ³ Built-in | Off/Wait/On/Alarm/Manual |
| `sensor.operating_mode` | enum | ³ Built-in | Summer/Winter/Auto season |
| `sensor.recirculation_damper` | enum | ³ Built-in | Reg 1134; Off/On/Disabled — state of the motorised recirculation damper (R-variant only) |
| `sensor.supply_fan_airflow` | m³/h | ³ Built-in | Computed from live fan output %; see [Airflow sensors](#airflow-sensors) |
| `sensor.supply_fan_max_airflow` | m³/h | — | Computed constant; maximum fan airflow (from config) |
| `sensor.max_total_airflow` | m³/h | — | Computed constant; same as supply_fan_max_airflow (from config) |

### Binary sensors

#### Status

| Entity | Probe needed | What ON means |
|--------|-------------|--------------|
| `binary_sensor.dehumidify_request` | ³ | Dehumidification currently requested |
| `binary_sensor.recirculation_active` | ³ | Unit's supply fan is running (reg 1112) |
| `binary_sensor.alarm_active` | ³ | At least one alarm is active |
| `binary_sensor.temp_probe_ok` | ³ | Room temperature probe healthy (AL28 not active) |
| `binary_sensor.humidity_probe_ok` | ³ | Room humidity probe healthy (AL34 not active) |

#### Variant detection

These reflect configuration written by the installer (or the factory) to
holding registers. They are read-only from the integration.

| Entity | What it means |
|--------|--------------|
| `sensor.machine_type` | PG01 fan arrangement: *supply fan only* or *supply and exhaust fan*. **Not** a recirculation flag: an `R` unit reads *supply fan only*. |
| `binary_sensor.active_cooling_available` | ON: active cooling is enabled on this unit (PG02 = 1) |

Whether the unit has a recirculation fan (`R`) is shown by
`sensor.recirculation_damper`: *Disabled* means no damper is wired (non-`R`),
*Off*/*On* means it is an `R` unit.

#### Individual alarms

Each sensor maps to a single bit of a packed alarm register. **ON = alarm is active.**

| Entity | Alarm | Register bit | Effect |
|--------|-------|-------------|--------|
| `binary_sensor.alarm_compressor_lowpressure` | AL11 | Reg 768 bit 10 | Compressor stopped (low pressure / frost thermostat) |
| `binary_sensor.alarm_compressor_highpressure` | AL12 | Reg 768 bit 11 | Compressor stopped (high pressure switch) |
| `binary_sensor.alarm_water_antifreeze` | AL16 | Reg 768 bit 15 | Fan stopped (antifreeze protection) |
| `binary_sensor.alarm_dirty_filter` | AL22 | Reg 769 bit 5 | Maintenance reminder; display only, manual reset |

### Switches

| Entity | Register | Notes |
|--------|----------|-------|
| `switch.unit_on_off` | 1105 | BMS on/off request (requires PH02 = 1) |
| `switch.dehumidify` | 1140 | BMS dehumidify request (requires PH28 = 1) |
| `switch.active_cooling` | 1139 | BMS active-cooling request (requires PH27 = 1, summer season) |
| `switch.allow_operational_requests` | — | **Setup device.** Not a register: the integration's own gate. Off by default; while off, on/dehumidify/cooling/non-zero fan requests are refused. Restored across restarts |
| `switch.enable_time_programs` | 1779 | **Setup device.** PH03 — time programs can switch the unit off |
| `switch.enable_onoff_display` | 1777 | PH01 — on/off by wired display. Forced **off** while `has_display` is off (the default); turning it on by hand is undone on the next poll |
| `switch.enable_onoff_bms` | 1778 | PH02 — auto-set on startup; expose to inspect/reset |
| `switch.enable_dehumidify_bms` | 1870 | PH28 — auto-set on startup |
| `switch.enable_cooling_bms` | 1869 | PH27 — auto-set on startup |
| `switch.force_dehumidify_in_cooling` | 1692 | PU05; couple dehumidify to a cooling request |
| `switch.enable_integration` | 1798 | PG02; master enable for active cooling |
| `switch.enable_free_cooling` | 1799 | PG03; while off, outdoor temperature drives nothing |

### Numbers

| Entity | Register | Range | Notes |
|--------|----------|-------|-------|
| `number.humidity_setpoint` | 1586 | 0–100 %RH | PU01; target humidity for dehumidify |
| `number.summer_setpoint` | 1584 | 15–35 °C | SEtC; target room temp for active cooling |
| `number.winter_setpoint` | 1585 | 15–35 °C | SEtH; target room temp for heating |
| `number.fan_min_speed_dehumidify` | 1853 | 0–100 % | PF28; lower fan bound in dehumidify mode |
| `number.fan_max_speed_dehumidify` | 1647 | 0–100 % | PF10; upper fan bound in dehumidify mode |
| `number.fan_min_speed_cooling` | 1852 | 0–100 % | PF27; lower fan bound in active cooling |
| `number.fan_min_speed_vmc` | 1644 | 0–100 % | PF07; lower fan bound in VMC (ventilation-only) mode |
| `number.fan_max_speed_cooling` | 1646 | 0–100 % | PF09; upper fan bound in active cooling |
| `number.fan_manual_speed` | 1614 | 0–100 % | PM20; the fan **setpoint** — what was asked for. The fan entity and climate fan mode write here too. See the note below on the min/max band. |
| `number.dehumidify_differential` | 1694 | 0–100 %RH | PU07; the unit's own dehumidify hysteresis |
| `number.min_room_temp_dehumidify` | 1889 | 0–30 °C | PU13; **below this the unit refuses to dehumidify, including over Modbus** |
| `number.min_room_temp_diff_dehumidify` | 1890 | 0.1–20 °C | PU14; re-enable differential above PU13 |
| `number.fan_min_runtime` | 1638 | 0–999 s | PF01; device-side minimum fan runtime |
| `number.fan_post_run_time` | 1640 | 0–999 s | PF03; post-ventilation run-on |
| `number.humidity_setpoint_min` | 1892 | 0–100 %RH | PH29; lower clamp on target humidity |
| `number.humidity_setpoint_max` | 1893 | 0–100 %RH | PH30; upper clamp on target humidity |

### Select

| Entity | Register | Options | Notes |
|--------|----------|---------|-------|
| `select.probe_source` | 1803 | None/external, CNU2 T, CNU2 T+H, CNU T, CNU T+H, EPJ T, EPJ T+H | HA00 — which sensor feeds room T/H readings. **Set to "None / external probes" when running without a display.** |
| `select.winter_dehumidify` | 1689 | Disabled, With water, Without water | PU02; dehumidification during the heating season |

### Setup entities (read-only facts about the installation)

These live on the **HRDS+ setup** device and show how the unit is configured,
so you can see it without opening the display. See the
[first-use checklist](#first-use-checklist).

| Entity | Register | Shows |
|--------|----------|-------|
| `sensor.setup_check` | — | `ok` / `attention`; attribute `issues` lists the open items |
| `sensor.machine_type` | 1797 | PG01 — supply fan only, or supply and exhaust fan (not "has recirculation") |
| `sensor.remote_onoff_input` | 1824 | HB03 — unused / normally closed / normally open |
| `binary_sensor.remote_contact_closed` | 257 bit 0 | State of the remote on/off contact (meaning inferred, unverified) |
| `sensor.season_input` / `sensor.season_owner` | 1825 / 1878 | HB04 season contact type; PC11 who owns season change |
| `sensor.temperature_unit` | 1781 | PH05 — Celsius or Fahrenheit |
| `number.ai2_allocation` / `number.ai3_allocation` | 1805 / 1806 | HA02 / HA03 — what the analog inputs are allocated to (0 = unused, 45 = room temperature, 53/54 = room humidity). **Writable** - set to 0 when no such probe is wired |
| `sensor.fan_output_allocation` | 1832 | HC04 — raw allocation of the supply fan output |
| `sensor.damper_relay_allocation` | 1838 | HD01 — raw allocation of relay DO1 (10 = recirculation damper NO, 9 = NC) |
| `sensor.damper_prestart_time` | 1698 | PS01 — damper pre-start time, seconds |

### Fan

| Entity | What it does |
|--------|-------------|
| `fan.hrds_supply_fan` | The unit's supply/recirculation fan as a percentage. Reports the **actual** output (reg 639) — what the fan is doing — while `fan.set_percentage` writes the setpoint PM20 (1614). The commanded value, RPM and fan status are state attributes. Because the unit's own fan recirculates room air *in addition* to whatever the central MVHR pushes through the duct, this is the lever for topping combined airflow up to a target. |

## Installation

### HACS (custom repository)

1. In HACS, add this repository as a custom repository (category: *Integration*):
   `https://github.com/mikopp/ha_innova_deh-_hejluft_hrds-`
2. Install **Innova HRDS+ / hej.luft Dehumidifier** and restart Home Assistant.

### Manual

Copy `custom_components/innova_hrds/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Add the integration from **Settings → Devices & Services → Add Integration →
Innova HRDS+**, then provide:

| Field | Default | Notes |
|-------|---------|-------|
| Name  | `HRDS+` | Display name / device name |
| Host  | —       | IP / hostname of the Modbus-TCP gateway |
| Port  | `502`   | Modbus TCP port |
| Modbus slave ID | `1` | Factory default unit address |
| Scan interval | `30 s` | Polling period (min 5 s) |
| Model | `30`    | Device size: `30` = HRDS+30 (max 300 m³/h), `50` = HRDS+50 (max 500 m³/h). Sets airflow defaults. |
| A wired CNU2 display is connected | off | Leave **off** for a unit driven only from Home Assistant. See below. |

Before anything is written, the integration checks that the address really is an
HRDS+: the controller must identify itself as EVCO `EPB9…` over Modbus (FC 43)
and its status registers must make sense. Anything else is refused with
*"not an HRDS+"*, so a wrong IP or slave ID cannot have settings written into it.

On connection the integration sets the registers the unit needs in order to obey
Modbus: the "by BMS" enables **PH02/PH27/PH28**, and, unless a display is
connected, **PH01 = 0** (no on/off from a display; with PH01 = 1 and no display
the unit stays *Off (display)* and ignores Modbus) and **HA00 = 0** (no display
sensors). It re-checks them every poll, so a power cycle that resets them heals
itself, and a manual change to one of them is undone on the next poll. If you
*do* have a display, tick the option and the integration leaves PH01/HA00 alone.

## Device layout and first-use checklist

All setup happens through the integration, after it has connected. Nothing needs
to be changed on the unit beforehand. The device page is split by purpose:

| Where | What is there | When you touch it |
|-------|---------------|-------------------|
| **`HRDS+ setup`** device (linked to the main device) | Everything that decides whether the unit can run at all: the **Setup check** sensor, the **Allow operational requests** switch, the Modbus/display enables (PH01, PH02, PH27, PH28), probe allocation (HA00, HA02, HA03) and probe-OK flags, remote on/off input (HB03) and its contact state, season input (HB04, PC11), time programs (PH03), temperature unit (PH05), machine type (PG01), free-cooling/integration enables, and the fan/damper output wiring (HC04, HD01, PS01). | Once, after installing, and again if the wiring changes |
| **`HRDS+`** device, *Configuration* section | Post-setup tuning: setpoints, per-mode fan min/max, dehumidify differential, minimum room temperature (PU13/PU14), fan run times, humidity clamps | Occasionally |
| **`HRDS+`** device, main section | Climate, fan, the request switches (on/off, dehumidify, active cooling), live readings, status and alarms | Day to day |
| **`HRDS+`** device, *Diagnostic* section | Calibration and the fan request echo | When troubleshooting |

Entity ids follow the device name, so setup entities are prefixed with the setup
device name (for example `sensor.hrds_setup_setup_check`); the tables below omit
the prefix.

### Operational requests are off until you allow them

A fresh install starts with **`switch.allow_operational_requests`** (on the setup
device) **off**. While it is off, the integration refuses any request that makes the unit
act - turning it on, dehumidify, active cooling, or a non-zero fan speed - with
an error saying so. Turning things off, and every configuration write, always
works. Your choice is remembered across restarts. Turn it on once the checklist
below is clean.

### First-use checklist

1. Open the **HRDS+ setup** device. The **Setup check** sensor reads `ok` or
   `attention`; its `issues` attribute lists what to look at:

   | Issue | Meaning and what to do |
   |-------|------------------------|
   | `modbus_enables_pending` | PH02/PH27/PH28 are not set on the unit yet. The integration writes them on the next poll; if this persists, the unit rejects the write (check the log). |
   | `headless_settings_pending` | Without a display, PH01 and HA00 must be 0. Same: written on the next poll. |
   | `unit_off_by_digital_input` | The remote on/off contact (OFF/OFF terminals, HB03) is open, so the unit is forced off. Close it (the factory bridge) or set HB03 accordingly. |
   | `unit_off_by_scheduler` / `unit_off_by_clock` | A time program or the internal clock holds the unit off. Check PH03 (**Time programs enabled**); switch it off for Modbus-only control. |
   | `unit_off_by_display` | Only reported when the display option is ticked: the display has switched the unit off. |
   | `room_temperature_probe_missing` | AI2 is allocated to a probe (HA02 non-zero) but nothing is wired. The unit will wait for a room temperature. Set `number.ai2_allocation` (HA02) to 0 or wire the probe. |
   | `room_humidity_probe_missing` | Same for AI3 (`number.ai3_allocation`, HA03) and the humidity probe. |
   | `time_programs_enabled` | PH03 is on; the unit may switch itself off on schedule. |
   | `free_cooling_without_outdoor_probe` | **Free cooling** is on but no outdoor probe delivers a value. Turn off `switch.enable_free_cooling` unless an outdoor probe is fitted. |
   | `temperature_unit_fahrenheit` | PH05 is set to °F; the integration assumes °C. |

2. Read the remaining setup entities and confirm they match your installation:
   *Machine type* (supply only, or supply and exhaust fan), *Recirculation
   damper relay allocation* (a value other than `disabled`/unused on an `R`
   model), *AI2/AI3 allocation* and the *probe OK* flags (which probes the unit
   believes are connected), *Remote on/off input* and *contact closed*.
3. Check **Minimum room temperature (PU13)** in the Configuration section. The
   unit refuses to dehumidify below it, and what it does with no room
   temperature probe is not yet verified on hardware - see
   [`plans/todo.md`](plans/todo.md).
4. When the setup check is `ok`, turn on **Allow operational requests**.

### Airflow calibration (Options)

After the integration is set up, open **Settings → Devices & Services →
Innova HRDS+ → Configure** to adjust the airflow calibration used by the four
computed `m³/h` sensors:

| Field | Default (30/50) | Notes |
|-------|-----------------|-------|
| Model | `30` | Change here too if you need to switch model |
| Supply fan max airflow (m³/h) | `300` / `500` | Fan airflow at 100 % output — adjust if your duct or filter raises back-pressure |

These values feed the live `sensor.supply_fan_airflow` calculation (proportional:
`output% / 100 × Q_max`). The two static sensors (`supply_fan_max_airflow`,
`max_total_airflow`) are updated immediately when you save Options.

## Using the integration

### Setting target humidity and target temperature

Both targets are exposed on the **climate entity** (and as standalone `number`
entities):

* **Target humidity** (`target_humidity`, register `PU01` 1586, %RH) is the
  level the unit dehumidifies towards. It is only acted on while the unit is
  **on and dehumidifying** — i.e. the climate entity is in **Dry** or **Cool**
  mode (both request dehumidification). In **Off** the setpoint is stored but
  does nothing. The value is clamped by the unit's own min/max humidity
  parameters (PH29/PH30).
* **Target temperature** (`target_temperature`, the **summer** setpoint
  register 1584, °C) is the room temperature the unit aims for. It is used in
  **summer season** when active cooling (the "integration" function) is engaged,
  i.e. the climate entity is in **Cool** mode. The separate winter setpoint
  (register 1585) is exposed as its own `number` for the heating season.

So in short: set **target humidity** in **Dry** or **Cool**; **target
temperature** matters in **Cool** (summer). Both require a wired display or
external probes to be present, otherwise the unit ignores them.

### Fan mode and recirculation

The HRDS+ sits on the supply branch of your central MVHR ("inflow pipe"). The
word *integration* is used by the manufacturer for two different things, so it's
worth being precise:

* **Passive airflow** — the unit's own fan is off, but your central MVHR still
  pushes air through the duct. On an **`R` unit this only happens while the
  unit is idle** (Off / On-standby, no dehumidify or cooling request). There is
  no dedicated sensor: watch **Supply fan status = Off** while **Unit status =
  On**. The unit cannot measure the upstream MVHR's flow.
* **Fan integration** — the unit runs **its own fan** to blend central inflow
  air with room air across its coil. **On an `R` unit every Dry or Cool request
  does this:** the controller opens the recirculation damper, starts the fan
  after the damper is open, then starts the compressor. **Recirculation active**
  tells you the fan is running; **Supply fan output %** and **Supply fan speed
  (RPM)** show the actual speed.

**Dehumidifying on passive airflow alone is not possible on an `R` unit with
stock settings.** Fan mode "off" (a write of 0 to `PM20`) neither stops the fan
during Dry/Cool nor keeps the damper closed, and the unit may floor the fan at
its dehumidify minimum. Only a **non-`R`** unit (no damper, no fan) dehumidifies
on passive flow. For an `R` unit, an unofficial I/O reassignment exists; it is
untested here and carries a short-circuit risk if the recirculation inlet is
teed into the extract duct. See
[`references/MODBUS_REGISTERS.md` §13.5](references/MODBUS_REGISTERS.md).
Use the per-mode fan minimum/maximum `number` entities to choose how hard the fan
runs while it does.

### Drying with the fan on, but active cooling off

A common state is **drying + fan running + active cooling off**: the unit
removes moisture and its fan blends/moves air, but it is *not* actively cooling.

This is exactly the climate entity's **Dry** mode:

1. Set the climate entity to **Dry** (this turns the unit on, requests
   dehumidify, and leaves active cooling off).
2. The compressor runs to condense moisture, so the **fan runs** — you'll see
   **Supply fan status = On**, **Recirculation active = on**, and **Compressor
   status = On**.
3. **Active cooling (Modbus)** stays **off** — the compressor is working for
   dehumidification, not cooling.

If you prefer the individual switches over the climate entity, the same state is
**Unit on/off = On**, **Dehumidify = On**, **Active cooling = Off**. Going to
**Cool** mode instead adds the active-cooling request on top (summer only).
Technical details and register addresses are in
[`references/MODBUS_REGISTERS.md` §13](references/MODBUS_REGISTERS.md#13-airflow-passive-flow-fan-integration-and-active-cooling).

### Airflow sensors

The integration provides four computed sensors that estimate the unit's
recirculation airflow **automatically** from the live fan output reading and your
calibration settings (see [Airflow calibration](#airflow-calibration-options)
above):

| Sensor | What it shows |
|--------|--------------|
| `sensor.supply_fan_airflow` | Live estimate in m³/h; updates every poll cycle |
| `sensor.supply_fan_max_airflow` | Configured maximum airflow in m³/h (from Options) |
| `sensor.max_total_airflow` | Same as max airflow (provided for convenience) |

The formula is proportional: `Q = (output% / 100) × Q_max`, using the live
`supply_fan_output` register. The fan counts as stopped (0 m³/h) when the
unit's own `supply_fan_status` says so, not at a percentage of ours. Default
Q_max per model:

| Variant | Q_max |
|---------|------:|
| HRDS+ 30 | 300 m³/h |
| HRDS+ 50 | 500 m³/h |

Note: PF28 and PF27 (the per-mode fan minimums, exposed as `number` entities)
are configurable from 0 to 100 %, so the 130/190 m³/h figures from the
performance table are the tested operating range, not a firmware floor.

This is an open-loop estimate — it assumes constant duct resistance, so loaded
filters or restrictive ducts will make the real flow lower than estimated. If
you can measure actual flow, adjust `airflow_max_m3h` in Options to calibrate.
The full derivation and a two-point calibration recipe are in
[`references/README.md` — Translating fan speed to airflow](references/README.md#translating-fan-speed--rpm-to-airflow-mh),
with the underlying spec data in
[Technical data](references/README.md#technical-data-airflow-capacity-power).

### Commanded vs actual fan speed

The device does not necessarily run the fan at the percentage you ask for. The
technical handbook says the manual request is **scaled linearly between the
active mode's minimum and maximum** (PF28/PF10 for dehumidify, PF27/PF09 for
cooling, PF07 for VMC), so at the factory 50–85 % band a request of 30 % could
produce roughly 60 % output, and a request of 0 % would not stop the fan.

The integration therefore keeps the two apart:

* **Actual** — `sensor.hrds_supply_fan_output` (%),
  `sensor.hrds_supply_fan_airflow` (m³/h), `sensor.hrds_supply_fan_rpm`, and the
  state of `fan.hrds_supply_fan` and the climate entity's `fan_mode`.
* **Commanded** — `number.hrds_manual_fan_speed`, and the fan entity's
  `commanded_percent` attribute.

If you want a commanded percentage to mean an absolute percentage, set the
active mode's minimum to `0` and its maximum to `100` — both are writable
numbers. Whether PM20 really follows the band is **not yet confirmed on
hardware**; see [`plans/todo.md`](plans/todo.md).

## Probe requirements

The unit's control board exposes temperature and humidity readings, but most
probes must be **installed by the installer** — they do not come built-in.

| What you need | Hardware | Notes |
|--------------|----------|-------|
| Room temperature | NTC 10 kΩ B3435 (wall or duct mount) **or** CNU2 display | Needed for auto cooling/heating and dehumidify gating |
| Room humidity | 0–10 V or 4–20 mA humidity transmitter **or** CNU2 display | Needed for auto dehumidify |
| Outdoor temperature | NTC 10 kΩ B3435, IP65-rated | Only needed for Free-Cooling/Heating (PG03); otherwise optional |
| Exhaust / supply air temperature | NTC 10 kΩ B3435 | Optional; display/monitoring only |

**If you have no display and no external probes** (the default, with *A wired
CNU2 display is connected* left off), the integration sets HA00 = 0 and PH01 = 0
for you. The unit then responds only to explicit Modbus commands — dehumidify,
cooling and fan control work normally; only the _automatic_ setpoint-based
triggers are inactive. Probe inputs that are not wired report no value: room
temperature, room humidity, outdoor, exhaust, supply air temperature and air
quality show **unknown**, and the climate entity shows no current temperature or
humidity. That is expected, not an error. The factory-wired water and evaporator
temperatures keep working. (The `temp_probe_ok` / `humidity_probe_ok` sensors
follow alarms AL28/AL34, which a headless unit did not necessarily raise, so
judge by the sensors above rather than by those two.)

See [`references/README.md` — Probes](references/README.md#probes-built-in-display-and-external-sensors)
and [`references/MODBUS_REGISTERS.md` §14](references/MODBUS_REGISTERS.md#14-probes-built-in-display-and-external-sensors)
for full probe specifications, wiring, and the HA00/PH01 configuration detail.

## Requirements

* **Home Assistant 2026.9 or newer.**
* `pymodbus` 3.13.1 (pinned in the manifest to match what HA 2026.9 ships).

### Availability

Entities go **`unavailable`** when a poll fails, rather than continuing to show
the last good reading. If you drive this integration from templates or
automations, gate them on `has_value()` — a dehumidifier that acts on a
three-day-old humidity reading is worse than one that does nothing.

Writes that the unit rejects now raise an error instead of silently succeeding.
In an automation a failed service call **aborts the remaining steps**, so if you
issue several writes in sequence, either put the critical one first or mark the
rest `continue_on_error: true`.

## Prerequisites

* An Innova DEH+ / hej.luft HRDS+ with the Modbus RTU/RS-485 control board and a
  Modbus-RTU-to-TCP gateway reachable on your network.
* Room temperature/humidity readings require the wired CNU2 display or external
  probes (see [Probe requirements](#probe-requirements) above).

## Disclaimer

Use at your own risk. Many of the writable registers change installer-level
behaviour. Only change settings you understand.

## Credits

Architecture closely follows the
[`ha_comfoconnectpro`](https://github.com/hstrohmaier/ha_comfoconnectpro)
integration. Documentation © Innova / hej.luft (see `references/`).
