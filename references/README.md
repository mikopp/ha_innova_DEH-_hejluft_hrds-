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
expectation is that the unit's compressor still runs, but airflow comes from
the central MVHR passive inflow rather than the unit's own fan.
*This has not yet been verified on physical hardware* — see `plans/todo.md`
for the specific checks needed. In particular, it is unknown whether the unit
internally clamps the manual speed up to `MinSpeedFan_Dehum` (1853) /
`MinSpeedFan_Integ` (1852) even when 0 is written to 1614.

Fan mode is **independent of HVAC mode** — changing Dry ↔ Cool does not reset
the fan mode; switching to Off also turns off the unit via `Status_OnOff_byBMS`
(1105) but does not change the fan speed register.

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
