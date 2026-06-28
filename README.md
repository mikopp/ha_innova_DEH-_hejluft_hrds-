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
  * Fan mode is selectable: **off** (passive airflow from central MVHR only) /
    **low** / **medium** / **high** — controls the unit's own supply fan via
    the manual fan speed register. Fan mode persists across HVAC mode changes.
* **Sensors** — see entity table below.
* **Binary sensors** — dehumidify requested, fan integration active, probe
  health, alarm active.
* **Switches** — unit on/off, dehumidify, active cooling, plus the three
  "enable control via Modbus" registers.
* **Numbers** — humidity setpoint, summer/winter temperature setpoints, and the
  per-mode fan speed bands.
* **Select** — T/H probe source (HA00).

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
| `climate.hrds_climate` | HVAC mode (Off/Dry/Cool), action, fan mode, target T & RH. `current_temperature`¹ and `current_humidity`² are suppressed when the corresponding probe is absent. |

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
| `sensor.unit_status` | enum | ³ Built-in | OFF by display/DI/BMS/scheduler/clock, or ON |
| `sensor.mode_status` | enum | ³ Built-in | Summer/Winter × manual/auto/DI |
| `sensor.supply_fan_status` | enum | ³ Built-in | Off/Starting/On/Stopping/Alarm |
| `sensor.compressor_status` | enum | ³ Built-in | Off/Wait/On/Alarm/Manual |
| `sensor.operating_mode` | enum | ³ Built-in | Summer/Winter/Auto season |

### Binary sensors

| Entity | Probe needed | What ON means |
|--------|-------------|--------------|
| `binary_sensor.dehumidify_request` | ³ | Dehumidification currently requested |
| `binary_sensor.fan_integration_active` | ³ | Unit's supply fan is running (blending/integration) |
| `binary_sensor.alarm_active` | ³ | At least one alarm is active |
| `binary_sensor.temp_probe_ok` | ³ | Room temperature probe healthy (AL28 not active) |
| `binary_sensor.humidity_probe_ok` | ³ | Room humidity probe healthy (AL34 not active) |

### Switches

| Entity | Register | Notes |
|--------|----------|-------|
| `switch.unit_on_off` | 1105 | BMS on/off request (requires PH02 = 1) |
| `switch.dehumidify` | 1140 | BMS dehumidify request (requires PH28 = 1) |
| `switch.active_cooling` | 1139 | BMS active-cooling request (requires PH27 = 1, summer season) |
| `switch.enable_onoff_bms` | 1778 | PH02 — auto-set on startup; expose to inspect/reset |
| `switch.enable_dehumidify_bms` | 1870 | PH28 — auto-set on startup |
| `switch.enable_integration_bms` | 1869 | PH27 — auto-set on startup |

### Numbers

| Entity | Register | Range | Notes |
|--------|----------|-------|-------|
| `number.humidity_setpoint` | 1586 | 0–100 %RH | PU01; target humidity for dehumidify |
| `number.summer_setpoint` | 1584 | 15–35 °C | SEtC; target room temp for active cooling |
| `number.winter_setpoint` | 1585 | 15–35 °C | SEtH; target room temp for heating |
| `number.fan_min_speed_dehumidify` | 1853 | 0–100 % | PF28; lower fan bound in dehumidify mode |
| `number.fan_max_speed_dehumidify` | 1647 | 0–100 % | PF10; upper fan bound in dehumidify mode |
| `number.fan_min_speed_cooling` | 1852 | 0–100 % | PF27; lower fan bound in active cooling |
| `number.fan_max_speed_cooling` | 1646 | 0–100 % | PF09; upper fan bound in active cooling |
| `number.fan_manual_speed` | 1614 | 0–100 % | PM20; manual fan speed (climate fan mode writes here) |

### Select

| Entity | Register | Options | Notes |
|--------|----------|---------|-------|
| `select.probe_source` | 1803 | None/external, CNU2 T, CNU2 T+H, CNU T, CNU T+H, EPJ T, EPJ T+H | HA00 — which sensor feeds room T/H readings. **Set to "None / external probes" when running without a display.** |

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

On first connection the integration enables Modbus control on the unit
(PH02/PH27/PH28) so on/off, dehumidify and cooling commands are honoured. These
are also exposed as switches if you prefer to manage them yourself.

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

### Passive airflow vs. fan mode

The HRDS+ sits on the supply branch of your central MVHR ("inflow pipe"), and
the word *integration* is used by the manufacturer for two different things, so
it's worth being precise:

* **Passive airflow** — the unit's **own fan is off**, but your central MVHR is
  still pushing air through the duct, so air keeps flowing. Set the **climate
  fan mode to "off"** to stop the unit's own fan; the central MVHR continues
  to push air through passively. There is no dedicated sensor for this state —
  watch **Supply fan status = Off** while **Unit status = On** (and **Fan
  integration active = off**). The unit cannot measure the upstream MVHR's
  flow, so rely on your central system for the actual rate.
* **Fan integration** — the unit runs **its own fan** to blend (integrate) the
  central inflow air with room air across its coil. Set the climate fan mode to
  **low / medium / high** to drive the fan at a fixed speed. The **Fan
  integration active** binary sensor tells you when the fan is running; **Supply
  fan output %** and **Supply fan speed (RPM)** show the actual speed. Fine-grained
  modulation bands (per mode) are available via the standalone `number` entities.

**Fan mode is independent of HVAC mode.** You can set fan mode to "off" while
the HVAC mode is Dry or Cool — the unit will still dehumidify or cool using
the passive airflow from the inflow pipe, without running its own fan. This is
the expected use case when the central MVHR provides sufficient airflow.

> **Note (unverified):** the "fan off during Dry/Cool" behaviour is based on
> the unit's ducted architecture and user confirmation, but has not yet been
> tested on real hardware. See `plans/todo.md`.

### Drying with the fan on, but active cooling off

A common state is **drying + fan running + active cooling off**: the unit
removes moisture and its fan blends/moves air, but it is *not* actively cooling.

This is exactly the climate entity's **Dry** mode:

1. Set the climate entity to **Dry** (this turns the unit on, requests
   dehumidify, and leaves active cooling off).
2. The compressor runs to condense moisture, so the **fan runs** — you'll see
   **Supply fan status = On**, **Fan integration active = on**, and **Compressor
   status = On**.
3. **Active cooling (Modbus)** stays **off** — the compressor is working for
   dehumidification, not cooling.

If you prefer the individual switches over the climate entity, the same state is
**Unit on/off = On**, **Dehumidify = On**, **Active cooling = Off**. Going to
**Cool** mode instead adds the active-cooling request on top (summer only).
Technical details and register addresses are in
[`references/MODBUS_REGISTERS.md` §13](references/MODBUS_REGISTERS.md#13-airflow-passive-flow-fan-integration-and-active-cooling).

### Estimating recirculation airflow (m³/h) from fan output / RPM

The unit reports fan **output %** (`sensor.supply_fan_output`) and **RPM**
(`sensor.supply_fan_rpm`) but **never airflow in m³/h** — it cannot measure its
own flow. You can estimate it.

First identify your variant from the type-plate code `HRDS+ ` **`30`**/**`50`**:

| Variant | Nominal total | Recirc fan range | Recirc fan power |
|---------|--------------:|-----------------:|-----------------:|
| **HRDS+ 30** | 300 m³/h | 130–300 m³/h | 120 W |
| **HRDS+ 50** | 500 m³/h | 190–500 m³/h | 170 W |

For a centrifugal EC fan on a fixed duct, **flow scales with speed** (`Q ∝ RPM`),
so:

```
recirc m³/h  ≈  (RPM / RPM_at_100%) × Q_max          # via RPM
recirc m³/h  ≈  (supply_fan_output% / 100) × Q_max    # via output %
```

where `Q_max` = 300 (HRDS+30) / 500 (HRDS+50). `RPM_at_100%` is not on the
datasheet — read `sensor.supply_fan_rpm` once with `number.fan_manual_speed` at
100 % to calibrate it. Note the recirc fan, when running, never delivers below
its minimum (130 / 190 m³/h); below that it is simply **off** (0 m³/h).

This is an open-loop estimate — it assumes constant duct resistance, so loaded
filters or restrictive ducts will make the real flow lower than estimated. The
full derivation, the band-aware formula, and a two-point calibration recipe are
in
[`references/README.md` — Translating fan speed to airflow](references/README.md#translating-fan-speed--rpm-to-airflow-mh),
with the underlying spec data in
[Technical data](references/README.md#technical-data-airflow-capacity-power).

## Probe requirements

The unit's control board exposes temperature and humidity readings, but most
probes must be **installed by the installer** — they do not come built-in.

| What you need | Hardware | Notes |
|--------------|----------|-------|
| Room temperature | NTC 10 kΩ B3435 (wall or duct mount) **or** CNU2 display | Needed for auto cooling/heating and dehumidify gating |
| Room humidity | 0–10 V or 4–20 mA humidity transmitter **or** CNU2 display | Needed for auto dehumidify |
| Outdoor temperature | NTC 10 kΩ B3435, IP65-rated | Only needed for Free-Cooling/Heating (PG03); otherwise optional |
| Exhaust / supply air temperature | NTC 10 kΩ B3435 | Optional; display/monitoring only |

**If you have no display and no external probes**, set the `probe_source` select
entity to **"None / external probes"** (HA00 = 0) and disable the display input
(PH01 = 0, via the installer menu once). The unit then responds only to
explicit Modbus commands — dehumidify, cooling and fan control all work
normally; only the _automatic_ setpoint-based triggers are inactive. The
`temp_probe_ok` and `humidity_probe_ok` binary sensors will read **OFF** — this
is expected, not an error.

See [`references/README.md` — Probes](references/README.md#probes-built-in-display-and-external-sensors)
and [`references/MODBUS_REGISTERS.md` §14](references/MODBUS_REGISTERS.md#14-probes-built-in-display-and-external-sensors)
for full probe specifications, wiring, and the HA00/PH01 configuration detail.

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
