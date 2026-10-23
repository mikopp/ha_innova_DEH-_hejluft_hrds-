# Innova DEH+ / hej.luft HRDS+ — Home Assistant integration

[![Release](https://img.shields.io/github/v/release/mikopp/homeassistant-innova-hrds)](https://github.com/mikopp/homeassistant-innova-hrds/releases)
[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)
[![Lint](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/lint.yaml/badge.svg)](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/lint.yaml)
[![hassfest](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/hassfest.yaml)
[![HACS](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/hacs.yaml/badge.svg)](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/hacs.yaml)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mikopp&repository=homeassistant-innova-hrds&category=integration)

**English** · [Deutsch](README.de.md)

Home Assistant custom integration (installable with **HACS**) for the **Innova
DEH+** / **hej.luft HRDS+** ducted dehumidifiers (models *HRDS+ 30* and
*HRDS+ 50*, also written HRDS 30 / HRDS 50, or *DEH+ 30* / *DEH+ 50*, also
written DEH 30 / DEH 50). It controls and monitors the unit locally over
**Modbus TCP**, without any cloud. The units it is meant for are listed under
[Compatible devices](#compatible-devices).

**Deutsch:** Home-Assistant-Integration (per **HACS** installierbar) für die
Entfeuchter **hej.luft HRDS+ 30 / 50** und **Innova DEH+ 30 / 50**
(Taupunktentfeuchtung mit Lüftung und Flächenkühlung). Sie steuert und
überwacht das Gerät lokal über **Modbus TCP**, ohne Cloud. Installation und
Einrichtung stehen unter [Install and set up](#install-and-set-up) (derzeit nur
auf Englisch). Eine Kurzfassung mit Inhaltsverzeichnis: [README.de.md](README.de.md).

## Compatible devices

The unit is made by **[INNOVA S.r.l.](https://www.innova.it/)** (Storo, Italy).
hej.luft sells it in Austria under its own name as an OEM product. The
[CE declaration on the hej.luft site](https://www.hejluft.at/_files/ugd/714411_e735ab85400c485fa7c042fac92d3230.pdf)
names Innova as the manufacturer of the HRDS and HRDS+ dehumidification units.

* **[hej.luft HRDS+ 30 / HRDS+ 50](https://www.hejluft.at/hrds)** (also written
  HRDS 30 / 50), with the type-plate codes of the
  [technical handbook](https://www.hejluft.at/_files/ugd/714411_f1ffc5d222f4476da2e37f29c64a7f93.pdf),
  for example *HRDS+ 30 H R K DC*.
* **[Innova DEH+ 30 H / 50 H](https://www.innova.it/en/products/vmc/dehumidifiers/deh-ad-incasso-orizzontale/)**:
  Innova's own name for the same unit, with the same sizes and nominal airflow
  (300 / 500 m³/h). hej.luft does not build or change it: the maintainer's
  HRDS+ 30 was shipped directly from Italy and is physically the same device as
  the DEH+ 30 H, and the integration was developed against it. The 50 sizes are
  untested (see the beta notice). The DEH+ installation manual kept in
  `doc/references/` describes the older microswitch controller, not the EVCO "K"
  board of the HRDS+; the registers and behaviour here come from the HRDS+
  handbooks.

> *If your unit uses the Innova board and is sold under another name, open an
> issue and link its product page.*

## Release 0.9.5 — beta, not 1.0 yet

The integration is released and usable, but it is a **beta**.

* **Developed against and tested on:** one hej.luft **HRDS+ 30 with
  recirculation** (`R` variant), run **headless**: no CNU2 display, no external
  room/outdoor probes, behind a Modbus RTU→TCP gateway, in the brine circuit of
  a ground-source heat pump. Which units and installations are known to work,
  and what was seen on each: [Tested units and installations](doc/tested-setups.md).
* **Not tested on real hardware:** Other versions like the HRDS+ 50, units
  without recirculation (non-`R`), units with a display or external probes
  (automatic setpoint control), winter heating, free cooling.
  **The fan speed is the unit's:** Home Assistant shows it but cannot set it,
  because the unit takes no fan-speed request over Modbus. Raising *Fan min
  speed* raises a running fan ([Fan speed](#fan-speed)).
  The open items are listed in [`plans/todo.md`](plans/todo.md).
* **Climate *Auto* mode is not tested on a real device.** It only appears
  with a display or room probe. CI tests it against a simulated display unit
  derived from the headless dump, not against a real display unit.

Reports from other units are very welcome, see
[Reporting issues](#reporting-issues). The aim for 1.0 is in
[Road to 1.0](#road-to-10).

## Quick start

1. [Install](#1-install) the integration with HACS and restart Home Assistant.
2. [Add it](#2-add-the-integration) under *Settings → Devices & Services*,
   with the address of your Modbus-TCP gateway.
3. [Check the setup](#3-check-the-setup): open the **HRDS+ setup** device and
   make sure **Setup check** reads `ok`.
4. **[Choose what Home Assistant may control](#4-choose-what-home-assistant-may-control).**
   Turn on the **Modbus enables** for the functions you want (on/off,
   dehumidify, integration), then **Allow operational requests**. Both are
   **off after a fresh install** (the unit's on/off enable from factory), and
   the integration never turns them on by itself. Without them it monitors:
   readings and settings work.
5. Read [How the unit works](#how-the-unit-works) for the operating modes,
   including the passive cold-water path, and how to drive them.

## What it does

The integration talks to the unit's control board via Modbus TCP and exposes:

* A **climate entity** showing room temperature & humidity, with the current
  HVAC action (off / idle / fan / drying / cooling / heating) and an HVAC mode
  you can set to pick the operating mode (see [How the unit works](#how-the-unit-works)):
  * **Off** — clears both requests and turns the unit off (Modbus on/off off).
    Off always means the unit is off, so it never disagrees with
    `switch.unit_on_off`
  * **Standby** (Home Assistant's *fan only* mode, renamed) — the unit is on
    with nothing requested and nothing on the unit that could start a request
    (no display, no room probe): it waits. While the fan of an `R` unit runs
    without a request (for example its run-on) the action is *Fan*;
    otherwise it is *Idle*. Offered
    instead of Auto; climate *turn on* goes here
  * **Dry** — dehumidification; supply air leaves at about room temperature
  * **Cool** — the "integration" request in **summer**: dehumidifies *and* cools
    (with cold enough water without the compressor, see
    [Operating modes in summer](#operating-modes-in-summer))
  * **Heat** — the "integration" request in **winter**, offered when you
    enable winter heating in the options (never on a brine circuit), and shown
    whenever the unit has a winter integration request from elsewhere
  * Target humidity / temperature are only offered when a display or a room
    probe makes the unit act on them; without one Home Assistant does the
    regulating.
  * No fan mode: the unit takes no fan-speed request over Modbus (see
    [Fan speed](#fan-speed)). On an `R` unit every dehumidify or cooling
    request opens the recirculation damper and starts the fan (see
    [Fan and recirculation](#fan-and-recirculation)).
* **Sensors** — see the [entity reference](doc/entity-reference.md), including three computed airflow
  sensors derived from your model's calibration data.
* **Binary sensors** — dehumidify requested, recirculation active, probe
  health, overall alarm active, four individual alarm sensors (compressor
  low/high pressure, antifreeze, dirty filter), and a variant-detection sensor
  (integration function available).
* **Switches** — unit on/off, dehumidify, integration request, plus the three
  "enable control via Modbus" registers.
* **Numbers** — humidity setpoint, summer/winter temperature setpoints, and the
  per-mode fan speed bands.
* **Select** — season (summer/winter), T/H probe source (HA00), winter
  dehumidification mode (PU02).
* **Fan** — the supply/recirculation fan as readings: running, status,
  actual output % and the unit's manual request. The unit switches it with
  its requests; Home Assistant cannot.
* **Water-circuit diagnostics** — valve/pump output, condenser valve, water
  alarms and a *Water circuit check* summary. Read-only: the unit runs its own
  water valve and pump.
* An optional **installer** child device with the complete installer menu
  (about 240 parameters), kept off the main device page. Off by default; turn
  it on in the integration options.

How the unit itself behaves (all variants, seasons, display/probe setups, with
sources and what has been tested on hardware) is in
[`doc/references/UNIT_BEHAVIOUR.md`](doc/references/UNIT_BEHAVIOUR.md); the registers
are in [`doc/references/MODBUS_REGISTERS.md`](doc/references/MODBUS_REGISTERS.md).

## Install and set up

### Before you start

* An Innova DEH+ / hej.luft HRDS+ with the Modbus RTU/RS-485 control board and a
  Modbus-RTU-to-TCP gateway reachable on your network. You need the gateway's
  IP address or hostname, its port (usually 502) and the unit's Modbus slave ID
  (factory: 1).
* Home Assistant 2026.10 or newer (see [Requirements](#requirements)).
* Room temperature/humidity readings require the wired CNU2 display or external
  probes (see [Probe requirements](#probe-requirements)). Without either, the
  integration still works; Home Assistant then does the regulating.

### 1. Install

#### HACS (custom repository)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mikopp&repository=homeassistant-innova-hrds&category=integration)

Or by hand:

1. In HACS, add this repository as a custom repository (category: *Integration*):
   `https://github.com/mikopp/homeassistant-innova-hrds`
2. Install **Innova DEH+ / hej.luft HRDS+ Dehumidifier** and restart Home Assistant.

HACS installs the `innova_hrds.zip` asset attached to each
[GitHub release](https://github.com/mikopp/homeassistant-innova-hrds/releases);
each release is prepared so that `manifest.json`, the changelog and the tag
name the same version, and the release workflow checks that before zipping, so
the version Home Assistant shows is the release version. Updates appear in
HACS when a new release is published. Releases 0.9.x are normal (not
"pre-release") releases, so they are offered without enabling HACS' beta versions.

#### Manual

Copy `custom_components/innova_hrds/` into your Home Assistant
`config/custom_components/` directory and restart.

### 2. Add the integration

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
| Water register connected to | Heating/cooling circuit | Choose **Brine circuit** if the unit is on the brine of a ground-source heat pump. See [Water circuit](#water-circuit-and-brine). |
| Allow winter heating | off | Lets Home Assistant request heating in winter (the integration request heats with water from the heating circuit), and accepts that the unit heats on its own (see [The unit heats on its own](#the-unit-heats-on-its-own)). Off: Home Assistant refuses its own winter integration requests; the unit can still heat by itself. Cannot be turned on together with a brine circuit. |
| Brine temperature guard sensor | empty | Optional HA temperature sensor on the brine supply. See [Brine temperature guard](#brine-temperature-guard). |
| Brine guard minimum temperature | 8 °C | Lowest brine temperature at which a request may start. |

Before anything is written, the integration checks that the address really is an
HRDS+: the controller must identify itself as EVCO `EPB9…` over Modbus (FC 43)
and its status registers must make sense. Anything else is refused with
*"not an HRDS+"*, so a wrong IP or slave ID cannot have settings written into it.
If the form says *"Cannot reach the unit"*, check the host, the port and the
Modbus slave ID.

Without a display, the integration sets two registers the unit needs in order
to run at all: **PH01 = 0** (no on/off from a display; with PH01 = 1 and no
display the unit stays *Off (display)* and ignores Modbus) and **HA00 = 0** (no
display sensors). It checks them every poll and writes one only when it reads
wrong (the unit keeps its settings in EEPROM, which wears with every write, and
across a power cycle); a manual change to one of them is undone. If you *do*
have a display, tick the option and the integration leaves PH01/HA00 alone.
Nothing else is written on connection: the Modbus enables **PH02/PH27/PH28**
are yours (see [step 4](#4-choose-what-home-assistant-may-control)).

### 3. Check the setup

All setup happens through the integration, after it has connected. Nothing needs
to be changed on the unit beforehand. Open **Settings → Devices & Services →
Innova HRDS+** and look at the **HRDS+ setup** device first. The device page is
split by purpose:

| Where | What is there | When you touch it |
|-------|---------------|-------------------|
| **`HRDS+ setup`** device (linked to the main device) | Everything that decides whether the unit can run at all: the **Setup check** sensor, the **Allow operational requests** switch, the Modbus/display enables (PH01, PH02, PH27, PH28), probe allocation (HA00, HA02, HA03) and probe-OK flags, remote on/off input (HB03) and its contact state, season input (HB04, PC11), time programs (PH03), temperature unit (PH05), machine type (PG01), free-cooling/integration enables, and the fan/damper output wiring (HC04, HD01, PS01). | Once, after installing, and again if the wiring changes |
| **`HRDS+`** device, *Configuration* section | Post-setup tuning: setpoints (only with a probe), per-mode fan min/max, dehumidify differential, minimum room temperature (PU13/PU14), fan run times, humidity clamps | Occasionally |
| **`HRDS+`** device, main section | Climate, fan, season, the request switches (on/off, dehumidify, integration), live readings, status and alarms | Day to day |
| **`HRDS+`** device, *Diagnostic* section | Water valve/pump, condenser valve, water circuit check, airflow calibration, fan request echo | When troubleshooting |
| **`HRDS+ installer`** device (linked to the main device) | The rest of the installer menu (see [Installer device](doc/entity-reference.md#installer-device-hrds-installer)) | Rarely, by an installer |

Entity ids follow the device name, so setup entities are prefixed with the setup
device name (for example `sensor.hrds_setup_setup_check`); the
[entity reference](doc/entity-reference.md) omits the prefix.

**What is left to fix:** while *Setup check* reads *Needs attention (see
attributes)*, open it (click the row, then *Attributes*). `to_fix` lists each
open item in plain words, in the Home Assistant language, with what to do about
it; `issues` has the same items as short codes (explained in the
[First-use checklist](#first-use-checklist)). The device page itself cannot
show attributes, so this sensor is the one place to look.

**What to check, in this order:**

1. **Setup check** (on the setup device) reads `ok` or `attention`. If it reads
   `attention`, the `issues` attribute says what; the table under
   [First-use checklist](#first-use-checklist) explains each one. A factory
   unit usually shows `free_cooling_without_outdoor_probe` until you switch off
   **Enable free cooling (PG03)** (no outdoor probe is fitted). Each setup
   switch carries a `hint` attribute (open the entity, *Attributes*) that says
   when to leave it on or turn it off:

   | Switch | Leave | Why |
   |--------|-------|-----|
   | Enable free cooling/heating (PG03) | **Off** unless an outdoor probe is wired | It acts on the outdoor temperature (bypass relay). With no probe there is no valid reading, so the unit may behave unpredictably. Also off when a central ventilation system handles free cooling. |
   | Enable on/off via display (PH01) | **Off** without a CNU2 display | Otherwise the unit stays off waiting for the display. |
   | Enable on/off, dehumidify (DEU), integration (INT) via Modbus (PH02, PH28, PH27) | **Your choice** | Each one lets Home Assistant control one function; see [step 4](#4-choose-what-home-assistant-may-control). The integration never changes them. |
2. **Probe settings** match what is wired. Without a display and without
   probes, *T/H probe source (HA00)* is *None / external probes* and both *T/H
   probe temperature / humidity input* selects are *Unused*; the integration
   sets HA00 for you. Select a probe type only where a probe is really wired,
   otherwise the unit raises alarm AL28 / AL34.
3. **Unit facts** are right: *Machine type*, *Recirculation damper relay
   allocation* (not `disabled` on an `R` model), *Remote on/off input* and
   *Remote on/off contact closed*, *Time programs enabled* (switch it off for
   Modbus-only control), *Temperature unit* (°C).
4. **Season and water circuit** fit your installation: `select.season`, and the
   integration options *Water register connected to* and *Allow winter heating*.
5. **Minimum room temperature (PU13)** in the Configuration section of the main
   device: the unit refuses to dehumidify below it.

#### First-use checklist

1. Open the **HRDS+ setup** device. The **Setup check** sensor reads `ok` or
   `attention`; its `issues` attribute lists what to look at:

   | Issue | Meaning and what to do |
   |-------|------------------------|
   | `headless_settings_pending` | Without a display, PH01 and HA00 must be 0. The integration writes them on the next poll; if this persists, the unit does not keep the write, and after three tries the integration stops writing it (check the log). |
   | `unit_off_by_digital_input` | The remote on/off contact (OFF/OFF terminals, HB03) is open, so the unit is forced off. Close it (the factory bridge) or set HB03 accordingly. |
   | `unit_off_by_scheduler` / `unit_off_by_clock` | A time program or the internal clock holds the unit off. Check PH03 (**Time programs enabled**); switch it off for Modbus-only control. |
   | `unit_waiting_for_first_on` | Without a display, *Unit status* still reads *off by display* although PH01 is 0: the unit keeps a stored OFF until the first Modbus ON. Turn on *Enable on/off via Modbus (PH02)* and *Allow operational requests*, then switch on *Unit on/off (Modbus)* once (main device). |
   | `unit_off_by_display` | Only reported when the display option is ticked: the display has switched the unit off. |
   | `room_temperature_probe_missing` | *T/H probe temperature input* (HA02) says a probe is on AI2, but nothing is wired. The unit will wait for a room temperature. Set `select.ai2_allocation` to *Unused* or wire the probe. |
   | `room_humidity_probe_missing` | Same for *T/H probe humidity input* (`select.ai3_allocation`, HA03) and the humidity probe. |
   | `probe_input_unrecognised` | HA02 or HA03 holds a code that is not one of the documented probe codes, so the select shows unknown (the raw code is in the log). Pick an option, or check what the installer wired. |
   | `time_programs_enabled` | PH03 is on; the unit may switch itself off on schedule. |
   | `free_cooling_without_outdoor_probe` | **Free cooling** is on but no outdoor probe delivers a value. Turn off `switch.enable_free_cooling` unless an outdoor probe is fitted. |
   | `temperature_unit_fahrenheit` | PH05 is set to °F; the integration assumes °C. |
   | `water_pump_output_not_configured` | Relay K5 (external water valve and the PM pump output) is not configured, so the unit cannot start the circulation pump. Check HD05 on the installer device (12 = water valve) and the wiring. |
   | `winter_dehumidify_on_brine` | Brine circuit selected, no brine temperature guard, but PU02 allows dehumidifying in winter - the coil can freeze. Set `select.winter_dehumidify` to *Disabled*, or configure a [brine temperature guard](#brine-temperature-guard). |
   | `unit_heats_on_its_own` | The unit has a room temperature source and the integration function, so in winter it heats by itself below SEtH − PF12, and *Allow winter heating* is off. Accept it (turn the option on) or stop it, see [The unit heats on its own](#the-unit-heats-on-its-own). |
   | `unit_heats_on_its_own_on_brine` | Same on a brine circuit, where the unit pumps cold brine through the register instead of heating. Lower the winter setpoint (and PH09) or switch the unit off in winter. |
   | `winter_heating_without_integration` | *Allow winter heating* is on but the unit has no integration function (PG02 = 0), so nothing can heat. Turn the option off or enable PG02 on the unit. |

2. Read the remaining setup entities and confirm they match your installation:
   *Machine type* (supply only, or supply and exhaust fan), *Recirculation
   damper relay allocation* (a value other than `disabled`/unused on an `R`
   model), *T/H probe temperature / humidity input* and the *probe OK* flags (which probes the unit
   believes are connected), *Remote on/off input* and *contact closed*.
3. Check **Minimum room temperature (PU13)** in the Configuration section. The
   unit refuses to dehumidify below it, and what it does with no room
   temperature probe is not yet verified on hardware - see
   [`plans/todo.md`](plans/todo.md).
4. Check the **season** (`select.season`; read-back `sensor.operating_mode`) and
   the integration options *Water register connected to* and *Allow winter
   heating*.
5. On a water circuit fed by a pump the HRDS+ switches (brine in particular):
   watch `sensor.water_valve_pump` turn *On* with the first request and the
   **Water circuit check** stay `ok` (see [Water circuit](#water-circuit-and-brine)).
6. When the setup check is `ok`, continue with
   [step 4](#4-choose-what-home-assistant-may-control) and choose what Home
   Assistant may control.

### 4. Choose what Home Assistant may control

You are in charge of two things, both on the **HRDS+ setup** device. The
integration never turns either on by itself.

1. **The Modbus enables on the unit**, one per function. Turn on the ones
   for the functions you want Home Assistant to control. Leave a function's
   enable off to keep it on the unit's own controls (display, remote contact,
   digital inputs). Home Assistant then only shows what the unit does, and
   refuses that operation with a message naming the switch to turn on.
2. **Allow operational requests**, the integration's own safety gate (below).

With every enable off (or the gate off), the integration is a monitor: every
reading, status, alarm and setting works, and nothing can make the unit act.

#### Which enable gives which function

| To do this from Home Assistant | Turn on (setup device) | Register | While it is off |
|---|---|---|---|
| Switch the unit **on and off**: climate *Off*, climate *turn on/off*, switching from *Off* to any mode, `switch.unit_on_off` | **Enable on/off via Modbus (PH02)** | 1778 | The unit's own controls switch it. The climate offers only the modes on the side the unit is on: no *Off* while it runs, only *Off* while it is off. |
| **Dehumidify**: climate *Dry*, `switch.dehumidify` | **Enable dehumidify (DEU) via Modbus (PH28)** | 1870 | No *Dry*. A dehumidify request from the unit's own humidity logic or the DEU input still shows as *Dry*. |
| **Cool in summer, heat in winter**: climate *Cool* / *Heat*, `switch.integration_request` | **Enable integration (INT) via Modbus (PH27)**; the unit also needs the integration function (PG02, `DC` models) | 1869 | No *Cool* / *Heat*. The unit's own integration (its room temperature logic, the INT input) still shows. |

Good to know:

* **Full control** from Home Assistant (a unit without a display): turn on all
  three, then *Allow operational requests*.
* The real unit this integration was developed on shipped with PH02 **off**
  and PH27/PH28 **on** ([as-delivered settings](doc/references/UNIT_BEHAVIOUR.md#15-as-delivered-settings-vs-handbook-defaults)):
  Dry and Cool were allowed, but Home Assistant could not switch the unit on
  until PH02 was turned on.
* The unit acts on a request register only while its enable is on, and it
  presumably keeps a request written earlier
  ([UNIT_BEHAVIOUR §3.3](doc/references/UNIT_BEHAVIOUR.md#33-requests-deu-and-int)).
  So turning on an enable while its request is still on starts that request
  at once. The integration therefore checks that like a start (the gate, the
  brine guard, the season).
* The unit keeps its settings across a power cycle
  ([UNIT_BEHAVIOUR §3.6](doc/references/UNIT_BEHAVIOUR.md#36-persistence-across-a-power-cycle)),
  so the enables stay as you left them.
* Fan speed and every setting (setpoints, selects, setup entities) need no
  enable.

#### Allow operational requests

> **This is the switch that makes the unit operational.** After a fresh install
> **`switch.hrds_setup_allow_operational_requests`** (on the **HRDS+ setup**
> device) is **off**. While it is off, Home Assistant cannot make the unit act.

What it blocks, and what it does not:

| Blocked while the switch is off | Always works |
|---|---|
| Turning the unit **on** (also climate *Auto*), **dehumidify** (climate *Dry*, `switch.dehumidify`), **integration** (climate *Cool* / *Heat*, `switch.integration_request`), and any **non-zero fan speed** | Turning things **off** (climate *Off*, switches off, fan 0), reading every sensor, and every configuration write (setpoints, selects, setup entities) |

A blocked request fails with *"Operational requests are not allowed yet. Review
the setup entities, then turn on 'Allow operational requests'."* That message
means this switch is still off.

To turn it on, open the **HRDS+ setup** device and toggle **Allow operational
requests**, or call the service:

```yaml
action: switch.turn_on
target:
  entity_id: switch.hrds_setup_allow_operational_requests
```

Good to know:

* It is the integration's own safety gate, not a register on the unit, and it
  is not tied to the setup check: you decide when you have looked at the setup
  entities. Turn it on once the setup check is `ok`.
* Your choice is remembered across restarts and reloads.
* Turning it off again does not stop a running unit; it only refuses new
  requests. To stop the unit, set the climate to *Off*: that clears both
  requests and switches the unit off (with PH02 on).

### 5. First run

1. Set the climate entity to **Dry** (or turn on `switch.dehumidify`). Only
   turning on `switch.unit_on_off` is not enough on a unit without a display
   or room probe: it then has nothing to act on, so the climate entity shows
   *Standby* with the action *Idle*.
2. Watch **Unit status**: a unit waiting for its first request reads *Off
   (Modbus)* and changes to *On*. The recirculation fan (`R` units) starts
   with the request.
3. If it does not start, look at the **Setup check** `issues`, at the error
   Home Assistant showed for the request (a refused request names the reason),
   and at the Home Assistant log. See [Reporting issues](#reporting-issues) if
   you need help.

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

## How the unit works

A short summary for using the integration. The complete description of the
unit, with handbook references and what has been seen on real hardware, is
[`doc/references/UNIT_BEHAVIOUR.md`](doc/references/UNIT_BEHAVIOUR.md).

### What is inside

The unit sits in the supply duct of the central ventilation (MVHR). The air
passes the **evaporator** of a small compressor circuit (held at about 6 °C, so
moisture condenses) and then a **water register**. The compressor's heat goes
into the building's water circuit; an internal valve
(`sensor.water_condenser_valve`) decides whether that warm water also reheats
the dried air. The external valve and pump (`sensor.water_valve_pump`) connect
the unit to your water circuit: a heat pump's surface heating/cooling circuit,
the brine of a ground-source heat pump, or a separate ground loop. `R` units
add a recirculation fan and damper, which run with **every** request (see
[Fan and recirculation](#fan-and-recirculation)). Details:
[UNIT_BEHAVIOUR §2](doc/references/UNIT_BEHAVIOUR.md#2-hardware-air-path-water-path-terminals).

### Two requests

The unit knows exactly two requests:

* **DEU** — dehumidify (`switch.dehumidify`, climate **Dry**)
* **INT** — integration (`switch.integration_request`, climate **Cool** in summer,
  **Heat** in winter)

What they do depends on the season and on how cold the water is.

### Operating modes in summer

| Mode | Requested by | What the unit does | Air leaves |
|------|--------------|--------------------|-----------|
| **Dehumidify** | DEU (climate **Dry**) | Compressor runs; its heat reheats the air | Dried, at about room temperature |
| **Cool and dehumidify** | INT (climate **Cool**), with PU05 on (factory) | Compressor runs; all heat goes into the water | Dried and cold |
| **Passive (cold water)** | Any request while the water is below **PU08** (factory 10 °C) | **Compressor stays off**; the cold water cools and dries the air. With PU09 on, the compressor joins after PU10 (120 min) if the request is still open | Dried and cooled, without compressor |

The passive path is automatic; nothing has to be set for it. Cold brine early
in summer runs it, a heat pump in cooling mode (about 16–20 °C) runs the
compressor, and water above PC07 (30 °C) blocks with AL03. PU08, PU09 and PU10
are on the installer device.

**PU05, *Force dehumidify when cooling*** (`switch.force_dehumidify_in_cooling`,
factory on) is what makes an INT request start the compressor. With PU05 off,
INT presumably cools with the water only; **not tested on a real unit**, leave
PU05 on unless you want to try this.

Sources and the remaining combinations:
[UNIT_BEHAVIOUR §6](doc/references/UNIT_BEHAVIOUR.md#6-summer-operation).

### Operating modes in winter

| Request | What the unit does |
|---------|--------------------|
| INT (climate **Heat**) | **Heating support**: compressor off, warm water from the heating circuit through the water register. Home Assistant requests it only with the option *Allow winter heating*, never on brine; the unit also raises it by itself (see [The unit heats on its own](#the-unit-heats-on-its-own)) |

The unit has **no heat source of its own** and no heating register. A winter
INT request only opens the external valve, runs the pump and the fan, and keeps
the compressor off (handbook §2.6.2, §6.4). The air gets warmer only if the
building's heating circuit delivers warm water (boiler, or a heat pump in
heating mode). So the climate action shows **Heating** only when the unit can
be doing it: there is a winter INT request (a latched one, from Home Assistant
or a display, or the unit's own while the room is below SEtH + PF12), the unit
has the integration function PG02, the valve/pump output is on, AL04 is not
active, the compressor is off, and the water temperature is at least **PC08**
(the unit's own minimum for winter integration; handbook 20 °C, the reference
unit shipped with 10 °C). Otherwise it
shows *Idle*, or *Drying* while the unit dehumidifies. The option *Allow
winter heating* does not enter: the unit knows nothing of it, so a winter INT
set elsewhere shows as *Heat*. On brine a winter INT only circulates cold
brine: it never shows as *Heat* or *Heating*. Not tested on a real unit.
| DEU (climate **Dry**) | Only if PU02 (`select.winter_dehumidify`) allows it; factory: disabled. On brine only with a passing [brine temperature guard](#brine-temperature-guard) |

On a brine circuit the handbook forbids heating and active winter
dehumidifying (the register can freeze) and recommends switching the unit off
in winter; see [Water circuit and brine](#water-circuit-and-brine).

### How to use it

1. **Set the season** with `select.season` (without a display; see
   [Season and winter heating](#season-and-winter-heating)).
2. **Pick the mode on the climate entity:** **Dry** to dry the air at room
   temperature, **Cool** to dry and cool (summer), **Auto** to let the unit
   decide from its own room sensors (only offered with a display or room
   probe), **Standby** to have it on and waiting (without a display or room
   probe), **Off** to stop: it clears both requests and turns the unit off.
   Climate *turn on* goes to Standby (Auto where the unit regulates by
   itself), *turn off* to Off. The
   switches `switch.dehumidify` and `switch.integration_request` do the same per
   request. Every start needs the matching Modbus enable and [Allow operational requests](#4-choose-what-home-assistant-may-control).
3. **Decide who regulates.** Without a display or room probe the unit runs
   while a request is on and ignores its setpoints, so let Home Assistant
   switch **Dry** / **Cool** on and off (for example a generic hygrostat or
   thermostat on your own sensors). With a display or probe the unit regulates
   to its own targets (see
   [Setting target humidity and target temperature](#setting-target-humidity-and-target-temperature)).
4. **Leave the passive path to the unit.** You can see it run: the request is
   on, `sensor.water_valve_pump` is *On*, `sensor.water_temperature` is below
   PU08, and `sensor.compressor_status` is not *On*. The water check then lists
   `water_below_compressor_limit`, which here is information, not a fault.
5. **The fan** starts at the active mode's minimum speed; raise the minimum
   to run it faster (see
   [Fan speed](#fan-speed)).

## Using the integration

### Season and winter heating

Without a display the season is set with `select.season` (HB04 = 4 summer,
3 winter). Because winter changes the integration request from cooling to
heating, the integration guards it:

* An integration request (switch or climate Cool/Heat) is **refused unless the
  unit reports summer**, unless you enabled **Allow winter heating** in the
  options. With the season on *auto* (1583), the mode status (1110) decides
  which season is in force; an unknown season counts as not summer.
* Switching the season to winter is refused while an integration request is on,
  and on brine without a passing brine guard while the unit is on and its room
  probe could make it dehumidify in winter by itself (PU02 enabled).
* *Allow winter heating* governs only what Home Assistant requests. The unit
  can heat by itself below SEtH − PF12 (about 13.5 °C with the factory PH10 cap and
  PF12), see below and
  [UNIT_BEHAVIOUR §3.3](doc/references/UNIT_BEHAVIOUR.md#33-requests-deu-and-int).
* Not something software controls: in OFF/standby the internal water valve is
  open. If warm water circulates through the unit, it warms the ventilation air
  passing through - unless an external valve on V3V closes the circuit.

### The unit heats on its own

With a room temperature source (a display, or a probe on AI2) and the
integration function (PG02), the unit raises its own winter integration request
when the room falls below **SEtH − PF12** and drops it above SEtH + PF12
(handbook §6.1.2). It does not ask Home Assistant, and *Allow winter heating*
cannot stop it: the unit knows nothing of that option. The factory PH10 cap
(14 °C, also PH09) only limits SEtH, so with the factory dead band (PF12 =
0.5 K) the unit heats whenever the room is below 13.5 °C. Headless without a
probe it never heats by itself.

The integration tells you instead of pretending otherwise:

* `binary_sensor.automatic_heating` (*Unit heats on its own*) is **on** while
  the unit, switched on in winter, can heat by itself. Its attributes say on
  what: `starts_below` / `stops_above` (SEtH ∓ PF12), `winter_setpoint`,
  `dead_band`, `winter_setpoint_min` / `_max` (PH09/PH10), the room
  temperature and its source, and `heating` (the unit heats right now). It is
  not created without a room temperature source or the integration function.
* The climate entity shows **Auto** with the action **Heating** while it does,
  and **Off** switches the unit off, since only that stops its own logic.
* The setup check lists `unit_heats_on_its_own` while *Allow winter heating* is
  off, and `unit_heats_on_its_own_on_brine` on a brine circuit (there it pumps
  cold brine through the register instead of heating).

To react, either accept it (turn *Allow winter heating* on) or stop it:

* **Lower the threshold**: set *PH09 Winter setpoint min* (installer device,
  enable it in the options) to 5 °C or less, then the winter setpoint to 5 °C.
  The unit then only heats below 4.5 °C, and the setup check stops listing it.
* **Switch the unit off in winter** (what the handbook recommends on brine).
* Setting PG02 = 0 or unallocating the room probe also stops it, but takes
  summer cooling or the unit's own humidity control with it.

### Water circuit and brine

The unit switches its water circuit itself: relay K5 drives the external valve
(V3V) and, together with it, the pump output (PM). The integration only shows
it (`sensor.water_valve_pump`) and never overrides it. The **Water circuit
check** (`sensor.water_check`, attribute `issues`) flags:

| Issue | Meaning |
|-------|---------|
| `pump_off_while_compressor_runs` | Compressor on but the valve/pump output off - no water through the condenser |
| `water_too_warm` | While circulating, water is above PC07 (max water temperature for dehumidify / summer integration); AL03 follows after PA16 |
| `water_below_compressor_limit` | While circulating, water is below PU08: the compressor will not start and the unit runs on the [passive cold-water path](#operating-modes-in-summer). Expected with cold brine in early summer, not a fault |
| `high_water_temperature_alarm` / `low_water_temperature_alarm` / `antifreeze_alarm` | AL03 / AL04 / AL16 active |
| `brine_unit_on_in_winter` | Brine circuit, winter, unit on. The anti-stagnation cycle (Pb07/Pb08) pulses valve and pump and can blow short bursts of cold air; the handbook recommends switching the unit off in winter |
| `brine_guard_blocking` | The [brine temperature guard](#brine-temperature-guard) currently refuses requests |

With **Water register connected to = Brine circuit** (handbook §3.8.7), heating
is impossible and dehumidifying in winter is forbidden because the coil can
freeze. The integration refuses winter integration requests regardless of the
heating option. Winter dehumidify requests are refused too, unless a brine
temperature guard is configured and passing. Without a guard, the setup check
flags PU02 if it allows winter dehumidifying.
In the handbook's brine variants (4 to 6, §3.8.7) the HRDS+'s PM output
switches an additional brine pump through a relay; that wiring is what
`sensor.water_valve_pump` reflects. The maintainer's unit is wired as variant 6
(a branch parallel to the heat pump) and the pump starts on a request; see
[Tested units and installations](doc/tested-setups.md).

#### Brine temperature guard

The unit cannot tell how cold the brine is before it starts: its water probe
only sees the brine while valve and pump run (otherwise it reads the standing
water at plant-room temperature), and its own protections react only after
the fact (AL16 below PA43, factory 3 °C, stops the fan; AL04 and PU08 do not
cover winter dehumidifying). The freezing risk is on the air side: below about
0 °C brine, condensate freezes on the register fins.

If Home Assistant has a temperature sensor on the brine supply, for example
from the heat pump, set it as **Brine temperature guard sensor** in the
options. Then:

* A dehumidify or integration request, or switching the unit on while one is
  latched, **starts only while that sensor reads at least the minimum**
  (option **Brine guard minimum temperature**, default 8 °C) **and has
  reported within the last 24 h**. This applies in every season and to any
  water circuit. A sensor that is unavailable, not numeric or not a
  temperature also blocks. Switching off is always allowed.
* Why 8 °C: it stays well above the unit's own frost alarm (AL16 at PA43,
  factory 3 °C, which stops the fan and clears at PA43 + PA44 = 5 °C), and below
  PU08 (10 °C), so early-summer brine can still run the
  [passive cold-water path](#operating-modes-in-summer). An install that
  already saved the earlier default of 10 °C keeps it until you change it in
  the options.
* On a brine circuit a passing guard is what permits **dehumidifying in
  winter**. Without a guard, winter dehumidifying on brine is always refused.
  The unit itself only dehumidifies in winter if PU02
  (`select.winter_dehumidify`) is *With water*; the factory value is
  *Disabled*.
* Winter heating stays impossible on brine, guard or not.
* `binary_sensor.brine_temperature_guard` (device class *problem*) is the
  alarm indicator: **on** while the guard blocks. Its attributes give the
  source entity, temperature, minimum, last report and reason (`too_cold`,
  `stale`, `unavailable`, `not_a_number`, `not_a_temperature`). It is only
  created when a sensor is configured and stays available while the Modbus
  link is down.

The guard decides whether a request may **start**. It does not stop a request
that is already running when the brine cools; the indicator turns on and the
unit's own protections (AL16, AL11) remain in charge.

### Setting target humidity and target temperature

Without a display or a configured room probe the unit **ignores** its setpoints
(Modbus manual: *„Die Soll-Werte sind nur wirksam, wenn das Display vorhanden
ist oder externe Sensoren angeschlossen sind“*). In that case the integration
does not create them, and the climate entity offers no targets: use Home
Assistant (a generic hygrostat/thermostat on your own sensors) to switch
**Dry** / **Cool** on and off. The decision is made at start-up from HA02/HA03;
reload the integration after wiring a probe.

When a display or probe is present, both targets are exposed on the **climate
entity** (and as standalone `number` entities):

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

### Fan and recirculation

* **Passive airflow**: the unit's own fan is off and only the MVHR pushes air
  through. On an `R` unit this only happens while the unit is idle (Off or on
  with no request): watch **Supply fan status = Off**.
* **Every Dry or Cool request on an `R` unit opens the recirculation damper
  and runs the fan** (damper first, fan after the pre-start time, then the
  compressor). **Recirculation damper** and **Supply fan output %** show it.
* So an `R` unit never dehumidifies on passive airflow: the fan runs at
  least at its band minimum. Only a non-`R` unit (no fan, no damper) dehumidifies on
  MVHR flow alone. An unofficial I/O reassignment exists for `R` units; it is
  untested here and has a short-circuit risk if the recirculation inlet is
  teed into the extract duct.

The per-mode fan minimum `number` entities set how hard the fan runs (see
[Fan speed](#fan-speed)). Sources, vendor statements and the workaround:
[UNIT_BEHAVIOUR §9](doc/references/UNIT_BEHAVIOUR.md#9-fan).

### Drying with the fan on, but active cooling off

That is the climate entity's **Dry** mode: **Unit on/off = On**, **Dehumidify
= On**, **Integration request = Off**. The compressor runs for
dehumidification, the fan runs (**Supply fan status = On**, **Recirculation
active = on**, **Compressor status = On**), and the air leaves at about room
temperature. **Cool** adds the integration request on top (summer only).

### Airflow sensors

The integration provides three computed sensors that estimate the unit's
recirculation airflow **automatically** from the live fan output reading and your
calibration settings (see [Airflow calibration](#airflow-calibration-options)
above): the live estimate in m³/h, which updates every poll cycle
(`sensor.supply_fan_airflow`), the configured maximum from the options, and a
copy of it kept for convenience. They are listed in the
[entity reference](doc/entity-reference.md).

The formula is proportional: `Q = (output% / 100) × Q_max`, using the live
`supply_fan_output` register. The fan counts as running only when the unit's
own `supply_fan_status` says *On* or *Stopping* (the run-on), and as stopped
(0 m³/h) otherwise, not at a percentage of ours. Default
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
The derivation and a two-point calibration recipe are in
[`doc/references/README.md` — Translating fan speed to airflow](doc/references/README.md#translating-fan-speed--rpm-to-airflow-mh),
with the underlying spec data in
[Technical data](doc/references/README.md#technical-data-airflow-capacity-power).

### Fan speed

**The fan is the unit's; Home Assistant shows it and can neither switch it nor
set its speed.** The unit runs the fan with every dehumidify or integration
request and stops it after a run-on; no register switches it by itself. It
has no register for a fan-speed request from Modbus either. PM20 (1614), the
"manual fan speed" of the register list, is the **display's** setpoint
("read only" in the handbook): the unit sets it itself, acknowledges a written
value inside the band without keeping it, and refuses one outside the band.
So the fan is shown by readings only, with no fan entity, the climate entity
has no fan mode, and `sensor.hrds_manual_fan_speed` shows PM20.

The fan runs at the highest of the unit's own requests, kept within the active
mode's band (PF28–PF10 for dehumidify, PF27–PF09 for cooling): the 0–10 V
input, scaled into the band, and the manual (display) request, which PM20
shows. Without a display or 0–10 V signal the manual request starts each run
at the band **minimum**: 50 % as shipped. Details:
[UNIT_BEHAVIOUR §9.1](doc/references/UNIT_BEHAVIOUR.md#91-bands-and-sources).

What the integration shows:

* `binary_sensor.hrds_supply_fan_running`: whether the fan turns, from its
  status: on while *On* and during the run-on (*Stopping*), off while
  *Starting*, off and in alarm.
* `sensor.hrds_supply_fan_status`: the unit's fan status itself.
* `sensor.hrds_supply_fan_output` (%) and `sensor.hrds_supply_fan_airflow`
  (m³/h): the speed the fan runs at.
* `sensor.hrds_supply_fan_rpm`: only when an input is allocated to the fan
  tachometer, else unknown.
* `sensor.hrds_manual_fan_speed`: PM20, the unit's manual request. While the
  fan runs it reads the same as the output.

What works over Modbus is the band. The unit keeps its manual request within
it, so on the reference unit, during a dehumidify run:

* raising `number.hrds_fan_min_speed_dehumidify` above the current speed
  raised the fan to the new minimum within a minute (50 → 55 %);
* lowering the minimum again did **not** slow the fan; it stays at its speed
  until the request ends, and the next run starts at the minimum;
* lowering the **maximum** below the current speed should slow it, but that
  is not tested yet.

Each change is a write to the unit's EEPROM, so do not drive the band from a
control loop. The cooling band (`_cooling`) is expected to work the same way
during an integration request; untested. The open tests:
[`plans/fan-speed-tests.md`](plans/fan-speed-tests.md).

## Entity reference

Every entity, with its register and what it shows, is in the
**[entity reference](doc/entity-reference.md)** (English). It is organised like
the devices the integration creates:

* **[HRDS+](doc/entity-reference.md#main-device-hrds)**: the operating surface
  (climate, fan, request switches, readings and alarms), with its
  *Configuration* and *Diagnostic* sections.
* **[HRDS+ setup](doc/entity-reference.md#setup-device-hrds-setup)**: the
  one-time checklist (setup check, Modbus enables, probe and wiring facts).
* **[HRDS+ installer](doc/entity-reference.md#installer-device-hrds-installer)**:
  the opt-in installer menu, about 240 parameters.

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
temperatures keep working. The `temp_probe_ok` / `humidity_probe_ok` sensors
show **unknown** too: with no probe allocated there is nothing for alarms
AL28/AL34 to check.

See [UNIT_BEHAVIOUR §8](doc/references/UNIT_BEHAVIOUR.md#8-display-and-probe-configurations)
for what each display/probe configuration does, and
[`doc/references/MODBUS_REGISTERS.md` §14](doc/references/MODBUS_REGISTERS.md#14-probes-inputs-and-probe-source)
for the inputs, probe types and HA00 values.

## Requirements

* **Home Assistant 2026.10 or newer.**
* `pymodbus` 3.13.1 or newer (a minimum version in the manifest, as hassfest
  requires for packages Home Assistant itself ships; HA 2026.10 ships 3.13.1).

### Availability

Entities go **`unavailable`** when a poll fails, rather than continuing to show
the last good reading. If you drive this integration from templates or
automations, gate them on `has_value()` — a dehumidifier that acts on a
three-day-old humidity reading is worse than one that does nothing.

Writes that the unit rejects now raise an error instead of silently succeeding.
In an automation a failed service call **aborts the remaining steps**, so if you
issue several writes in sequence, either put the critical one first or mark the
rest `continue_on_error: true`.

## Disclaimer

Use at your own risk. This is beta software, and many of the writable registers
change installer-level behaviour. Only change settings you understand.

## Reporting issues

**Issues without the diagnostic output cannot be supported.** Whatever the
problem (a wrong value, a refused write, a unit that does not start), the
read-only diagnostic script shows what the unit reports and what the
integration would do, and without it there is nothing to go on.

It only reads (Modbus function codes 03, 04 and 43) and never writes to the
unit. It needs a copy of this repository (the HACS download contains only the
component) and `pymodbus`:

```
git clone https://github.com/mikopp/homeassistant-innova-hrds.git
cd homeassistant-innova-hrds
pip install 'pymodbus>=3.13.1'
python3 tests/diagnose_hrds.py <gateway-ip> --json diag.json
```

Add `--port N` / `--unit N` if your gateway does not use port 502 / slave id 1,
and `--display` if a CNU2 display is fitted. **Attach `diag.json` to the issue.**
The file contains the gateway address in its `host` field: replace it before
posting.

Please also say which unit it is (HRDS+ 30 or 50, `R` or non-`R`, display or
headless, which probes are wired), the Home Assistant and integration versions,
the `issues` of `sensor.setup_check`, and the relevant part of the Home
Assistant log. The issue form asks for all of this.
[Open an issue](https://github.com/mikopp/homeassistant-innova-hrds/issues/new/choose).

## Road to 1.0

1.0 is for when the open points in [`plans/todo.md`](plans/todo.md) have been
checked on real hardware (fan behaviour, the minimum room temperature
interlock without a probe, mode combinations) and the integration has run on at
least one other kind of unit (a display, external probes, a different
size/variant). Until then the 0.x releases keep the beta label above.

## Design decisions

Why the integration behaves as it does (what it never writes, which requests
it refuses, what the climate modes mean) is recorded one decision per file in
[`doc/adr/`](doc/adr/README.md).

## Credits

Architecture closely follows the
[`ha_comfoconnectpro`](https://github.com/hstrohmaier/ha_comfoconnectpro)
integration. Documentation © Innova / hej.luft (see `doc/references/`).
