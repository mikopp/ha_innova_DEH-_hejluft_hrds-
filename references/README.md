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
[`MODBUS_REGISTERS.md` §13.3](./MODBUS_REGISTERS.md#133-dehumidify-with-the-fan-running-but-active-cooling-off).

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
