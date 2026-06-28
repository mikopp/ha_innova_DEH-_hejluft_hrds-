# References — HRDS+ / Innova DEH+

This directory holds the manufacturer documentation for the **hej.luft HRDS+**
air-dehumidification module for residential ventilation systems (sold by the
original manufacturer as the **Innova DEH+**), plus a distilled register
reference for building the Home Assistant integration in this repository.

## Files

| File | What it is |
|------|------------|
| [HRDS+_Modbus_RTU_RS485_DE.pdf](HRDS+_Modbus_RTU_RS485_DE.pdf) | **Modbus RTU/RS-485 connection & register manual** (German). The source of truth for all register addresses. |
| [HRDS+_Technisches_Handbuch_DE.pdf](HRDS+_Technisches_Handbuch_DE.pdf) | Technical manual — installation, operation, maintenance, technical data (German, 87 pp). |
| [HRDS+_Benutzerhandbuch_DE.pdf](HRDS+_Benutzerhandbuch_DE.pdf) | End-user manual (German, 12 pp). |
| [MODBUS_REGISTERS.md](MODBUS_REGISTERS.md) | **Distilled, machine-readable register map** extracted from the Modbus PDF. Start here for implementation. |

## What the unit is

The HRDS+ is an isothermal air dehumidifier for radiant-panel / residential
ventilation systems. Depending on configuration (`PG01_MachineType`) it runs as
a pure dehumidifier or as a dehumidifier with integrated ventilation (VMC). It
can additionally provide **active cooling** ("integration") in summer using its
refrigerant compressor and a chilled-water circuit, and it follows a
**Summer/Winter** season model.

The control board communicates via **Modbus RTU over RS-485** (Modicon Modbus,
9600 8N1 by default, slave address 1). A Modbus-TCP gateway, where present,
exposes the identical register model over TCP port 502 — which is what this
Home Assistant integration targets.

## What you can do over Modbus (capability summary)

All of the following are covered in detail, with exact register addresses, in
[`MODBUS_REGISTERS.md`](./MODBUS_REGISTERS.md). Every "by BMS" command requires
its enable register to be set first (§3 of that file) — otherwise the unit
silently ignores writes.

* **Turn the unit on/off** — `Status_OnOff_byBMS` (1105), feedback `sm_UnitStatus`
  (1104). Requires `PH02` (1778) = 1.
* **Turn dehumidification on/off** — `Status_Dehum_byBMS` (1140), feedback
  `DehumRequest` (1121). Requires `PH28` (1870) = 1.
* **Turn active cooling on/off** — `Status_Integ_byBMS` (1139), feedback via
  `CmpStatus` (1122). Requires `PH27` (1869) = 1 and integration enabled.
* **Set the air-flow / fan speed** — per-mode min/max bands
  (`1853/1647` dehumidify, `1852/1646` cooling) and manual setpoint (1614).
  **Percentages are ×100** (40 % → 4000). Actual output `outAO_SupplyFan` (639),
  RPM (1117). Fan-integration active flag `FanIntegration_Request` (1112, R/O).
* **Set the humidity target** — `PU01_Humidity_Setpoint` (1586), %RH.
* **Set the temperature target** — summer (1584) / winter (1585) setpoints, °C ×10.
* **Select season / operating mode** — `Mode_OperatingMode` (1583, R/O feedback),
  change via `DI4_Configuration` (1825).
* **Read humidity & temperature sensors** — room temp (499), room humidity (505),
  outdoor (500), water (501), discharge/supply (503), evaporator (511). Temps ×10.
* **Know whether the unit is on** — `sm_UnitStatus` (1104): `5` = ON, else OFF
  with a specific cause.
* **Read errors / status** — cumulative alarm flag `OR_Alarms` (1103) plus the
  per-bit alarm bitmaps `PackedAlarm_1/2/3` (768/769/770); reset via the
  `BMS_ALxx` registers. Component status: `SupplyFan_Status` (1119),
  `CmpStatus` (1122).
* **Other** — full weekly scheduler, probe calibration, filter running-hours and
  alarm thresholds, and complete hardware I/O configuration are all exposed; see
  the "FULL MODBUS REGISTER LIST" in the PDF (§6).

## Airflow: passive flow, fan integration, and active cooling (technical)

The word *integration* is overloaded in the manufacturer's documentation, which
makes the airflow behaviour easy to misread. There are **three** distinct
things, exposed by three different register groups. The full register-level
treatment — with the exact addresses, the detection logic and the
reproduce-over-Modbus recipe — lives in
[`MODBUS_REGISTERS.md` §13](./MODBUS_REGISTERS.md#13-airflow-passive-flow-fan-integration-and-active-cooling).
A short summary:

* **Passive airflow** — the unit's own supply fan is **off**, but the central
  MVHR upstream still pushes air through the inflow pipe. There is **no
  dedicated register** for this; it is inferred from `SupplyFan_Status` (1119) =
  OFF while `sm_UnitStatus` (1104) = ON. The HRDS+ cannot see the upstream MVHR's
  flow, so it cannot report a passive flow rate. Source:
  `HRDS+_Technisches_Handbuch_DE.pdf`, § Lüfterregelung / Funktionsweise.

  **Architectural proof:** the non-`R` variant (no recirc fan fitted) has no
  supply fan at all, yet the compressor runs normally for dehumidification and
  cooling on passive MVHR flow alone. This confirms that passive airflow is
  sufficient for compressor operation by design — it is not a special or
  unsupported state.
* **Fan integration** — the unit's **own fan runs** to blend the central-MVHR
  inflow air with recirculated room air across the coil. Exposed by the new
  read-only `FanIntegration_Request` (1112) → `fan_integration_active` binary
  sensor, plus `SupplyFan_Status` (1119), output `outAO_SupplyFan` (639) and RPM
  (1117).
* **Active cooling** — the manufacturer *also* calls this "integration"
  (`Status_Integ_byBMS`, 1139): the compressor/chilled-water circuit actively
  cools the supply air in summer (parameter `PG02_EnableIntegration`, 1798). This
  is the **active-cooling** request, unrelated to the fan's blending function
  above, and is mapped to the `active_cooling` switch.

**Dehumidify with the fan on but active cooling off** is a normal state:
`Status_Dehum_byBMS` (1140) = 1 runs the compressor to condense moisture, which
needs airflow, so the supply fan runs on the **dehumidify fan band**
(`MinSpeedFan_Dehum` 1853 / `MaxSpeedFan_Dehum` 1647) while
`Status_Integ_byBMS` (1139) stays 0. `CmpStatus` (1122) reads ON because the
compressor serves dehumidification — *not* active cooling. The full Modbus
recipe and the inverse coupling parameters (`PU05_ForceDehumInCooling` 1692,
`PU02_EnableWinterDehum` 1689) are in
[`MODBUS_REGISTERS.md` §13.4](./MODBUS_REGISTERS.md#134-dehumidify-with-the-fan-running-but-active-cooling-off).

## Fan mode — how the HA integration controls the supply fan

The HA climate entity exposes four fan modes, all written to
`PM20_SupplyFan_Manual` (reg 1614, holding, ×0.01 scaling):

| HA fan mode | Raw value written | Actual fan speed | Use when |
|-------------|-------------------|------------------|----------|
| `off`       | 0 (0 %)           | Fan stopped       | You want passive airflow from the central MVHR only |
| `low`       | 3000 (30 %)       | ~30 % output     | Light supplemental airflow |
| `medium`    | 5500 (55 %)       | ~55 % output     | Normal operation |
| `high`      | 8500 (85 %)       | ~85 % output     | Maximum airflow / fast drying |

Read-back: the integration reads `outAO_SupplyFan` (639, ×0.01 %) and maps it
to the nearest preset using midpoint thresholds (42.5 % → low/medium boundary,
70.0 % → medium/high boundary). If `SupplyFan_Status` (1119) is `1=OFF` or
`0=Disabled`, fan mode is reported as "off" regardless of the output value.

**Fan mode "off" while HVAC mode is Dry or Cool** relies on the unit honouring
a 0 % manual setpoint while dehumidification/cooling is requested. The
compressor continues to run, with airflow from the central MVHR passive inflow
only.

This pattern is **architecturally correct**: the non-`R` variant (no recirc
fan) always operates exactly this way — compressor dehumidifies and cools on
MVHR passive flow alone. The concept is therefore confirmed by design, not just
by assumption.

**Open question for the `R` variant:** when dehumidify is active and
`fan_manual_speed` is set to 0 %, does the firmware respect the 0 % or clamp
up to `MinSpeedFan_Dehum` (1853 / PF28)? Verify by writing 0 to register 1614
while dehumidify is active, then reading `outAO_SupplyFan` (639). The firmware
is confirmed to allow PF28 = 0 (configurable minimum), but whether a manual
override of 0 is honoured during active DEU is unverified. The compressor will
auto-protect via AL11 if passive airflow is insufficient.

Fan mode is **independent of HVAC mode** — changing Dry ↔ Cool does not reset
the fan mode; switching to Off also turns off the unit via `Status_OnOff_byBMS`
(1105) but does not change the fan speed register.

## Two HRDS+ variants — 30 vs 50

The unit comes in two airflow sizes, identified by the **second field of the
product code** on the type plate (Technisches Handbuch §2.4, p.9):
`HRDS + ` **`30`** ` H R K DC`.

| Code field | Meaning |
|-----------|---------|
| `HRDS+` | Inverter (variable-speed compressor) variant |
| **`30` / `50`** | **Total airflow class: `30` → up to 300 m³/h, `50` → up to 500 m³/h** |
| `H` | Horizontal install |
| `R` | **with recirculation (Umluft) fan + damper** — only this variant can blend room air; a non-`R` build has no recirc fan |
| `K` | Electronics revision K |
| `DC` | Dehumidify **and** cooling |

There is also a build **without recirculation** ("Version ohne Umluftumwälzung",
lighter — see weights below); it has no `outAO_SupplyFan` blending and cannot
top up airflow with room air.

### Detecting the variant over Modbus

The product code is on the type plate only — there is no hardware-ID register.
The table below lists the best Modbus proxies, exposed as HA sensors:

| Variant axis | Best Modbus indicator | Register | HA entity |
|---|---|---|---|
| **Airflow size (30 vs 50)** | Not readable — set manually in integration setup | — | config `model` field |
| **Recirculation fan present (`R` / non-`R`)** | `PG01_MachineType` (1797): `1` = VMC (has recirc fan), `0` = dehumidifier only | FC 03, R/W configured as R/O | `binary_sensor.has_recirculation` |
| **Recirculation damper state** | `outDO_RecircDamper` (1134): `off` = damper closed (room-air duct blocked, MVHR passive flow only), `on` = damper open (room air drawn in and blended), `disabled` = no damper output wired (non-`R` build, no recirculation assembly) | FC 04, R/O | `sensor.recirculation_damper` |
| **Active cooling present (`DC` / `D`)** | `PG02_EnableIntegration` (1798): `1` = cooling enabled on this unit | FC 03, R/W configured as R/O | `binary_sensor.active_cooling_available` |

**What the damper is:** a motorised flap in the room-air return duct. When
recirculation is active the control board opens the damper so the fan can draw
room air across the coil and blend it with the MVHR supply inflow. When idle
the damper closes, sealing the return duct, and only passive MVHR airflow
passes through. In German: *Umluft-Klappe* (Umluft = return/recirculation air,
Klappe = flap). The `outDO_RecircDamper` register reflects the board's digital
output to the damper motor.

**Caveats:** `PG01` and `PG02` are configuration parameters written by the
installer, not hard-wired hardware IDs. A unit with cooling hardware but
`PG02 = 0` (disabled by installer) reads as `active_cooling_available = OFF`.
The damper sensor (`outDO_RecircDamper`) is the most reliable hardware signal:
`disabled` means the control board sees no damper output wired up, i.e. the
unit physically lacks the recirculation assembly.

## Technical data (airflow, capacity, power)

From the Technisches Handbuch §10, p.77 ("Leistungsdaten Luftaufbereitung" /
"Elektrische Daten"). The two columns are the **30** and **50** variants.

| Spec | HRDS+ 30 | HRDS+ 50 |
|------|---------:|---------:|
| **Nominal total airflow (supply + recirc)** | **300 m³/h** | **500 m³/h** |
| External share (supply from the MVHR) | 0–300 m³/h | 0–500 m³/h |
| **Recirculation share (room air via own fan)** | **130–300 m³/h** | **190–500 m³/h** |
| Register-pack pressure drop @ nominal | 31 kPa | 38 kPa |
| Usable dehumidification capacity ¹ | 56 L/24h | 89 L/24h |
| Total cooling capacity ¹ | 2.59 kW | 3.95 kW |
| Compressor frequency range | 23–63 Hz | 23–78 Hz |
| **Max. electrical power (operating)** | **820 W** | **1130 W** |
| — compressor nominal | 690 W | 950 W |
| — **recirc fan nominal** | **120 W** | **170 W** |
| Sound pressure @ 3 m | 39.5 dB(A) | 40.8 dB(A) |
| Weight (with recirc / without) | 46 / 43 kg | 57 / 54 kg |

¹ At nominal airflow and the reference conditions footnoted in the handbook.

The 130–300 m³/h / 190–500 m³/h band in the table is the **tested operating
range** from the performance spec — not a firmware-enforced floor. The firmware
minimum during dehumidification is `PF28` (German handbook: "Minimale
Geschwindigkeit Zuluftventilator bei Entfeuchtung"), which **defaults to 50 %
but is configurable down to 0 %**. The equivalent for integration (cooling) is
`PF27`, same defaults. In practice the unit's refrigerant circuit protects itself
via **AL11** (compressor low-pressure / frost-thermostat: auto-stops the compressor
if evaporator icing indicates insufficient airflow) and **AL12** (high-pressure
stop). Passive MVHR airflow is sufficient for compressor operation — proven by the
non-`R` variant which has no fan and always runs on passive flow.

The **total** flow (supply + recirc) **must not exceed the nominal** (300 / 500)
— exceeding it costs efficiency, raises noise, and requires larger supply-duct
sizing (handbook p.24).

### Dehumidification capacity vs. airflow

More airflow over the coil = faster drying, with clear diminishing returns near
the nominal flow. From the per-flow performance tables (handbook p.78 / p.79,
reference inlet conditions):

| Airflow | HRDS+ 30 dehum. | HRDS+ 50 dehum. |
|--------:|----------------:|----------------:|
| 150 m³/h | 31.2 L/d | — |
| 200 m³/h | 41.1 L/d | 42.6 L/d |
| 250 m³/h | 50.7 L/d | — |
| 300 m³/h | 54.4 L/d | 62.4 L/d |
| 400 m³/h | — | 81.1 L/d |
| 500 m³/h | — | 83.2 L/d |

## Translating fan speed (% / RPM) to airflow (m³/h)

The unit exposes two fan-speed readouts but **no register that reports airflow
directly** — it cannot measure its own m³/h:

| Reading | Register | Entity | Scale |
|---------|----------|--------|-------|
| Supply-fan analog **output %** | `outAO_SupplyFan` (639) | `sensor.supply_fan_output` | ×0.01 → % |
| Supply-fan **RPM** | (1117) | `sensor.supply_fan_rpm` | raw rpm |
| Manual fan **setpoint %** | `PM20_SupplyFan_Manual` (1614) | `number.fan_manual_speed` | ×0.01 → % (write) |

The performance curves in the handbook (§10.3, p.80–81) are **pressure-vs-flow
system curves**, not an RPM-vs-flow table, so there is no published direct
RPM→m³/h conversion. Estimate it with the **fan affinity law**: for a
centrifugal EC fan on a fixed duct (constant static pressure), **flow is
proportional to fan speed** — `Q ∝ N`. Hence:

```
m³/h  ≈  (RPM / RPM_max) × Q_max
```

- `Q_max` = the variant's recirc nominal max: **300** (HRDS+30) / **500** (HRDS+50).
- `RPM_max` = the RPM read back at 100 % output — **not published, calibrate once**:
  drive `fan_manual_speed` to 100 %, let it settle, read `sensor.supply_fan_rpm`.

Equivalently, via the analog output % (the same curve, already normalised):

```
m³/h  ≈  (output% / 100) × Q_max
```

with the practical note that the fan output % where recirculation actually begins
corresponds to `PF28` (default 50 %, configurable to 0 %): below that the fan
is simply OFF (0 m³/h passive MVHR flow only), not a proportional fraction. So
a more faithful map across the running range is:

```
m³/h  ≈  Q_min + (output% − band_min%) / (100 − band_min%) × (Q_max − Q_min)
         clamped to [Q_min, Q_max];   Q_min = 130 (30) / 190 (50)
```

**Accuracy caveats:** the affinity law holds only at constant duct resistance.
Higher static pressure (filters loading, longer/narrower ducts) means the same
RPM moves *less* air — see the available-pressure curves on p.81. For better
accuracy do a **two-point calibration** (read RPM/output% at two known balanced
flows from the MVHR commissioning report) and fit a line, rather than assuming a
single `Q_max`. The estimate is open-loop either way; treat derived m³/h as
indicative, not metered.

## Probes: built-in, display, and external sensors

Understanding which sensors are physically present and which need to be
installed is essential for setting up the integration. Full detail is in
[`MODBUS_REGISTERS.md` §14](./MODBUS_REGISTERS.md#14-probes-built-in-display-and-external-sensors).
Short summary:

### Always present (factory-wired inside the unit)

| Sensor | Register | What it does |
|--------|----------|-------------|
| Evaporator temperature | 511 (`AI_Tevaporation`) | Compressor modulation — always active |
| Water circuit temperature | 501 (`AI_Twater`) | Over-temperature / antifreeze protection — always active |

### Need a display or external probe (not present by default)

| Sensor | Register | Probe type | Used for |
|--------|----------|-----------|---------|
| Room temperature | 499 (`AI_TreturnRoom`) | NTC 10 kΩ B3435, or CNU2 display | Automatic cooling/heating trigger; alarm-gating |
| Room humidity | 505 (`AI_HretRoom`) | 0–10 V or 4–20 mA humidity transmitter, or CNU2 display | Automatic dehumidify trigger |
| Outdoor temperature | 500 (`AI_Toutdoor`) | NTC 10 kΩ B3435, IP65 | Only used for Free-Cooling/Heating (PG03); otherwise display-only |
| Exhaust temperature | 502 (`AI_Texhaust`) | NTC 10 kΩ B3435 | Display / monitoring only |
| Discharge temperature | 503 (`AI_Tdischarge`) | NTC 10 kΩ B3435 | Display / monitoring only |

### Configuring the probe source — HA00 (register 1803)

The **HA00** parameter (holding register 1803) tells the unit which source to
use for room T/H. The factory default is `6` (CNU2 display with both sensors).

| Scenario | Set HA00 to |
|---------|------------|
| Wired CNU2 display present (T + H) | `6` (default) |
| Wired CNU2 display present (T only) | `5` |
| External NTC (T) + humidity transmitter (H) on AI2/AI3 | `0` |
| No display, no external probes (fully manual BMS mode) | `0` + set PH01 = 0 |

The HA integration exposes HA00 as a `select` entity (`T/H probe source`).

### Probe fault alarms

When the configured probe source is absent, the unit raises:
* **AL28** — room temperature probe fault (stops automatic cooling/heating)
* **AL34** — room humidity probe fault (stops automatic dehumidification)

The HA integration decodes these from the packed alarm registers (769/770) and
exposes them as `temp_probe_ok` / `humidity_probe_ok` binary sensors. When
either is OFF, the climate entity suppresses the corresponding current value.

## How this maps onto the Home Assistant integration

The integration models the unit as a **climate entity** plus supporting
sensors/numbers/switches:

* `current_temperature` ← room temperature (499); `current_humidity` ← room
  humidity (505).
* `hvac_action` ← derived from `sm_UnitStatus` / `DehumRequest` / `CmpStatus`
  (OFF / IDLE / DRYING / COOLING / FAN).
* `hvac_mode` ← used to drive the operating mode: OFF, DRY (dehumidify), COOL
  (active cooling). Writing a mode toggles the on/off + dehum + integration
  request registers.
* `target_humidity` ← `PU01` (1586); `target_temperature` ← season setpoint.

Two device traits matter for the implementation and are easy to get wrong:

1. **No coils / discrete inputs exist** — model everything as input registers
   (read-only) or holding registers (read-write). 0/1 flags are analog.
2. **The address space is wide and sparse**, so the polling hub must read in
   contiguous ≤125-register chunks, not one block.

See [`MODBUS_REGISTERS.md` §12](./MODBUS_REGISTERS.md#12-notes-for-the-ha-integration)
for the full implementation notes.
