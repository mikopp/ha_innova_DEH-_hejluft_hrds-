# HRDS+ / Innova DEH+ — Modbus Register Definition

Machine-readable extraction of the Modbus register map for the **hej.luft HRDS+**
air-dehumidification module (OEM: **Innova DEH+**), taken from
`references/HRDS+_Modbus_RTU_RS485_DE.pdf` (Stand: Mai 2026).

This file is the **single source of truth for the registers**: which exist,
their addresses, names, encodings, ranges and value meanings. It is written to
be read by both humans and agents. If a value here disagrees with the PDF, the
PDF wins — please fix this file.

What the unit *does* with these registers (states, sequences, seasons,
variants, what was tested on hardware) is in
[`UNIT_BEHAVIOUR.md`](UNIT_BEHAVIOUR.md). How the Home Assistant integration
uses them is in [`../adr/`](../adr/README.md) and [`../../README.md`](../../README.md),
not here.

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
  * Working hours (`PM00`…`PM04`): raw = whole hours, one 16-bit word each
    (UNIT_BEHAVIOUR.md T29). The display's "Hours x10" shows raw ÷ 10, so
    the shipped limit raw `20000` ("2000.0") is 20000 h.

## 3. Function enables — **set these first**

Modbus write commands are **ignored** unless the matching "by BMS" function is
enabled. An `OFF` command always wins over any `ON` command, regardless of
source (contact, display, Modbus).

| Addr HEX | Addr DEC | Name                    | R/W | Description |
|----------|----------|-------------------------|-----|-------------|
| `0x06F2` | 1778 | `Enable_OnOffByBMS`       | R/W | **PH02** — set `1` to allow On/Off over Modbus (`0=Disabled,1=Enabled`). |
| `0x074D` | 1869 | `Enable_IntegByBMS`       | R/W | **PH27** — set `1` to allow the integration (INT) request over Modbus. |
| `0x074E` | 1870 | `Enable_DehumByBMS`       | R/W | **PH28** — set `1` to allow the dehumidify request over Modbus. |
| `0x06F1` | 1777 | `Enable_OnOffByDisplay`   | R/W | **PH01** — set `0` if no wired display is present. While `1` with no display the unit stays `sm_UnitStatus` = `0` (OFF by display) permanently, and an OFF from any source beats a Modbus ON. Factory value is `1`. See [UNIT_BEHAVIOUR §3.1](UNIT_BEHAVIOUR.md#31-on--off). |
| `0x070B` | 1803 | `T/H Probe Source` (HA00) | R/W | Source for temp/humidity probes: `0=None`, `6=CNU2 display` (factory default; a unit seen in the field read `2`). Set `0` if no display. All values: §14.3. |

## 4. Operating commands (control)

| Addr HEX | Addr DEC | Name                  | R/W | Values / meaning |
|----------|----------|-----------------------|-----|------------------|
| `0x0451` | 1105 | `Status_OnOff_byBMS`     | R/W | Unit On/Off request: `0=Off`, `1=On`. (Requires PH02=1.) |
| `0x0474` | 1140 | `Status_Dehum_byBMS`     | R/W | Dehumidify request: `0=No`, `1=Yes`. (Requires PH28=1.) |
| `0x0473` | 1139 | `Status_Integ_byBMS`     | R/W | Integration / **active-cooling** request: `0=No`, `1=Yes`. (Requires PH27=1.) |
| `0x062F` | 1583 | `Mode_OperatingMode`     | R/O | Season: `0=Summer`, `1=Winter`, `2=Auto`. Use as feedback. |
| `0x0721` | 1825 | `DI4_Configuration`(HB04)| R/W | Season change w/o display: `4=Summer (DI4 N/O)`, `3=Winter (DI4 N/C)`. **Only 3 or 4 are valid — other values raise alarm AL25.** |
| `0x0766` | 1894 | `PC12_Enable_OnOFF_by_INT_DEU` | R/W | `1` = a DEU/INT request on the **digital inputs** starts the unit even with the OFF/OFF contact open. (Earlier docs guessed 1879; that is PE24.) |
| `0x0756` | 1878 | `PriorityChangeMode_Display` (PC11) | R/W | Who owns season change: `0=Display`, `1=DI/Digital-IN`. |

> **Integration (INT)** (`0x0473`) cools in summer and supports heating in
> winter; **DEU** (`0x0474`) dehumidifies. What each request does in which
> season: [UNIT_BEHAVIOUR §6–§7](UNIT_BEHAVIOUR.md#6-summer-operation).

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
> are connected [Modbus manual p.6]. Clamps and automatic thresholds:
> [UNIT_BEHAVIOUR §3.3–§3.4](UNIT_BEHAVIOUR.md#33-requests-deu-and-int).

## 6. Fan speed

Fan-speed registers are percentages with **two implied decimals** (write `4000`
for 40 %). Min/Max apply to the modulation band used in each mode.

| Addr HEX | Addr DEC | Name                 | R/W | Default | Range | Meaning |
|----------|----------|----------------------|-----|---------|-------|---------|
| `0x073D` | 1853 | `MinSpeedFan_Dehum` (PF28) | R/W | 50.00 | 0–100 | Supply-fan min speed in dehumidify |
| `0x066F` | 1647 | `MaxSpeedFan_Dehum` (PF10) | R/W | 85.00 | 0–100 | Supply-fan max speed in dehumidify |
| `0x073C` | 1852 | `MinSpeedFan_Integ` (PF27) | R/W | 50.00 | 0–100 | Supply-fan min speed in integration (cooling) |
| `0x066C` | 1644 | `MinSpeedSupplyFan_VMC` (PF07) | R/W | — | 0–100 | Supply-fan min speed in VMC (ventilation-only) mode |
| `0x066E` | 1646 | `MaxSpeedFan_Integ` (PF09) | R/W | 85.00 | 0–100 | Supply-fan max speed in integration (cooling) |
| `0x064E` | 1614 | `PM20_SupplyFan_Manual`    | R/W | — | 0–100 | Supply-fan manual setpoint of the **display**. Listed R/W in the raw parameter table [MB p.18], defined "via Display (read only)" in the handbook (PM20, §5.3); the unit sets it itself, a written value does not hold, one outside the band answers exception 04 (UNIT_BEHAVIOUR.md §9.1, T22, T23, T27, T28). Not a fan-speed command |
| `0x0458` | 1112 | `FanIntegration_Request`   | R/O | — | 0–100 | "Fans integration request": the fan request of the integration (INT) fan control (`PF31`) [MB p.14]. Not a 0/1 flag and not the INT request (1139), see §13. Read 0 while the fan ran during two dehumidify requests (UNIT_BEHAVIOUR.md T16, T18) |
| `0x0459` | 1113 | `Supply_AirQualityRequest` | R/O | — | 0–100 | Supply-fan air-quality request [MB p.14] |
| `0x045A` | 1114 | `SupplyFan_ManualRequest`  | R/O | — | 0–100 | Current manual (display) fan request; reads the same as `PM20` |
| `0x045B` | 1115 | `Supply_TimeBandsRequest`  | R/O | — | 0–100 | Supply-fan time-band request [MB p.15] |
| `0x045C` | 1116 | `SupplyFan_RemoteRequest`  | R/O | — | 0–100 | Current potentiometer (0–10 V) fan request |
| `0x027F` | 639  | `outAO_SupplyFan`          | R/O | — | 0–100 | Actual supply-fan analog output %: the speed the fan is driven at |
| `0x045D` | 1117 | `actRPMsupplyFan`          | R/O | — | 0–65535 | Supply-fan actual RPM. Needs an input allocated to the tachometer (input function 45 or 46, §16 `HA..`/`HB..`); 0 without one (UNIT_BEHAVIOUR.md §9.1) |

### 6.1 How the bands apply

The min/max pairs are per-mode bands; the handbook scales display and 0–10 V
requests linearly into the active band (§6.2). On a real unit the manual
(display) request mirrored in 1114/1614 is instead clamped into the band: a
raised minimum raises it, a lowered one leaves it (UNIT_BEHAVIOUR.md T24–T26).
No register takes a fan-speed
request from the BMS; the band registers are the only fan-speed registers the
Modbus manual's fan chapter lists as writable [MB p.7]. Other writable fan
setpoints, each tied to a condition: `FSC`/`FSE`/`FSN` (1595–1597, time bands,
need time programs `PH03`) [MB p.18], `PF23` (1660, forced by a digital input)
[MB p.20], `PF26` (1637, run-on). Behaviour:
[UNIT_BEHAVIOUR §9.1](UNIT_BEHAVIOUR.md#91-bands-and-sources).

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
| `0x045F` | 1119 | `SupplyFan_Status`   | `0=Disable`, `1=OFF`, `2=Wait ON`, `3=ON`, `4=Wait OFF`, `5=Alarm` |
| `0x0461` | 1121 | `DehumRequest`       | `0=No`, `1=Yes` — dehumidification currently requested |
| `0x0462` | 1122 | `CmpStatus`          | `0=Disable`, `1=Alarm`, `2=Manual`, `3=Wait ON`, `4=ON`, `5=Wait OFF`, `6=OFF` — compressor (active cooling/dehum) |
| `0x0464` | 1124 | `outDO_WaterCond` | Internal water condenser valve (relay K4): `0=OFF`, `1=ON`, `2=Disable`. A real unit reads `1` in standby, against the handbook's description; see [UNIT_BEHAVIOUR §11.1](UNIT_BEHAVIOUR.md#111-internal-valve-relay-k4). |
| `0x0466` | 1126 | `outDO_WaterFlow` | External water valve V3V (relay K5) — the PM pump output is switched together with it: `0=OFF`, `1=ON`, `2=Disable` (output not configured). |
| `0x046E` | 1134 | `outDO_RecircDamper` | `0=OFF` (damper closed), `1=ON` (damper open), `2=Disable` (no damper output allocated; expected on a non-`R` unit) |
| `0x027F` | 639  | `outAO_SupplyFan`    | Supply-fan output % (×0.01) |
| `0x0281` | 641  | `outAO_Cmp`          | Compressor output % (×0.01) |
| `0x044F` | 1103 | `OR_Alarms`          | `0/1` cumulative "any alarm active" flag |

### Packed digital I/O status (bit-fields, R/O)

The device packs digital inputs/outputs into 16-bit registers using **2 bits
per signal** (`bitN..bitN+1`); a non-zero pair means active.

| Addr HEX | Addr DEC | Name | Notable bits |
|----------|----------|------|--------------|
| `0x0180` | 384 | `Packed_DO1` | bit4-5=Compressor (K6), bit8-9=Recirculation damper (K1), bit10-11=External water valve or pump (K5), bit12-13=Water condensation valve (K4) (`0=Integration,1=Dehumidify`) |
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

What triggers each alarm, what it stops and how it resets:
[UNIT_BEHAVIOUR §12](UNIT_BEHAVIOUR.md#12-alarms-and-what-they-do-to-the-flow).

| Code | Description |
|------|-------------|
| AL02 | High humidity |
| AL03 | High summer water temperature |
| AL04 | Low winter water temperature |
| AL11 | Compressor low-pressure / frost-thermostat |
| AL12 | Compressor high-pressure switch |
| AL16 | Water-circuit antifreeze |
| AL18 | Generic alarm |
| AL19 | Generic warning |
| AL22 | Dirty filters |
| AL25 | I/O configuration error |
| AL26 | RTC clock failed/disconnected |
| AL28 | Room/return temperature probe fault |
| AL29 | External temperature probe fault |
| AL30 | Water temperature probe fault |
| AL34 | Room/return humidity probe fault |
| AL36 | Fan potentiometer fault |
| AL39 | Evaporator temperature probe fault |

### 9.3 Alarm reset registers (R/W)

Write `1` to reset the corresponding alarm: `0x030B`=AL01, `0x030C`=AL02,
`0x0311` (785)=AL11, `0x0312` (786)=AL12, `0x0317` (791)=AL18, `0x0319`=AL21,
`0x031A`=AL26, … (full list `0x030B`–`0x031A`).
**Filter alarm AL22 is reset by writing `0` to `0x0644` (1604).**

## 10. Key configuration parameters (R/W) worth knowing

| Addr HEX | Addr DEC | Name | Meaning |
|----------|----------|------|---------|
| `0x0705` | 1797 | `PG01_MachineType` | Fan arrangement: `0=supply fan only`, `1=supply fan + exhaust fan` (handbook PG01: „Entfeuchter nur mit Zuluftventilator“ / „mit Zuluft- und Abluftventilator“). **Not** "has a recirculation fan": an `R` unit reads `0` (its one fan is the recirculation fan). Use `outDO_RecircDamper` (1134) for that — `2=Disable` means no damper wired. Verified on an HRDS+ 30 `R`: PG01 = 0 with the damper output present (1134 = 0). |
| `0x0706` | 1798 | `PG02_EnableIntegration` | Enable the active-cooling integration function |
| `0x0699` | 1689 | `PU02_EnableWinterDehum` | `0=No`, `1=With water`, `2=Without water` |
| `0x069C` | 1692 | `PU05_ForceDehumInCooling` | Force dehumidify when cooling requested |
| `0x06F5` | 1781 | `PH05_TemperatureUM` | `0=°C`, `1=°F` |
| `0x06F3` | 1779 | `PH03_EnableTimePrograms` | `0=No`, `1=Yes`. Time programs can switch the unit OFF (status `off_by_scheduler`). |
| `0x070D` | 1805 | `HA02_AI2_Allocation` | Analog input 2 allocation. `0`=unused, `45`=room temperature probe. A probe code with nothing wired raises AL28. |
| `0x070E` | 1806 | `HA03_AI3_Allocation` | Analog input 3 allocation. `0`=unused, `53`/`54`=room humidity probe. A probe code with nothing wired raises AL34. |
| `0x0720` | 1824 | `DI3_Configuration` (HB03) | Remote ON/OFF contact (OFF/OFF terminals): `0=unused`, `1=normally closed`, `2=normally open`. With the contact open the unit is forced OFF (`off_by_di`). |
| `0x0728` | 1832 | `HC04` | Analog output allocation of the supply fan (raw code; `1` = 0-10 V supply fan). |
| `0x072E` | 1838 | `HD01` | Relay DO1 allocation (raw code; `10` = recirculation damper NO, `9` = NC). |
| `0x06A2` | 1698 | `PS01_PreStartTime_RecircDamper` | Damper pre-start time before the fan starts, in seconds (handbook default 20; a real unit read 90). |
| `0x0642` | 1602 | `PM00_Limit_FansHours` | Fan running-hours alarm limit (h; the display shows ÷ 10) |
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
   `PG02_EnableIntegration` (1798) = 1 (installer setting). In summer INT cools,
   in winter it supports heating.
2. On: write `1` to `1139`; Off: write `0`.
3. Compressor feedback via `1122` (`CmpStatus`, `4`=ON).

**Set the air-flow (fan) speed**
* Dehumidify-mode band: min `1853`, max `1647`. Cooling band: min `1852`,
  max `1646`. Remember the **×100** encoding (`40 %` → `4000`). `1614` (`PM20`)
  is the display's setpoint and does not hold a written value (§6).
* Actual output: `639` (`outAO_SupplyFan`, ×0.01 %), RPM: `1117`.

**Set the humidity target** — write %RH to `1586` (`PU01`), clamped by `1892`/`1893`.

**Set the temperature target** — summer `1584`, winter `1585` (°C ×0.1).

**Read sensors** — room temp `499` (×0.1 °C), room humidity `505` (%RH),
outdoor temp `500`, water temp `501`, supply/discharge temp `503`.

**Is the unit on?** — read `1104`; `5` = ON, anything `0–4` = a specific OFF cause.
A written request reads back late (several polls on a real unit), see
[UNIT_BEHAVIOUR §3.3](UNIT_BEHAVIOUR.md#33-requests-deu-and-int).

**Check errors / status** — read `1103` (any-alarm flag) then `768/769/770`
(per-bit alarm codes); decode with §9.2.

---

## 12. Transport notes

* **No coils / discrete inputs.** Read-only values are input registers (FC 04),
  read-write values holding registers (FC 03/06/16). 0/1 flags are analog
  registers, not bits [Modbus manual p.5].
* **Wide, sparse address space (≈0x0100–0x077A).** A single block read of the
  whole range exceeds Modbus' 125-register-per-request limit, so read in
  contiguous chunks per function code.
* **Keep the chunks small.** On a real unit behind an RS-485→TCP gateway a
  120-register read got no reply at all, while 10-register reads covered the
  whole map ([UNIT_BEHAVIOUR evidence T9](UNIT_BEHAVIOUR.md#13-evidence-log-what-was-seen-on-real-hardware)).
  Whether the limit is the gateway's or the controller's is open.
* **Enables are mandatory**: §3.
* See `HRDS+_Modbus_RTU_RS485_DE.pdf` §6 "FULL MODBUS REGISTER LIST" for the
  complete table (schedulers, probe calibration, alarm tuning, hardware I/O
  mapping); the installer parameters from it are in §16.

---

## 13. Two registers called "integration"

`Status_Integ_byBMS` (1139) and `FanIntegration_Request` (1112) both contain
the word *integration* but are unrelated: 1139 is the **INT request**
(cooling in summer, heating support in winter, written by the BMS); 1112 is a read-only "fans integration request", a fan request in % of the INT fan control (§6). It read 0 while the supply fan ran for a dehumidify request (UNIT_BEHAVIOUR.md §13, T16).

Airflow behaviour (passive MVHR flow, recirculation coupled to every request,
the unofficial I/O workaround) is in
[UNIT_BEHAVIOUR §9](UNIT_BEHAVIOUR.md#9-fan), in particular
[§9.3 Recirculation is coupled to every request](UNIT_BEHAVIOUR.md#93-recirculation-is-coupled-to-every-request-r-variant).

---

## 14. Probes: inputs and probe source

### 14.1 Analog inputs

| Register | Addr DEC | Input | Probe | Notes |
|----------|----------|-------|-------|-------|
| `AI_TreturnRoom` | 499 | AI2 (M2) when `HA02 = 45`, or the display | NTC 10 kΩ @ 25 °C, B 3435 | Probe fault: AL28 |
| `AI_Toutdoor` | 500 | configurable input | NTC 10 kΩ B 3435, outdoor rated | Probe fault: AL29 |
| `AI_Twater` | 501 | AI5 (M5), factory wired | — | Probe fault: AL30 |
| `AI_Texhaust` | 502 | configurable input | NTC 10 kΩ B 3435 | — |
| `AI_Tdischarge` | 503 | configurable input | NTC 10 kΩ B 3435 | — |
| `AI_HretRoom` | 505 | AI3 (M3) when `HA03 = 53/54`, or the display | 4–20 mA (`53`) or 0–10 V (`54`), 0–100 %RH | Probe fault: AL34 |
| `AI_AirQuality` | 506 | configurable input | 0–10 V / 4–20 mA | — |
| `AI_Tevaporation` | 511 | AI4 (M4), factory wired | — | Inverter version only; probe fault: AL39 |

The high- and low-pressure switches (DI1/DI2, the frost thermostat on DI2's
input) are digital inputs with no analog register; they raise AL12 / AL11.
Sources: handbook §6.3, §6.7, §7.3; Modbus manual p.7.

What each probe drives, and how the unit behaves with and without a display
or probes: [UNIT_BEHAVIOUR §8](UNIT_BEHAVIOUR.md#8-display-and-probe-configurations).

### 14.2 (merged into 14.1)

### 14.3 Probe source — HA00 parameter (register 1803)

Parameter **HA00** tells the controller which source to use for room
temperature and humidity (handbook §5.3, §6.7).

| HA00 value | Meaning | Room T source | Room H source |
|-----------|---------|---------------|---------------|
| `0` | None / external probes | AI2 (M2) if allocated with code 45 | AI3 (M3) if allocated with code 53/54 |
| `1` | CNU display (Evj), T only | CNU built-in NTC | — |
| `2` | CNU display (Evj), T + H | CNU built-in NTC | CNU built-in humidity |
| `3` | EPJ display, T only | EPJ built-in NTC | — |
| `4` | EPJ display, T + H | EPJ built-in NTC | EPJ built-in humidity |
| `5` | CNU2 display (Epj Graph), T only | CNU2 built-in NTC | — (AI3 probe possible) |
| `6` | CNU2 display (Epj Graph), T + H **(factory default)** | CNU2 built-in NTC | CNU2 built-in humidity |

Required pairs (handbook §5.1, §8.1): with CNU2 `PH01 = 1, HA00 = 6`; without
CNU2 `PH01 = 0, HA00 = 0`. A real unit without a display shipped with
`HA00 = 2`.

### 14.4 Probe fault bits

| Alarm | Register | Addr DEC | Bit |
|-------|----------|----------|-----|
| AL28 — room temperature probe fault | `PackedAlarm_2` | 769 | 11 |
| AL34 — room humidity probe fault | `PackedAlarm_3` | 770 | 1 |

### 14.5 / 14.6 (moved)

What each probe controls and how a unit without display or probes behaves:
[UNIT_BEHAVIOUR §8](UNIT_BEHAVIOUR.md#8-display-and-probe-configurations).
Request sources (automatic, digital input, Modbus):
[UNIT_BEHAVIOUR §3.3](UNIT_BEHAVIOUR.md#33-requests-deu-and-int).

### 14.7 Unwired analog inputs read a sentinel, not a temperature

Observed on an HRDS+ 30 with no display and no external probes (HA00 = 2,
PH01 = 1): `AI_TreturnRoom` (499), `AI_Toutdoor` (500), `AI_Texhaust` (502),
`AI_Tdischarge` (503), `AI_HretRoom` (505) and `AI_AirQuality` (506) all read raw
`32772` (`0x8004`); register 507 read `32762` (`0x7FFA`). Decoded as INT16 ×0.1
that is **-3276.4 °C** (and -32764 %RH), which is never a real reading. The
factory-wired `AI_Twater` (501) and `AI_Tevaporation` (511) read normally.

This sentinel is empirical, not in the manufacturer tables. A window of
`0x7FF0..0x800F` covers both observed words and cannot collide with a real
reading (±3276 °C). Negative temperatures are fine (-1.0 °C = `0xFFF6`). What a
wired but broken probe reads is not known yet.

---

## 15. Control parameters worth reading

Extracted from `HRDS+_Modbus_RTU_RS485_DE.pdf` §6 (FULL MODBUS REGISTER LIST).
What the unit does with them: [UNIT_BEHAVIOUR §5](UNIT_BEHAVIOUR.md#5-decision-procedure-agent-readable).

| Addr HEX | Addr DEC | Name | R/W | Range | Meaning |
|----------|----------|------|-----|-------|---------|
| `0x069E` | 1694 | `PU07_Dehumidity_Diff` | R/W | 0-100 %RH | Automatic DEU request on above `PU01 + PU07`, off below `PU01`. |
| `0x0761` | 1889 | `PU13_MinTRoom_disableDEU` | R/W | 0-30.0 °C (×0.1) | Room temperature below which dehumidification (and the compressor) is disabled. |
| `0x0762` | 1890 | `PU14_TRoomDIFF_enableDEU` | R/W | 0.1-20.0 °C (×0.1) | Differential above `PU13` at which dehumidification is re-enabled. |
| `0x0666` | 1638 | `PF01_MinTimeOnFan` | R/W | 0-999 s | Minimum fan run time. |
| `0x0668` | 1640 | `PF03_MinTimePostFan` | R/W | 0-999 s | Fan run-on after the compressor stops (`0` disables it). |
| `0x0707` | 1799 | `PG03_EnableFreeCoolingHeating` | R/W | `0=No`, `1=Yes` | Enables free cooling/heating; only then does `AI_Toutdoor` (500) drive anything. |

> The `PF01`/`PF03` unit is inferred from the parameter's 0-999 range and the
> technical manual's description ("Mindestlaufzeit" / "Nachlauf"); it is not
> stated explicitly in the Modbus table. Confirm against the wired display
> before relying on the absolute value.

### 15.1 (moved)

The consequences for an external controller (the unit already enforces minimum
run times, `PU13` can veto a dehumidify request, `PU07` sets the unit's own
hysteresis) are in [UNIT_BEHAVIOUR §3.3, §9, §10](UNIT_BEHAVIOUR.md#33-requests-deu-and-int).

---

## 16. Installer-menu parameters (installer device)

Every handbook parameter (§5.3) that has a Modbus address in the RTU
manual's parameter table and is not already listed above. Scaling was checked
against a real unit's raw read-back. Not listed: passwords (`PSd*`), `PH15`
(restore defaults), `PH18` (clear alarm history) and addresses above 1900
(not verified).

The *Access* column mixes two things: `R/W` / `R/O` is the register as the
Modbus manual defines it; "shown R/O" and "disabled by default" record how the
Home Assistant integration exposes it (it deliberately never writes link
settings, I/O allocation, refrigerant, safety bypass and test mode; source of
truth for that: `custom_components/innova_hrds/installer_params.py`).

| Addr HEX | Addr DEC | Code | Meaning | Scale | Range | Access |
|----------|----------|------|---------|-------|-------|--------|
| `0x0642` | 1602 | PM00 | Fan hours alarm limit | x1 | 0…65535 h | R/W |
| `0x0644` | 1604 | PM01 | Supply fan hours (0 resets AL22) | x1 | 0…65535 h | R/W |
| `0x0646` | 1606 | PM02 | Return fan hours | x1 | 0…65535 h | shown R/O, disabled by default |
| `0x0648` | 1608 | PM03 | Compressor hours alarm limit | x1 | 0…65535 h | R/W |
| `0x064A` | 1610 | PM04 | Compressor hours | x1 | 0…65535 h | shown R/O |
| `0x064F` | 1615 | PM21 | Compressor forced | x1 | 0…1  | shown R/O |
| `0x0650` | 1616 | PM80 | Room temperature probe offset | x0.1 | -10…10 °C | R/W |
| `0x0651` | 1617 | PM81 | Outdoor temperature probe offset | x0.1 | -10…10 °C | R/W |
| `0x0652` | 1618 | PM82 | Water temperature probe offset | x0.1 | -10…10 °C | R/W |
| `0x0653` | 1619 | PM83 | Exhaust temperature probe offset | x0.1 | -10…10 °C | R/W, disabled by default |
| `0x0654` | 1620 | PM84 | Discharge temperature probe offset | x0.1 | -10…10 °C | R/W |
| `0x0655` | 1621 | PM85 | Defrost probe offset | x0.1 | -10…10 °C | R/W, disabled by default |
| `0x0656` | 1622 | PM86 | Room humidity probe offset | x1 | -10…10 % | R/W |
| `0x0657` | 1623 | PM87 | Air quality probe offset | x1 | -100…100 ppm | R/W, disabled by default |
| `0x0658` | 1624 | PM88 | Fan potentiometer offset | x1 | -10…10 % | R/W, disabled by default |
| `0x0659` | 1625 | PM89 | Pressure probe offset | x0.1 | -20…20 bar | shown R/O, disabled by default |
| `0x065B` | 1627 | PC01 | Room temperature sniffing cycles | x1 | 0…1  | R/W 0/1, disabled by default |
| `0x065C` | 1628 | PC02 | Sniffing wait time | x1 | 0…999 min | R/W, disabled by default |
| `0x065D` | 1629 | PC03 | Sniffing active time | x1 | 1…30 min | R/W, disabled by default |
| `0x065E` | 1630 | PC04 | Both fans in sniffing cycle | x1 | 0…1  | R/W 0/1, disabled by default |
| `0x065F` | 1631 | PC05 | Season change (0 manual, 1 manual+auto, 2 auto) | x1 | 0…2  | R/W |
| `0x0660` | 1632 | PC06 | Auto season probe (0 water, 1 room) | x1 | 0…1  | R/W |
| `0x0661` | 1633 | PC07 | Max water temperature for dehumidify / summer integration | x0.1 | 0…70 °C | R/W |
| `0x0662` | 1634 | PC08 | Min water temperature for winter integration (below it AL04 blocks heating) | x0.1 | 0…70 °C | R/W |
| `0x0663` | 1635 | PC09 | Auto summer above room temperature | x0.1 | 0…70 °C | R/W |
| `0x0664` | 1636 | PC10 | Auto winter below room temperature | x0.1 | 0…70 °C | R/W |
| `0x0665` | 1637 | PF26 | Supply fan post-run speed | x0.01 | 0…100 % | R/W |
| `0x0667` | 1639 | PF02 | Delay between the two fans | x1 | 0…999 s | R/W, disabled by default |
| `0x0669` | 1641 | PF04 | Stop supply fan during defrost | x1 | 0…1  | R/W 0/1, disabled by default |
| `0x066A` | 1642 | PF05 | Supply fan speed on air quality probe fault | x0.01 | 0…100 % | R/W, disabled by default |
| `0x066D` | 1645 | PF08 | Supply fan max speed (VMC) | x0.01 | 0…100 % | R/W |
| `0x0670` | 1648 | PF11 | Fan speed step | x1 | 1…100 % | R/W |
| `0x0671` | 1649 | PF12 | Room temperature dead band | x0.1 | 0…20 °C | R/W |
| `0x0672` | 1650 | PF13 | Fan speed step interval (integration) | x1 | 1…100 s | R/W |
| `0x0674` | 1652 | PF15 | Air quality setpoint min | x1 | 1…9999 ppm | R/W, disabled by default |
| `0x0675` | 1653 | PF16 | Air quality setpoint max | x1 | 1…9999 ppm | R/W, disabled by default |
| `0x0676` | 1654 | PF17 | Air quality setpoint | x1 | 1…9999 ppm | R/W, disabled by default |
| `0x0677` | 1655 | PF18 | Air quality dead band | x1 | 0…1000 ppm | R/W, disabled by default |
| `0x0678` | 1656 | PF19 | Air quality fan step interval | x1 | 1…100 s | R/W, disabled by default |
| `0x0679` | 1657 | PF20 | Defrost fan speed step | x0.01 | 0…100 % | R/W, disabled by default |
| `0x067A` | 1658 | PF21 | Defrost fan step interval | x1 | 1…100 s | R/W, disabled by default |
| `0x067C` | 1660 | PF23 | Supply fan speed forced by DI | x0.01 | 0…100 % | R/W |
| `0x067F` | 1663 | PE01 | Compressor minimum off time | x1 | 0…999 s | R/W |
| `0x0680` | 1664 | PE02 | Compressor minimum on time | x1 | 0…999 s | R/W |
| `0x0681` | 1665 | PE03 | Minimum time between compressor starts | x1 | 0…999 s | R/W |
| `0x0682` | 1666 | PE04 | Delay fan start to compressor start | x1 | 0…999 s | R/W |
| `0x0683` | 1667 | PE05 | Compressor safety-time bypass | x1 | 0…1  | shown R/O |
| `0x0684` | 1668 | PE06 | Compressor min output (dehumidify) | x0.01 | 0…100 % | R/W |
| `0x0685` | 1669 | PE07 | Compressor max output (dehumidify) | x0.01 | 0…100 % | R/W |
| `0x0686` | 1670 | PE08 | Compressor output step | x0.01 | 1…100 % | R/W |
| `0x0687` | 1671 | PE09 | Compressor output step interval | x1 | 1…100 s | R/W |
| `0x0688` | 1672 | PE10 | Defrost interval | x1 | 1…99 h | R/W, disabled by default |
| `0x0689` | 1673 | PE11 | End of defrost setpoint | x0.1 | -15…70 °C | R/W, disabled by default |
| `0x068A` | 1674 | PE12 | Maximum defrost time | x1 | 1…99 min | R/W, disabled by default |
| `0x068B` | 1675 | PE13 | Dripping time | x1 | 0…15 min | R/W, disabled by default |
| `0x068C` | 1676 | PE14 | Defrost interval counting | x1 | 0…2  | R/W, disabled by default |
| `0x068D` | 1677 | PE15 | Defrost counting setpoint | x0.1 | -15…70 °C | R/W, disabled by default |
| `0x068E` | 1678 | PE16 | Condenser valve switch time | x1 | 0…999 s | R/W |
| `0x068F` | 1679 | PE17 | High-pressure pre-alarm setpoint | x0.1 | 16…42 bar | R/W |
| `0x0690` | 1680 | PE18 | High-pressure pre-alarm differential | x0.1 | 0.1…10 bar | R/W |
| `0x0691` | 1681 | PE19 | Compressor step at high-pressure pre-alarm | x0.01 | 0…100 % | R/W |
| `0x0692` | 1682 | PE20 | Step interval at high-pressure pre-alarm | x1 | 1…999 s | R/W |
| `0x0693` | 1683 | Pb01 | Water valve close delay | x1 | 0…999 s | R/W |
| `0x0694` | 1684 | Pb02 | Valve sniffing active time (temperature alarm) | x1 | 1…999 s | R/W |
| `0x0695` | 1685 | Pb03 | Valve sniffing wait time (temperature alarm) | x1 | 1…99 min | R/W |
| `0x0696` | 1686 | Pb04 | Preheating setpoint | x0.1 | 0…30 °C | R/W, disabled by default |
| `0x0697` | 1687 | Pb05 | Preheating differential | x0.1 | 0.1…20 °C | R/W, disabled by default |
| `0x0698` | 1688 | Pb06 | Preheating maximum time | x1 | 0…60 min | R/W, disabled by default |
| `0x069A` | 1690 | PU03 | Dehumidify during high-temperature alarm | x1 | 0…1  | R/W 0/1 |
| `0x069B` | 1691 | PU04 | Dehumidify during water-flow alarm | x1 | 0…1  | R/W 0/1 |
| `0x069F` | 1695 | PU08 | Cold-water-only dehumidify below water temperature | x0.1 | 0…30 °C | R/W |
| `0x06A0` | 1696 | PU09 | Compressor as second step | x1 | 0…1  | R/W 0/1 |
| `0x06A1` | 1697 | PU10 | Delay before compressor second step | x1 | 0…240 min | R/W |
| `0x06A3` | 1699 | PS02 | Outdoor damper pre-start time | x1 | 0…9999 s | R/W, disabled by default |
| `0x06A5` | 1701 | PS04 | External damper min opening | x0.01 | 0…100 % | R/W, disabled by default |
| `0x06A6` | 1702 | PS05 | External damper max opening | x0.01 | 0…100 % | R/W, disabled by default |
| `0x06A7` | 1703 | PS06 | Free-cooling/heating activation setpoint | x0.1 | 0…20 °C | R/W, disabled by default |
| `0x06A8` | 1704 | PS07 | Free-cooling/heating differential | x0.1 | 0…20 °C | R/W, disabled by default |
| `0x06A9` | 1705 | PS08 | External damper step at high humidity | x0.01 | 1…100 % | R/W, disabled by default |
| `0x06AA` | 1706 | PS09 | External damper step interval | x1 | 1…100 s | R/W, disabled by default |
| `0x06AB` | 1707 | Pr01 | Rotary exchanger setpoint differential | x0.1 | 0…20 °C | R/W, disabled by default |
| `0x06AC` | 1708 | Pr02 | Rotary exchanger differential | x0.1 | 0…20 °C | R/W, disabled by default |
| `0x06AD` | 1709 | Pr03 | Exchanger defrost setpoint | x0.1 | -15…70 °C | R/W, disabled by default |
| `0x06AE` | 1710 | Pr04 | Exchanger defrost dead band | x0.1 | 0…20 °C | R/W, disabled by default |
| `0x06AF` | 1711 | Pr05 | Cross-flow bypass cycle time | x1 | 1…99 s | R/W, disabled by default |
| `0x06B0` | 1712 | Pr06 | Exchanger stop setpoint | x0.1 | -15…70 °C | R/W, disabled by default |
| `0x06B1` | 1713 | Pr07 | Exchanger stop differential | x0.1 | 0…20 °C | R/W, disabled by default |
| `0x06B2` | 1714 | Pr08 | Rotary exchanger defrost step | x0.01 | 0…100 % | R/W, disabled by default |
| `0x06B3` | 1715 | Pr09 | Rotary exchanger defrost interval | x1 | 1…100 s | R/W, disabled by default |
| `0x06B4` | 1716 | Pr10 | Rotary exchanger PWM frequency | x1 | 1…2000 Hz | R/W, disabled by default |
| `0x06B5` | 1717 | PA01 | Fan hours alarm | x1 | 0…1  | R/W 0/1 |
| `0x06B6` | 1718 | PA02 | Compressor hours alarm | x1 | 0…1  | R/W 0/1 |
| `0x06B7` | 1719 | PA03 | Hours alarm relay (0 none, 1 light, 2 serious) | x1 | 0…2  | R/W |
| `0x06B8` | 1720 | PA04 | Probe alarm delay | x1 | 0…240 s | R/W |
| `0x06B9` | 1721 | PA05 | Probe alarm relay | x1 | 0…2  | R/W |
| `0x06BA` | 1722 | PA06 | Air-flow alarm delay after reset | x1 | 0…999 s | R/W |
| `0x06BB` | 1723 | PA07 | Air-flow alarm delay | x1 | 0…999 s | R/W |
| `0x06BC` | 1724 | PA08 | Air-flow alarm relay | x1 | 0…2  | R/W |
| `0x06BD` | 1725 | PA09 | Water-flow alarm delay after reset | x1 | 0…999 s | R/W |
| `0x06BE` | 1726 | PA10 | Water-flow alarm delay | x1 | 0…999 s | R/W |
| `0x06BF` | 1727 | PA11 | Water-flow alarms per hour before manual reset | x1 | 0…5  | R/W |
| `0x06C0` | 1728 | PA12 | Water-flow alarm relay | x1 | 0…2  | R/W |
| `0x06C1` | 1729 | PA13 | Filter alarm delay | x1 | 0…999 s | R/W |
| `0x06C2` | 1730 | PA14 | Filter alarm reset type | x1 | 0…2  | R/W |
| `0x06C3` | 1731 | PA15 | Filter alarm relay | x1 | 0…2  | R/W |
| `0x06C4` | 1732 | PA16 | High/low water temperature alarm delay | x1 | 1…999 s | R/W |
| `0x06C5` | 1733 | PA17 | High/low water temperature alarm differential | x0.1 | 0.1…10 °C | R/W |
| `0x06C6` | 1734 | PA18 | High/low water temperature alarm relay | x1 | 0…2  | R/W |
| `0x06C7` | 1735 | PA19 | High humidity warning setpoint | x1 | 0…100 % | R/W |
| `0x06C9` | 1737 | PA21 | High humidity time before alarm | x1 | 0…60 min | R/W |
| `0x06CA` | 1738 | PA22 | High humidity events | x1 | 0…99  | R/W |
| `0x06CB` | 1739 | PA23 | Fan speed sensor alarm delay after reset | x1 | 0…999 s | R/W |
| `0x06CC` | 1740 | PA24 | Fan speed sensor alarm delay | x1 | 0…999 s | R/W |
| `0x06CD` | 1741 | PA25 | Fan max speed for speed sensor alarm | x1 | 0…9999 rpm | R/W |
| `0x06CE` | 1742 | PA26 | Fan alarm relay | x1 | 0…2  | R/W |
| `0x06CF` | 1743 | PA27 | Compressor thermal switch alarm delay | x1 | 0…999 s | R/W |
| `0x06D0` | 1744 | PA28 | Compressor thermal switch reset type | x1 | 0…2  | R/W |
| `0x06D1` | 1745 | PA29 | Compressor thermal switch relay | x1 | 0…2  | R/W |
| `0x06D2` | 1746 | PA30 | Low-pressure alarm bypass time | x1 | 0…999 s | R/W |
| `0x06D3` | 1747 | PA31 | Low-pressure alarm delay | x1 | 0…999 s | R/W |
| `0x06D4` | 1748 | PA32 | Low-pressure alarms per hour before manual reset | x1 | 0…5  | R/W |
| `0x06D5` | 1749 | PA33 | High-pressure alarm setpoint | x0.1 | 16…45 bar | R/W |
| `0x06D6` | 1750 | PA34 | High-pressure alarm differential | x0.1 | 0.1…10 bar | R/W |
| `0x06D7` | 1751 | PA35 | High-pressure alarms per hour before manual reset | x1 | 0…5  | R/W |
| `0x06D8` | 1752 | PA36 | Pressure alarm relay | x1 | 0…2  | R/W |
| `0x06D9` | 1753 | PA37 | Discharge temperature alarm delay | x1 | 0…999 s | R/W |
| `0x06DA` | 1754 | PA38 | Discharge temperature alarm setpoint | x0.1 | 70…140 °C | R/W |
| `0x06DB` | 1755 | PA39 | Discharge temperature alarm differential | x0.1 | 10…30 °C | R/W |
| `0x06DC` | 1756 | PA40 | Discharge temperature alarms per hour | x1 | 0…5  | R/W |
| `0x06DD` | 1757 | PA41 | Discharge temperature alarm relay | x1 | 0…2  | R/W |
| `0x06DE` | 1758 | PA42 | Antifreeze alarm delay | x1 | 0…999 s | R/W |
| `0x06DF` | 1759 | PA43 | Antifreeze water temperature setpoint | x0.1 | 0…20 °C | R/W |
| `0x06E0` | 1760 | PA44 | Antifreeze differential | x0.1 | 0.1…10 °C | R/W |
| `0x06E1` | 1761 | PA45 | Antifreeze alarm relay | x1 | 0…2  | R/W |
| `0x06E2` | 1762 | PA46 | Fire/smoke alarm type | x1 | 0…1  | R/W, disabled by default |
| `0x06E3` | 1763 | PA47 | Fire/smoke alarm relay | x1 | 0…2  | R/W, disabled by default |
| `0x06E4` | 1764 | PA48 | Generic warning delay | x1 | 0…999 s | R/W |
| `0x06E5` | 1765 | PA49 | Generic warning reset type | x1 | 0…2  | R/W |
| `0x06E6` | 1766 | PA50 | Generic alarm delay | x1 | 0…999 s | R/W |
| `0x06E7` | 1767 | PA51 | Generic alarm reset type | x1 | 0…2  | R/W |
| `0x06E8` | 1768 | PA52 | Clock (RTC) alarm | x1 | 0…1  | R/W 0/1 |
| `0x06E9` | 1769 | PA53 | Clock alarm reset type | x1 | 0…2  | R/W |
| `0x06EB` | 1771 | PA55 | Phase sequence alarm relay | x1 | 0…2  | R/W, disabled by default |
| `0x06EC` | 1772 | PA56 | Expansion alarm relay | x1 | 0…2  | R/W, disabled by default |
| `0x06ED` | 1773 | PH11 | Modbus address | x1 | 1…247  | shown R/O |
| `0x06EE` | 1774 | PH12 | Modbus baud rate code | x1 | 0…7  | shown R/O |
| `0x06EF` | 1775 | PH13 | Modbus parity code | x1 | 0…2  | shown R/O |
| `0x06F0` | 1776 | PH14 | Modbus stop bits code | x1 | 0…1  | shown R/O |
| `0x06F4` | 1780 | PH04 | Unit state on holiday (0 off, 1 on) | x1 | 0…1  | R/W |
| `0x06F6` | 1782 | PH06 | Pressure unit (0 bar, 1 psi) | x1 | 0…1  | shown R/O |
| `0x06F7` | 1783 | PH07 | Summer setpoint min | x0.1 | -15…70 °C | R/W |
| `0x06F8` | 1784 | PH08 | Summer setpoint max | x0.1 | -15…70 °C | R/W |
| `0x06F9` | 1785 | PH09 | Winter setpoint min | x0.1 | -15…70 °C | R/W |
| `0x06FA` | 1786 | PH10 | Winter setpoint max (caps SEtH; factory 14 °C, so the unit still heats by itself below 14 °C − PF12) | x0.1 | -15…70 °C | R/W |
| `0x06FC` | 1788 | PH16 | CAN baud rate code | x1 | 1…4  | shown R/O, disabled by default |
| `0x06FD` | 1789 | PH17 | CAN node | x1 | 1…127  | shown R/O, disabled by default |
| `0x06FF` | 1791 | PH19 | Air quality probe min | x1 | 0…9999  | shown R/O, disabled by default |
| `0x0700` | 1792 | PH20 | Air quality probe max | x1 | 0…9999  | shown R/O, disabled by default |
| `0x0701` | 1793 | PH21 | Pressure probe min | x0.1 | 0…87 bar | shown R/O, disabled by default |
| `0x0702` | 1794 | PH22 | Pressure probe max | x0.1 | 0…87 bar | shown R/O, disabled by default |
| `0x0703` | 1795 | PH23 | EVCO LED | x1 | 0…1  | R/W 0/1, disabled by default |
| `0x0708` | 1800 | PG04 | Heat exchanger type | x1 | 0…2  | shown R/O, disabled by default |
| `0x0709` | 1801 | PG05 | Expansion module | x1 | 0…1  | shown R/O, disabled by default |
| `0x070C` | 1804 | HA01 | AI1 allocation (fan potentiometer) | x1 | 0…60  | shown R/O |
| `0x070F` | 1807 | HA04 | AI4 allocation (evaporator temperature) | x1 | 0…52  | shown R/O |
| `0x0710` | 1808 | HA05 | AI5 allocation (water temperature) | x1 | 0…52  | shown R/O |
| `0x0711` | 1809 | HA06 | AI6 allocation (dehumidify request DI) | x1 | 0…52  | shown R/O |
| `0x0712` | 1810 | HA07 | AI7 allocation (integration request DI) | x1 | 0…52  | shown R/O |
| `0x0713` | 1811 | HA08 | AI1 Epj allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x0714` | 1812 | HA09 | AI2 Epj allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x0715` | 1813 | HA10 | AI1 expansion allocation | x1 | 0…60  | shown R/O, disabled by default |
| `0x0716` | 1814 | HA11 | AI2 expansion allocation | x1 | 0…60  | shown R/O, disabled by default |
| `0x0717` | 1815 | HA12 | AI3 expansion allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x0718` | 1816 | HA13 | AI4 expansion allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x0719` | 1817 | HA14 | AI5 expansion allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x071A` | 1818 | HA15 | AI6 expansion allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x071B` | 1819 | HA16 | AI7 expansion allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x071C` | 1820 | HA17 | AI1 Evj allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x071D` | 1821 | HA18 | AI2 Evj allocation | x1 | 0…52  | shown R/O, disabled by default |
| `0x071E` | 1822 | HB01 | DI1 allocation (high pressure) | x1 | 0…46  | shown R/O |
| `0x071F` | 1823 | HB02 | DI2 allocation (low pressure) | x1 | 0…46  | shown R/O |
| `0x0722` | 1826 | HB05 | DI1 expansion allocation | x1 | 0…46  | shown R/O, disabled by default |
| `0x0723` | 1827 | HB06 | DI2 expansion allocation | x1 | 0…46  | shown R/O, disabled by default |
| `0x0724` | 1828 | HB07 | DI3 expansion allocation | x1 | 0…46  | shown R/O, disabled by default |
| `0x0725` | 1829 | HC01 | AO1 allocation (compressor) | x1 | 0…7  | shown R/O |
| `0x0726` | 1830 | HC02 | AO2 allocation | x1 | 0…7  | shown R/O |
| `0x0727` | 1831 | HC03 | AO3 allocation | x1 | 0…7  | shown R/O |
| `0x0729` | 1833 | HC05 | AO1 expansion allocation | x1 | 0…7  | shown R/O, disabled by default |
| `0x072A` | 1834 | HC06 | AO2 expansion allocation | x1 | 0…7  | shown R/O, disabled by default |
| `0x072B` | 1835 | HCF1 | Supply fan PWM frequency | x1 | 10…2000 Hz | shown R/O, disabled by default |
| `0x072C` | 1836 | HCF2 | Return fan PWM frequency | x1 | 10…2000 Hz | shown R/O, disabled by default |
| `0x072D` | 1837 | HCF3 | Compressor PWM frequency | x1 | 10…2000 Hz | shown R/O, disabled by default |
| `0x072F` | 1839 | HD02 | DO2 allocation (serious alarm) | x1 | 0…30  | shown R/O |
| `0x0730` | 1840 | HD03 | DO3 allocation (VMC contact) | x1 | 0…30  | shown R/O |
| `0x0731` | 1841 | HD04 | DO4 allocation (water condensation valve) | x1 | 0…30  | shown R/O |
| `0x0732` | 1842 | HD05 | DO5 allocation (external water valve / pump) | x1 | 0…30  | shown R/O |
| `0x0733` | 1843 | HD06 | DO6 allocation (compressor) | x1 | 0…30  | shown R/O |
| `0x0734` | 1844 | HD07 | DO1 expansion allocation | x1 | 0…30  | shown R/O, disabled by default |
| `0x0735` | 1845 | HD08 | DO2 expansion allocation | x1 | 0…30  | shown R/O, disabled by default |
| `0x0736` | 1846 | HD09 | DO3 expansion allocation | x1 | 0…30  | shown R/O, disabled by default |
| `0x0737` | 1847 | HD10 | DO4 expansion allocation | x1 | 0…30  | shown R/O, disabled by default |
| `0x0738` | 1848 | HD11 | Open-collector expansion allocation | x1 | 0…30  | shown R/O, disabled by default |
| `0x0739` | 1849 | Pb07 | Anti-stagnation valve active time | x1 | 1…999 s | R/W |
| `0x073A` | 1850 | Pb08 | Anti-stagnation valve wait time | x1 | 1…99 min | R/W |
| `0x073B` | 1851 | PE21 | Compressor min output (integration) | x0.01 | 0…100 % | R/W |
| `0x073E` | 1854 | PF29 | Return fan min speed | x0.01 | 0…100 % | R/W, disabled by default |
| `0x073F` | 1855 | PF30 | Return fan max speed | x0.01 | 0…100 % | R/W, disabled by default |
| `0x0740` | 1856 | PF31 | Integration fan control (0 temperature, 1 max of manual/remote, 2 max of all) | x1 | 0…2  | R/W |
| `0x0741` | 1857 | PF32 | Return fan speed forced by DI | x0.01 | 0…100 % | R/W, disabled by default |
| `0x0742` | 1858 | PM22 | Return fan manual setpoint | x0.01 | 0…100 % | R/W, disabled by default |
| `0x0746` | 1862 | PF33 | Return fan speed on air quality probe fault | x0.01 | 0…100 % | R/W, disabled by default |
| `0x0747` | 1863 | PF34 | Return fan post-run speed | x0.01 | 0…100 % | R/W, disabled by default |
| `0x0748` | 1864 | PM91 | Free-cooling probe offset | x0.1 | -10…10 °C | R/W, disabled by default |
| `0x0749` | 1865 | PM92 | Evaporator probe offset | x0.1 | -10…10 °C | R/W |
| `0x074A` | 1866 | PH24 | Evaporation pressure probe min | x0.1 | 0…87 bar | shown R/O, disabled by default |
| `0x074B` | 1867 | PH25 | Evaporation pressure probe max | x0.1 | 0…87 bar | shown R/O, disabled by default |
| `0x074C` | 1868 | PH26 | Refrigerant code | x1 | 0…19  | shown R/O |
| `0x074F` | 1871 | PE22 | Compressor max output (integration) | x0.01 | 0…100 % | R/W |
| `0x0751` | 1873 | PU11 | Evaporator temperature setpoint | x0.1 | 0…68 °C | R/W |
| `0x0752` | 1874 | PU12 | Evaporator dead band | x0.1 | 0.1…18 °C | R/W |
| `0x0754` | 1876 | PA57 | High humidity alarm type (0 display, 1 blocking) | x1 | 0…1  | R/W |
| `0x0755` | 1877 | PA58 | Max dehumidify time forced by DI | x1 | 0…999 min | R/W |
| `0x0757` | 1879 | PE24 | Compressor speed ramp | x0.1 | 0…20 rps | R/W |
| `0x0758` | 1880 | PE25 | Compressor ramp-down on alarm or off | x0.1 | 0…20 rps | R/W |
| `0x0759` | 1881 | PE26 | Ramp to and from minimum step | x0.1 | 0…20 rps | R/W |
| `0x075A` | 1882 | PE27 | Compressor max speed | x1 | 0…200 rps | R/W |
| `0x075B` | 1883 | PE28 | Compressor step 1 speed | x1 | 0…200 rps | R/W |
| `0x075D` | 1885 | PE30 | Minimum time at step 1 | x1 | 0…255 s | R/W |
| `0x075E` | 1886 | PE31 | Minimum time at step 2 | x1 | 0…255 s | R/W |
| `0x075F` | 1887 | PE32 | Maximum time below step 1 | x1 | 0…255 s | R/W |
| `0x0760` | 1888 | PE33 | Compressor speed (rps) control | x1 | 0…1  | R/W 0/1 |
| `0x0763` | 1891 | PA59 | Alarm relay (0 always, 1 summer only) | x1 | 0…1  | R/W |
| `0x0768` | 1896 | PA60 | Auto-reset delay of high humidity block | x1 | 0…9999 s | R/W |
| `0x0769` | 1897 | PT01 | Test mode enabled | x1 | 0…1  | shown R/O, disabled by default |
| `0x076A` | 1898 | PT02 | Supply fan speed in test mode | x0.01 | 0…100 % | shown R/O, disabled by default |
| `0x076B` | 1899 | PT03 | Return fan speed in test mode | x0.01 | 0…100 % | shown R/O, disabled by default |
| `0x076C` | 1900 | PT04 | External damper in test mode | x0.01 | 0…100 % | shown R/O, disabled by default |
