# HRDS+ / Innova DEH+ — Modbus Register Definition

Machine-readable extraction of the Modbus register map for the **hej.luft HRDS+**
air-dehumidification module (OEM: **Innova DEH+**), taken from
`references/HRDS+_Modbus_RTU_RS485_DE.pdf` (Stand: Mai 2026).

This file is the authoritative register reference for the Home Assistant
integration in this repository. It is written to be read by both humans and
agents. If a value here disagrees with the PDF, the PDF wins — please fix this
file.

---

## 1. Transport & framing

The HRDS+ control board speaks **Modicon Modbus RTU over RS-485**. A
Modbus-TCP gateway (if fitted) exposes the same register model over TCP/502.

Factory serial defaults:

| Setting       | Default | Register        |
|---------------|---------|-----------------|
| Modbus address| `1`     | `0x06ED` (1773) |
| Baud rate     | `9600`  | `0x06EE` (1774) — `0=1200,1=2400,2=4800,3=9600,4=19200,5=28800,6=38400,7=57600` |
| Parity        | `None`  | `0x06EF` (1775) — `0=None,1=Odd,2=Even` |
| Stop bits     | `1`     | `0x06F0` (1776) — `0=1 stop bit,1=2 stop bits` |

> The serial-port parameters above can **only** be changed from the wired
> remote (Installer menu → MODBUS, password `2`) or the service software — not
> over Modbus itself. Power-cycle the unit after changing them.

## 2. Addressing & data-type conventions

* **`Addr HEX` / `Addr DEC`** in the tables below are the *direct* protocol
  addresses. Use them as-is with pymodbus (`address=1105` for `0x0451`); do
  **not** apply a `-1` offset.
* All registers are **16-bit, big-endian**.
* **Function codes** (this is how Read/Write is split):
  * **`R/O` → FC 04** "Read Input Registers".
  * **`R/W` → FC 03** "Read Holding Registers" (read) and FC 06 / FC 16 (write).
* **Everything is analog.** The manufacturer explicitly states that even 0/1
  status flags are analog registers — **there are no Modbus coils or discrete
  inputs** on this device.
* **Signed vs unsigned:** registers whose `Min` is negative (e.g. temperatures
  with `Min -3276.8`) are **INT16**; the rest are **UINT16**.
* **Scaling** (derived from the `Min/Max`/`Default` columns and the in-text
  notes):
  * Temperatures: value ×0.1 °C (e.g. raw `245` → `24.5 °C`). Range shown as
    `-3276.8 … 3276.7` ⇒ INT16 ÷10.
  * Setpoints (`SEtC`, `SEtH`, `Actual_Setpoint`): ×0.1 °C.
  * **Fan speeds / analog-out percentages: value ×0.01 %** — *write two implied
    decimals*. e.g. `40 %` is the raw value `4000`; `85 %` is `8500`.
  * Humidity (`PU01`, `AI_HretRoom`, warning setpoint): integer **%RH**, no scale.
  * Working hours (`PM00`/`PM01`…): ×0.1 h (raw `1500` → `150.0` → 1500 h, per
    the "h ×10" note — read the PDF §Filterverschmutzung carefully).

## 3. Function enables — **set these first**

Modbus write commands are **ignored** unless the matching "by BMS" function is
enabled. An `OFF` command always wins over any `ON` command, regardless of
source (contact, display, Modbus).

| Addr HEX | Addr DEC | Name                    | R/W | Description |
|----------|----------|-------------------------|-----|-------------|
| `0x06F2` | 1778 | `Enable_OnOffByBMS`       | R/W | **PH02** — set `1` to allow On/Off over Modbus (`0=Disabled,1=Enabled`). |
| `0x074D` | 1869 | `Enable_IntegByBMS`       | R/W | **PH27** — set `1` to allow the integration / active-cooling request over Modbus. |
| `0x074E` | 1870 | `Enable_DehumByBMS`       | R/W | **PH28** — set `1` to allow the dehumidify request over Modbus. |
| `0x06F1` | 1777 | `Enable_OnOffByDisplay`   | R/W | **PH01** — set `0` if no wired display is present. |
| `0x070B` | 1803 | `T/H Probe Source` (HA00) | R/W | Source for temp/humidity probes: `0=None`, `6=CNU2 display`. Set `0` if no display. |

## 4. Operating commands (control)

| Addr HEX | Addr DEC | Name                  | R/W | Values / meaning |
|----------|----------|-----------------------|-----|------------------|
| `0x0451` | 1105 | `Status_OnOff_byBMS`     | R/W | Unit On/Off request: `0=Off`, `1=On`. (Requires PH02=1.) |
| `0x0474` | 1140 | `Status_Dehum_byBMS`     | R/W | Dehumidify request: `0=No`, `1=Yes`. (Requires PH28=1.) |
| `0x0473` | 1139 | `Status_Integ_byBMS`     | R/W | Integration / **active-cooling** request: `0=No`, `1=Yes`. (Requires PH27=1.) |
| `0x062F` | 1583 | `Mode_OperatingMode`     | R/O | Season: `0=Summer`, `1=Winter`, `2=Auto`. Use as feedback. |
| `0x0721` | 1825 | `DI4_Configuration`(HB04)| R/W | Season change w/o display: `4=Summer (DI4 N/O)`, `3=Winter (DI4 N/C)`. **Only 3 or 4 are valid — other values raise alarm AL25.** |
| `0x0756` | 1878 | `PriorityChangeMode_Display` (PC11) | R/W | Who owns season change: `0=Display`, `1=DI/Digital-IN`. |

> **Active cooling** in this product = the *integration* function (`0x0473`),
> which engages the compressor/chilled-water circuit to actively cool supply
> air in summer mode. Plain dehumidification (`0x0474`) removes moisture without
> the active-cooling integration.

## 5. Setpoints

| Addr HEX | Addr DEC | Name                    | R/W | Default | Min | Max | Unit/scale |
|----------|----------|-------------------------|-----|---------|-----|-----|------------|
| `0x0630` | 1584 | `SEtC_SummerSetpoint`      | R/W | 24.0 | 15.0 | 158.0 | °C ×0.1 |
| `0x0631` | 1585 | `SEtH_WinterSetpoint`      | R/W | 20.0 | 15.0 | 158.0 | °C ×0.1 |
| `0x0632` | 1586 | `PU01_Humidity_Setpoint`   | R/W | 55   | 0    | 100   | %RH |
| `0x0764` | 1892 | `PH29_Min_Humidity_Setpoint` | R/W | — | 0 | 100 | %RH lower clamp for PU01 |
| `0x0765` | 1893 | `PH30_Max_Humidity_Setpoint` | R/W | — | 0 | 100 | %RH upper clamp for PU01 |
| `0x06C7` | 1735 | `Setpoint_HighHumWarning` (PA19) | R/W | 70 | 0 | 100 | %RH — triggers high-humidity warning AL02 |

> Setpoints only take effect when a display is present **or** external probes
> are connected.

## 6. Fan speed

Fan-speed registers are percentages with **two implied decimals** (write `4000`
for 40 %). Min/Max apply to the modulation band used in each mode.

| Addr HEX | Addr DEC | Name                 | R/W | Default | Range | Meaning |
|----------|----------|----------------------|-----|---------|-------|---------|
| `0x073D` | 1853 | `MinSpeedFan_Dehum` (PF28) | R/W | 50.00 | 0–100 | Supply-fan min speed in dehumidify |
| `0x066F` | 1647 | `MaxSpeedFan_Dehum` (PF10) | R/W | 85.00 | 0–100 | Supply-fan max speed in dehumidify |
| `0x073C` | 1852 | `MinSpeedFan_Integ` (PF27) | R/W | 50.00 | 0–100 | Supply-fan min speed in integration (cooling) |
| `0x066E` | 1646 | `MaxSpeedFan_Integ` (PF09) | R/W | 85.00 | 0–100 | Supply-fan max speed in integration (cooling) |
| `0x064E` | 1614 | `PM20_SupplyFan_Manual`    | R/W | — | 0–100 | Manual supply-fan setpoint |
| `0x045A` | 1114 | `SupplyFan_ManualRequest`  | R/O | — | 0–100 | Current manual fan request |
| `0x045C` | 1116 | `SupplyFan_RemoteRequest`  | R/O | — | 0–100 | Current potentiometer fan request |
| `0x027F` | 639  | `outAO_SupplyFan`          | R/O | — | 0–100 | Actual supply-fan analog output % |
| `0x045D` | 1117 | `actRPMsupplyFan`          | R/O | — | 0–65535 | Supply-fan actual RPM |

## 7. Sensors (read-only, FC 04)

| Addr HEX | Addr DEC | Name              | Type | Scale | Description |
|----------|----------|-------------------|------|-------|-------------|
| `0x01F3` | 499 | `AI_TreturnRoom`     | INT16 | ×0.1 °C | Return/room air temperature (needs display or external probe) |
| `0x01F4` | 500 | `AI_Toutdoor`        | INT16 | ×0.1 °C | Outdoor air temperature |
| `0x01F5` | 501 | `AI_Twater`          | INT16 | ×0.1 °C | Water-circuit temperature |
| `0x01F6` | 502 | `AI_Texhaust`        | INT16 | ×0.1 °C | Exhaust air temperature |
| `0x01F7` | 503 | `AI_Tdischarge`      | INT16 | ×0.1 °C | Discharge (supply) air temperature |
| `0x01F9` | 505 | `AI_HretRoom`        | INT16 | %RH | Return/room relative humidity (needs display or external probe) |
| `0x01FA` | 506 | `AI_AirQuality`      | INT16 | ppm/raw | Air-quality probe |
| `0x01FF` | 511 | `AI_Tevaporation`    | INT16 | ×0.1 °C | Evaporator temperature (inverter-compressor version only) |
| `0x0457` | 1111| `Actual_Setpoint`    | INT16 | ×0.1 °C | Active room setpoint in use |

## 8. Unit & component status (read-only, FC 04)

| Addr HEX | Addr DEC | Name              | Values |
|----------|----------|-------------------|--------|
| `0x0450` | 1104 | `sm_UnitStatus`      | `0=OFF by display`, `1=OFF by DI`, `2=OFF by BMS`, `3=OFF by scheduler`, `4=OFF by RTC`, `5=ON` |
| `0x0456` | 1110 | `ModeStatus`         | `0=Summer manual`, `1=Winter manual`, `2=Summer auto`, `3=Winter auto`, `4=Summer DI`, `5=Winter DI` |
| `0x0458` | 1112 | `FanIntegration_Request` | `0=No`, `1=Yes` — the **fan-integration** function is currently active, i.e. the supply fan is running to integrate (mix) the central-MVHR inflow air with room air. Set whenever the fan runs for ventilation/integration, independent of whether active cooling (`Status_Integ_byBMS`, 1139) is requested. |
| `0x045F` | 1119 | `SupplyFan_Status`   | `0=Disable`, `1=OFF`, `2=Wait ON`, `3=ON`, `4=Wait OFF`, `5=Alarm` |
| `0x0461` | 1121 | `DehumRequest`       | `0=No`, `1=Yes` — dehumidification currently requested |
| `0x0462` | 1122 | `CmpStatus`          | `0=Disable`, `1=Alarm`, `2=Manual`, `3=Wait ON`, `4=ON`, `5=Wait OFF`, `6=OFF` — compressor (active cooling/dehum) |
| `0x046E` | 1134 | `outDO_RecircDamper` | `0=OFF`, `1=ON`, `2=Disable` |
| `0x027F` | 639  | `outAO_SupplyFan`    | Supply-fan output % (×0.01) |
| `0x0281` | 641  | `outAO_Cmp`          | Compressor output % (×0.01) |
| `0x044F` | 1103 | `OR_Alarms`          | `0/1` cumulative "any alarm active" flag |

### Packed digital I/O status (bit-fields, R/O)

The device packs digital inputs/outputs into 16-bit registers using **2 bits
per signal** (`bitN..bitN+1`); a non-zero pair means active.

| Addr HEX | Addr DEC | Name | Notable bits |
|----------|----------|------|--------------|
| `0x0180` | 384 | `Packed_DO1` | bit4-5=Compressor, bit8-9=Recirculation damper, bit12-13=Water condensation valve (`0=Integration,1=Dehumidify`) |
| `0x0181` | 385 | `Packed_DO2` | bit4-5=On/Off, bit6-7=Summer/Winter, bit8-9=Serious alarm, bit10-11=Light alarm, bit12-13=High humidity |
| `0x0101` | 257 | `Packed_logicDI1` | bit0-1=Remote on/off, bit2-3=Summer/Winter, bit4-5=Dehum request, bit6-7=Integration/thermo request |

## 9. Alarms

### 9.1 Active-alarm bitmaps (R/O, FC 04)

Each bit = one alarm code. Bit set ⇒ alarm active.

| Addr HEX | Addr DEC | Name | Bit → code |
|----------|----------|------|------------|
| `0x0300` | 768 | `PackedAlarm_1` | bit00=AL01 … bit15=AL16 |
| `0x0301` | 769 | `PackedAlarm_2` | bit00=AL17 … bit15=AL32 |
| `0x0302` | 770 | `PackedAlarm_3` | bit00=AL33, bit01=AL34, bit02=AL35, bit04=AL37, bit05=AL38, bit06=AL39 |

### 9.2 Alarm code reference

| Code | Description | Reset | Effect |
|------|-------------|-------|--------|
| AL02 | High humidity | Auto | Shuts everything off if PA57=1, else display-only |
| AL03 | High summer water temperature | Auto | Disables active cooling (integration); disables dehum if PU03=0 |
| AL04 | Low winter water temperature | Auto | Disables winter heating (integration) |
| AL11 | Compressor low-pressure / frost-thermostat | Auto (manual if >5×/h) | Stops compressor |
| AL12 | Compressor high-pressure switch | Auto (manual if >5×/h) | Stops compressor |
| AL16 | Water-circuit antifreeze | Auto | Stops fan |
| AL18 | Generic alarm | Manual | Shuts everything off |
| AL19 | Generic warning | Auto | Display only |
| AL22 | Dirty filters | Manual | Display only |
| AL25 | I/O configuration error | Auto | Shuts everything off |
| AL26 | RTC clock failed/disconnected | Auto | Disables scheduler |
| AL28 | Room/return temperature probe fault | Auto | Disables dependent control |
| AL29 | External temperature probe fault | Auto | Disables dependent control |
| AL30 | Water temperature probe fault | Auto | Disables dependent control |
| AL34 | Room/return humidity probe fault | Auto | Disables dependent control |
| AL36 | Fan potentiometer fault | Auto | Disables dependent control |
| AL39 | Evaporator temperature probe fault | Auto | Disables dependent control |

### 9.3 Alarm reset registers (R/W)

Write `1` to reset the corresponding alarm: `0x030B`=AL01, `0x030C`=AL02,
`0x0311` (785)=AL11, `0x0312` (786)=AL12, `0x0317` (791)=AL18, `0x0319`=AL21,
`0x031A`=AL26, … (full list `0x030B`–`0x031A`).
**Filter alarm AL22 is reset by writing `0` to `0x0644` (1604).**

## 10. Key configuration parameters (R/W) worth knowing

| Addr HEX | Addr DEC | Name | Meaning |
|----------|----------|------|---------|
| `0x0705` | 1797 | `PG01_MachineType` | `0=Only dehumidifier`, `1=Dehumidifier + VMC (ventilation)` |
| `0x0706` | 1798 | `PG02_EnableIntegration` | Enable the active-cooling integration function |
| `0x0699` | 1689 | `PU02_EnableWinterDehum` | `0=No`, `1=With water`, `2=Without water` |
| `0x069C` | 1692 | `PU05_ForceDehumInCooling` | Force dehumidify when cooling requested |
| `0x06F5` | 1781 | `PH05_TemperatureUM` | `0=°C`, `1=°F` |
| `0x0642` | 1602 | `PM00_Limit_FansHours` | Fan running-hours alarm limit (h ×10) |
| `0x0644` | 1604 | `PM01_SupplyFan_Hours` | Fan running-hours counter (write 0 to reset filter alarm AL22) |

---

## 11. Cookbook — common operations

> Requires the matching **PH02 / PH27 / PH28** enable register set to `1` first
> (see §3). All addresses are decimal Modbus PDU addresses.

**Turn the unit on / off**
1. One-time: write `1` to `1778` (PH02 Enable_OnOffByBMS).
2. On: write `1` to `1105`; Off: write `0` to `1105`.
3. Read back `1104` (`sm_UnitStatus`); `5` = ON.

**Turn dehumidification on / off**
1. One-time: write `1` to `1870` (PH28 Enable_DehumByBMS).
2. On: write `1` to `1140`; Off: write `0`.
3. Read back `1121` (`DehumRequest`) and `1122` (`CmpStatus`).

**Turn active cooling (integration) on / off**
1. One-time: write `1` to `1869` (PH27 Enable_IntegByBMS) and ensure
   `PG02_EnableIntegration` (1798) = 1, season = Summer.
2. On: write `1` to `1139`; Off: write `0`.
3. Compressor feedback via `1122` (`CmpStatus`, `4`=ON).

**Set the air-flow (fan) speed**
* Dehumidify-mode band: min `1853`, max `1647`. Cooling band: min `1852`,
  max `1646`. Manual: `1614`. Remember the **×100** encoding (`40 %` → `4000`).
* Actual output: `639` (`outAO_SupplyFan`, ×0.01 %), RPM: `1117`.

**Set the humidity target** — write %RH to `1586` (`PU01`), clamped by `1892`/`1893`.

**Set the temperature target** — summer `1584`, winter `1585` (°C ×0.1).

**Read sensors** — room temp `499` (×0.1 °C), room humidity `505` (%RH),
outdoor temp `500`, water temp `501`, supply/discharge temp `503`.

**Is the unit on?** — read `1104`; `5` = ON, anything `0–4` = a specific OFF cause.

**Check errors / status** — read `1103` (any-alarm flag) then `768/769/770`
(per-bit alarm codes); decode with §9.2.

---

## 12. Notes for the HA integration

* **No coils / discrete inputs.** Model read-only entities as input registers
  (FC 04) and read-write entities as holding registers (FC 03). 0/1 flags are
  analog registers, not bits.
* **Wide, sparse address space (≈0x0100–0x077A).** A single block read of the
  whole range exceeds Modbus' 125-register-per-request limit. The hub must read
  in **contiguous chunks** (≤125 regs) per function code, not one big block.
* **Enables are mandatory.** The integration should set PH02/PH27/PH28 on setup
  (or expose them), or writes will silently no-op.
* **Fan/percent registers use ×0.01 scaling**; temps/setpoints ×0.1; humidity ×1.
* See `references/HRDS+_Modbus_RTU_RS485_DE.pdf` §6 "FULL MODBUS REGISTER LIST"
  for the complete ~250-register table (schedulers, probe calibration, alarm
  tuning, hardware I/O mapping) not reproduced in full here.

---

## 13. Airflow: passive flow, fan integration, and active cooling

The HRDS+ sits on the supply branch of a central MVHR/VMC system (the "inflow
pipe"). The word *integration* is overloaded in the manufacturer documentation,
so this section pins down the three distinct concepts and the registers that
expose each. Sources: `HRDS+_Technisches_Handbuch_DE.pdf` (§ Funktionsweise /
Integration, Lüfterregelung) and `HRDS+_Benutzerhandbuch_DE.pdf` (operation
modes); register numbers from the Modbus PDF and §§6–8 above.

### 13.1 Three concepts, three meanings

| Concept | What physically happens | How it is exposed |
|---------|-------------------------|-------------------|
| **Passive airflow** | The unit's own supply fan is **off**, but the central MVHR upstream still pushes air through the unit's duct, so air keeps flowing through the inflow pipe. | **No dedicated register.** Infer it: `SupplyFan_Status` (1119) = `1` (OFF) while `sm_UnitStatus` (1104) = `5` (ON). The unit cannot measure the upstream MVHR's flow, so there is no "passive flow rate". |
| **Fan integration** (the *fan's* job) | The unit's **own supply fan runs** to "integrate" — i.e. blend the central-MVHR inflow air with recirculated room air and drive it across the coil. | `FanIntegration_Request` (1112) = `1` when the fan-integration function is active; `SupplyFan_Status` (1119) = `3` (ON); modulation at `outAO_SupplyFan` (639, ×0.01 %) and `actRPMsupplyFan` (1117). |
| **Active cooling** (the manufacturer's *"integration" register*) | The compressor / chilled-water circuit engages to **actively cool** the supply air in summer (the "Integration" function PG02). | `Status_Integ_byBMS` (1139, R/W request, requires PH27=1), feedback via `CmpStatus` (1122). **This is a different meaning of "integration" than the fan blending in row 2.** |

> **Trap.** `Status_Integ_byBMS` (1139) and `FanIntegration_Request` (1112) both
> contain the word *integration* but are unrelated: 1139 is the *active-cooling*
> command (compressor), 1112 is a read-only status that the *supply fan* is
> running its integration/blending function. The HA integration maps 1139 to the
> `active_cooling` switch and 1112 to the `fan_integration_active` binary sensor.

### 13.2 HA fan mode → register mapping

The climate entity writes `PM20_SupplyFan_Manual` (1614, holding, ×0.01) to
control the supply fan independently of the HVAC mode:

| Fan mode | Value written to 1614 | Percentage |
|----------|-----------------------|------------|
| off      | 0                     | 0 %        |
| low      | 3000                  | 30 %       |
| medium   | 5500                  | 55 %       |
| high     | 8500                  | 85 %       |

Read-back uses `outAO_SupplyFan` (639, ×0.01 %) with nearest-neighbour
thresholds at 42.5 % (low/medium) and 70.0 % (medium/high). Fan mode "off"
is also forced when `SupplyFan_Status` (1119) = `1` or `0`.

**Open question (unverified):** does writing `1614 = 0` actually stop the fan
when a mode is active, or is it clamped up to `MinSpeedFan_Dehum` (1853) /
`MinSpeedFan_Integ` (1852) internally? See `plans/todo.md`.

### 13.3 Detecting passive airflow

There is no Modbus point that reports "air is passively flowing through the
duct". Derive it from the fan being commanded off while the unit is otherwise
running:

```
passive_airflow = (sm_UnitStatus[1104] == 5)        # unit is ON
                  and (SupplyFan_Status[1119] == 1)  # but supply fan is OFF
                  and (FanIntegration_Request[1112] == 0)
```

The unit only knows the state of *its own* fan (1119) and its integration
request (1112). Whether the central MVHR is actually moving air is upstream of
the HRDS+ and not visible on this bus — treat passive airflow as "fan off, unit
on" and rely on the central system's own controls/sensors for the real rate.

### 13.4 Dehumidify with the fan running but active cooling off

This is a normal, common state: the unit is **drying** and the **fan is on**,
but **active cooling is off**.

* `Status_Dehum_byBMS` (1140) = 1 → the compressor condenses moisture out of the
  air. Dehumidification inherently needs airflow over the coil, so the **supply
  fan runs** (`SupplyFan_Status` 1119 = ON, `FanIntegration_Request` 1112 = 1)
  using the **dehumidify fan band** `MinSpeedFan_Dehum` (1853) /
  `MaxSpeedFan_Dehum` (1647).
* `Status_Integ_byBMS` (1139) = 0 → the **active-cooling** integration is *not*
  requested, so the chilled-water/active-cooling band
  `MinSpeedFan_Integ` (1852) / `MaxSpeedFan_Integ` (1646) is not in play.
* Feedback: `CmpStatus` (1122) = `4` (ON) because the compressor is running for
  dehumidification — **not** because active cooling is on. `DehumRequest`
  (1121) = 1, `outAO_SupplyFan` (639) shows the actual fan %.

In other words, the compressor here serves dehumidification, and the fan runs to
move/blend air across the coil; active cooling (1139) is an *additional,
separate* request layered on top in summer. See `PU05_ForceDehumInCooling`
(1692) for the inverse coupling (force dehum whenever cooling is requested) and
`PU02_EnableWinterDehum` (1689) for dehumidification in the winter season.

To reproduce over Modbus (assuming PH02/PH28 already = 1):
1. `1105` ← 1 (unit on), `1140` ← 1 (dehumidify), `1139` ← 0 (active cooling off).
2. Optionally shape the airflow with the dehumidify band `1853`/`1647`
   (×100 encoding: 50 % → `5000`).
3. Read back `1121`=1, `1119`=3 (fan ON), `1112`=1 (integration/blend active),
   `1139`-derived `CmpStatus` `1122`=4, while there is no active-cooling request.

---

## 14. Probes: built-in, display, and external sensors

### 14.1 Which probes are always present (factory-wired)

These sensors are hard-wired to fixed analog inputs on the control board and
are always available regardless of display or external probe configuration:

| Register | Addr DEC | Name | Input | Notes |
|----------|----------|------|-------|-------|
| `AI_Twater` | 501 | Water circuit temperature | M5 (AI5) fixed | Used for AL03 / AL04 protection |
| `AI_Tevaporation` | 511 | Evaporator temperature | M4 (AI4) fixed | Compressor modulation control |

The **high-pressure** and **low-pressure** switches (DI1/DI2) are also
factory-wired but are digital inputs that do not appear as Modbus analog
registers; they generate alarms AL11 / AL12 directly.

### 14.2 Which probes are external (must be wired by installer)

All other temperature and humidity measurements come from **configurable analog
inputs** on the control board. The installer assigns a function code to each
analog input (via parameters HA02, HA03 …) and wires the appropriate sensor to
the corresponding terminal. If no sensor is wired to a configured input, the
unit raises a probe-fault alarm.

| Register | Addr DEC | Name | Probe type | What it drives |
|----------|----------|------|-----------|---------------|
| `AI_TreturnRoom` | 499 | Room/return temperature | NTC 10 kΩ B3435 | Automatic dehumidify/cooling requests; alarm gating (PU13). **Raises AL28 if missing.** |
| `AI_HretRoom` | 505 | Room/return humidity | 0–10 V (0=0 %RH, 10 V=100 %RH) or 4–20 mA | Automatic dehumidify request. **Raises AL34 if missing.** |
| `AI_Toutdoor` | 500 | Outdoor temperature | NTC 10 kΩ B3435, outdoor-rated IP65+ | Only used by Free-Cooling/Free-Heating (PG03). Display-only if PG03 = 0. |
| `AI_Texhaust` | 502 | Exhaust air temperature | NTC 10 kΩ B3435 | Display/monitoring only — no control logic. |
| `AI_Tdischarge` | 503 | Discharge (supply) air temperature | NTC 10 kΩ B3435 | Display/monitoring only — no control logic. |
| `AI_AirQuality` | 506 | Air quality | 0–10 V or 4–20 mA IAQ sensor | Display/monitoring; can trigger ventilation boost if wired. |

The room temperature and humidity probes can alternatively be provided by the
**CNU2 wired display unit**, which has built-in T and H sensors. See §14.3.

### 14.3 Probe source — HA00 parameter (register 1803)

Parameter **HA00** (holding register 1803, R/W) tells the controller which
source to use for room temperature and humidity. The unit ignores readings from
unconfigured inputs; it raises AL28/AL34 when the configured source is absent.

| HA00 value | Meaning | Room T source | Room H source |
|-----------|---------|---------------|---------------|
| `0` | None / external probes | AI2 (M2) if wired with code 45 | AI3 (M3) if wired with code 53/54 |
| `1` | CNU display, T only | CNU built-in NTC | — |
| `2` | CNU display, T + H | CNU built-in NTC | CNU built-in humidity |
| `3` | EPJ display, T only | EPJ built-in NTC | — |
| `4` | EPJ display, T + H | EPJ built-in NTC | EPJ built-in humidity |
| `5` | CNU2 display, T only | CNU2 built-in NTC | — |
| `6` | CNU2 display, T + H **(factory default)** | CNU2 built-in NTC | CNU2 built-in humidity |

> **Headless setup (no display, no external probes):** set HA00 = 0 **and**
> PH01 (1777) = 0 ("display not present"). Without this, the unit raises AL28
> and AL34 continuously, which blocks dependent control. The HA integration
> exposes HA00 as a `select` entity (`probe_source`) and PH01 via the
> `enable_onoff_bms` family; set both from HA rather than requiring a
> service-tool visit.

### 14.4 Probe fault detection — packed alarm registers

Probe faults are reported in the packed alarm bitmap registers. Bits are
**set** when the alarm is active (probe absent or faulty):

| Alarm | Register | Addr DEC | Bit | What it blocks |
|-------|----------|----------|-----|----------------|
| AL28 — room temp probe fault | `PackedAlarm_2` | 769 | 11 | Automatic integration (cooling/heating) request; PU13 minimum-temp interlock |
| AL34 — room humidity probe fault | `PackedAlarm_3` | 770 | 1 | Automatic dehumidify request |

The HA integration decodes these bits into two binary sensors:

* `temp_probe_ok` — **ON** = room temperature probe is healthy (AL28 not active)
* `humidity_probe_ok` — **ON** = room humidity probe is healthy (AL34 not active)

When either sensor reads OFF, the climate entity suppresses the corresponding
`current_temperature` / `current_humidity` attribute (reports `None`) so the
HA UI does not show a stale or garbage value.

### 14.5 What each probe controls (summary)

| Probe | Control purpose | Display only if… |
|-------|----------------|-----------------|
| Room temperature (499) | Triggers auto cooling (SEtC/SEtH) and auto dehumidify (PU13 guard) | HA00 = 0 with no probe wired |
| Room humidity (505) | Triggers auto dehumidify (PU01 setpoint) | HA00 = 0 with no probe wired |
| Evaporator temp (511) | Compressor modulation (PU11 target 6 °C) | Never — always controls |
| Water temp (501) | AL03 / AL04 protection; gates cooling/heating | Never — always controls |
| Outdoor temp (500) | Free-Cooling / Free-Heating damper control | PG03 = 0 (default) |
| Exhaust temp (502) | — | Always display only |
| Discharge temp (503) | — | Always display only |

### 14.6 Running without any display or external probes

The unit can be driven **entirely via Modbus** (from Home Assistant) without a
display or any room sensors. In this mode:

1. Set **HA00 = 0** (`probe_source` select → "None / external probes") and
   **PH01 = 0** (disable display; the HA integration does not yet expose PH01
   directly — set it once via the wired remote's installer menu or service
   software).
2. The HA integration auto-sets **PH02/PH27/PH28** = 1 on every connection,
   so on/off, dehumidify and cooling are controllable immediately.
3. Automatic setpoint-based control (trigger dehumidify when room humidity >
   PU01) does **not** function — there is no room sensor to compare against.
   Issue dehumidify / cooling requests **explicitly via Modbus** (the climate
   entity or individual switches).
4. `current_temperature` and `current_humidity` on the climate entity read
   `None`; the `temp_probe_ok` and `humidity_probe_ok` binary sensors read OFF
   (because AL28/AL34 are active). This is expected and not an error.
5. The evaporator and water-circuit probes remain active (factory-wired) and
   continue to protect the unit against AL03/AL04/AL11/AL12.
