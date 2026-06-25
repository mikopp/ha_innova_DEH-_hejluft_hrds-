# Innova DEH+ / hej.luft HRDS+ — Home Assistant integration

Home Assistant custom integration for the **Innova DEH+** air dehumidification
module (sold in Austria as the **hej.luft HRDS+**) over **Modbus TCP**.

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
  * **Dry** — dehumidification
  * **Cool** — active cooling (the unit's "integration" function)
  * Target humidity and target temperature are settable.
* **Sensors** — room/outdoor/water/supply temperatures, room humidity, air
  quality, fan output %, fan RPM, compressor output %, active setpoint, and
  enum status sensors (unit status, season, fan status, compressor status).
* **Binary sensors** — dehumidify requested, fan integration active, alarm
  active.
* **Switches** — unit on/off, dehumidify, active cooling, plus the three
  "enable control via Modbus" registers.
* **Numbers** — humidity setpoint, summer/winter temperature setpoints, and the
  per-mode fan speed bands.

See [`references/README.md`](references/README.md) for the full capability list
and [`references/MODBUS_REGISTERS.md`](references/MODBUS_REGISTERS.md) for the
register-level detail.

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

### Passive airflow vs. "integration" (fan) mode

The HRDS+ sits on the supply branch of your central MVHR ("inflow pipe"), and
the word *integration* is used by the manufacturer for two different things, so
it's worth being precise:

* **Passive airflow** — the unit's **own fan is off**, but your central MVHR is
  still pushing air through the duct, so air keeps flowing. You don't switch
  this on; it's simply what happens when the unit isn't running its fan. There
  is **no dedicated sensor** for it — watch **Supply fan status = Off** while
  **Unit status = On** (and **Fan integration active = off**). The unit can't
  measure the upstream MVHR's flow, so rely on your central system for the
  actual rate. Use this when you only want the background ventilation and don't
  need drying or cooling — keep the climate entity **Off**.
* **Fan integration** — the unit runs **its own fan** to blend (integrate) the
  central inflow air with room air across its coil. This happens automatically
  whenever the unit needs airflow (dehumidifying or cooling). The **Fan
  integration active** binary sensor tells you when it's running; **Supply fan
  output %** and **Supply fan speed (RPM)** show how hard. Shape it with the
  per-mode fan-speed `number` entities (dehumidify band vs. cooling band).

There is no separate "turn the fan on" control: the fan follows the operating
mode. Put the climate entity in **Dry** or **Cool** to make the unit run its fan
(integration); leave it **Off** to fall back to passive airflow only.

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

## Prerequisites

* An Innova DEH+ / hej.luft HRDS+ with the Modbus RTU/RS-485 control board and a
  Modbus-RTU-to-TCP gateway reachable on your network.
* Temperature/humidity readings require the wired display or external probes to
  be present (per the manufacturer manual).

## Disclaimer

Use at your own risk. Many of the writable registers change installer-level
behaviour. Only change settings you understand.

## Credits

Architecture closely follows the
[`ha_comfoconnectpro`](https://github.com/hstrohmaier/ha_comfoconnectpro)
integration. Documentation © Innova / hej.luft (see `references/`).
