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
| `0x06F1` | 1777 | `Enable_OnOffByDisplay`   | R/W | **PH01** — set `0` if no wired display is present. While `1` with no display the unit stays `sm_UnitStatus` = `0` (OFF by display) permanently, and an OFF from any source beats a Modbus ON. Factory value is `1`. The integration sets it to `0` in headless mode (the default). |
| `0x070B` | 1803 | `T/H Probe Source` (HA00) | R/W | Source for temp/humidity probes: `0=None`, `6=CNU2 display` (factory default; a unit seen in the field read `2`). Set `0` if no display. The integration sets it to `0` in headless mode. |

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
| `0x066C` | 1644 | `MinSpeedSupplyFan_VMC` (PF07) | R/W | — | 0–100 | Supply-fan min speed in VMC (ventilation-only) mode |
| `0x066E` | 1646 | `MaxSpeedFan_Integ` (PF09) | R/W | 85.00 | 0–100 | Supply-fan max speed in integration (cooling) |
| `0x064E` | 1614 | `PM20_SupplyFan_Manual`    | R/W | — | 0–100 | Manual supply-fan setpoint |
| `0x045A` | 1114 | `SupplyFan_ManualRequest`  | R/O | — | 0–100 | Current manual fan request |
| `0x045C` | 1116 | `SupplyFan_RemoteRequest`  | R/O | — | 0–100 | Current potentiometer fan request |
| `0x027F` | 639  | `outAO_SupplyFan`          | R/O | — | 0–100 | Actual supply-fan analog output % |
| `0x045D` | 1117 | `actRPMsupplyFan`          | R/O | — | 0–65535 | Supply-fan actual RPM |

### 6.1 The min/max band is a scaling range, not just a clamp

`HRDS+_Technisches_Handbuch_DE.txt` § Lüfter-Regelung, on manual fan control:

> „Die Drehzahl wird **linear zwischen den jeweiligen Minimal- und
> Maximalwerten** (PF28/PF10 bzw. PF27/PF09) **skaliert**."

So the manual request is a **position within the active mode's band**, not an
absolute percentage. At the factory band (50–85 %) a request of 30 would produce
roughly `50 + 0.30 × (85 − 50) ≈ 60.5 %` actual output, and a request of 0 would
produce 50 %, **not** a stopped fan.

That passage describes manual control *at the display*. `PM20_SupplyFan_Manual`
(1614) is the Modbus manual setpoint and `SupplyFan_ManualRequest` (1114) is
documented as the "manual display request", which strongly suggests they feed the
same logic — but **this has not been confirmed on hardware**. See `plans/todo.md`.

Consequences if it holds:

* To command an absolute percentage, first open the band: set the mode's minimum
  (`PF28` 1853 dehumidify, `PF27` 1852 integration, `PF07` 1644 VMC) to `0` and
  the maximum (`PF10` 1647 / `PF09` 1646) to `100`. Then request == output.
* To actually stop the fan, the minimum must be `0`; otherwise the floor applies.
* `outAO_SupplyFan` (639) is the only trustworthy reading of what the fan is
  doing. The integration's `fan` and `climate` entities both report it for that
  reason, and expose the commanded value separately.

**The per-mode minimum is device state, not integration state.** All three minima
are writable holding registers and are exposed as `number` entities; the
integration deliberately does not carry its own "fan is off below X %" setting,
which would shadow them.

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
| `0x0464` | 1124 | `outDO_WaterCond` | Internal water condenser valve (relay K4): `0=OFF`, `1=ON`, `2=Disable`. ON = closed, all compressor heat to the water (summer integration). |
| `0x0466` | 1126 | `outDO_WaterFlow` | External water valve V3V (relay K5) — the PM pump output is switched together with it: `0=OFF`, `1=ON`, `2=Disable` (not configured: the unit cannot start the pump). |
| `0x046E` | 1134 | `outDO_RecircDamper` | `0=OFF` (damper closed — room-air duct sealed, MVHR passive flow only), `1=ON` (damper open — room air blended with MVHR inflow), `2=Disable` (no damper wired, non-`R` variant) |
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
| `0x0705` | 1797 | `PG01_MachineType` | Fan arrangement: `0=supply fan only`, `1=supply fan + exhaust fan` (handbook PG01: „Entfeuchter nur mit Zuluftventilator“ / „mit Zuluft- und Abluftventilator“). **Not** "has a recirculation fan": an `R` unit reads `0` (its one fan is the recirculation fan). Use `outDO_RecircDamper` (1134) for that — `2=Disable` means no damper wired. Verified on an HRDS+ 30 `R`: PG01 = 0 with the damper output present (1134 = 0). |
| `0x0706` | 1798 | `PG02_EnableIntegration` | Enable the active-cooling integration function |
| `0x0699` | 1689 | `PU02_EnableWinterDehum` | `0=No`, `1=With water`, `2=Without water` |
| `0x069C` | 1692 | `PU05_ForceDehumInCooling` | Force dehumidify when cooling requested |
| `0x06F5` | 1781 | `PH05_TemperatureUM` | `0=°C`, `1=°F` |
| `0x06F3` | 1779 | `PH03_EnableTimePrograms` | `0=No`, `1=Yes`. Time programs can switch the unit OFF (status `off_by_scheduler`). Exposed as a switch; the integration flags it in the setup check. |
| `0x070D` | 1805 | `HA02_AI2_Allocation` | Analog input 2 allocation. `0`=unused, `45`=room temperature probe. A probe code with nothing wired raises AL28. Exposed as a writable number. |
| `0x070E` | 1806 | `HA03_AI3_Allocation` | Analog input 3 allocation. `0`=unused, `53`/`54`=room humidity probe. A probe code with nothing wired raises AL34. Exposed as a writable number. |
| `0x0720` | 1824 | `DI3_Configuration` (HB03) | Remote ON/OFF contact (OFF/OFF terminals): `0=unused`, `1=normally closed`, `2=normally open`. With the contact open the unit is forced OFF (`off_by_di`). Shown read-only. |
| `0x0728` | 1832 | `HC04` | Analog output allocation of the supply fan (raw code; `1` = 0-10 V supply fan). Shown read-only. |
| `0x072E` | 1838 | `HD01` | Relay DO1 allocation (raw code; `10` = recirculation damper NO, `9` = NC). Shown read-only. |
| `0x06A2` | 1698 | `PS01_PreStartTime_RecircDamper` | Damper pre-start time before the fan starts, in seconds (default 20). Shown read-only. |
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
  in **contiguous chunks** per function code, not one big block. Keep the
  chunks small: a real unit behind an RS-485 gateway did not answer a
  120-register read at all, while 10-register reads covered the whole map.
  The integration reads at most 10 per request and halves that if a block
  goes unanswered while a single register answers promptly.
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

> **Read §13.5 first.** The three-way split below is this repository's own
> reading, not manufacturer terminology. On the `R` variant the controller does
> **not** treat recirculation as a separate mode: every dehumidification or
> integration request opens the recirculation damper and starts the fan. There
> is no documented way to dehumidify on passive MVHR flow with the damper closed.

### 13.1 Three concepts, three meanings

| Concept | What physically happens | How it is exposed |
|---------|-------------------------|-------------------|
| **Passive airflow** | The unit's own supply fan is **off**, but the central MVHR upstream still pushes air through the unit's duct, so air keeps flowing through the inflow pipe. On the `R` variant this is the **OFF / ON-Standby** state („ohne Luftaufbereitung“, no air treatment, §2.7); on the non-`R` variant it is the only state. | **No dedicated register.** Infer it: `SupplyFan_Status` (1119) = `1` (OFF) while `sm_UnitStatus` (1104) = `5` (ON). The unit cannot measure the upstream MVHR's flow, so there is no "passive flow rate". |
| **Fan integration** (the *fan's* job) | The unit's **own supply fan runs** to "integrate" — i.e. blend the central-MVHR inflow air with recirculated room air and drive it across the coil. On the `R` variant this happens on **every** dehumidification and integration request (§13.5). | `FanIntegration_Request` (1112) = `1` when the fan-integration function is active; `SupplyFan_Status` (1119) = `3` (ON); modulation at `outAO_SupplyFan` (639, ×0.01 %) and `actRPMsupplyFan` (1117). The Modbus PDF labels 1112 only "Fans integration request" (R/O); the blending interpretation is ours. |
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

**Fan mode "off" does not give passive-only dehumidification.** Even if
`1614 = 0` stopped the fan, the recirculation damper still opens on every
dehumidification/integration request (§13.5). A user report also says the fan
could not be commanded below 30 %. Whether the remaining floor is a clamp to
`MinSpeedFan_Dehum` (1853) / `MinSpeedFan_Integ` (1852) or a band rescale is
still unverified on hardware — see `plans/todo.md`.

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
On a stock `R` unit this condition only holds while no dehumidification or
integration request is active, i.e. while the air passes untreated.

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

### 13.5 Dehumidifying without recirculation (`R` variant)

**The manufacturer documentation has no such mode.** Dehumidification and
recirculation are coupled in the controller:

* **Handbuch §2.7 Betriebsarten.** The dehumidify mode (DEU) and both
  integration modes (INT summer, INT winter) all list „die Umluftklappe ist
  geöffnet“ and „der Lüfter ist aktiv“. DEU says explicitly: „In diesem
  Betriebsmodus ist die Umluftumwälzung aktiviert“. Only OFF / ON-Standby
  („ohne Luftaufbereitung“) has the damper closed and the fan off. The mode
  pictures match: the closed-damper picture is the untreated standby state.
* **§6.5 Umluftklappe.** The damper opens whenever there is an integration or
  dehumidification request. It closes only once the request has ended, the
  compressor's safety times have elapsed and the external water valve has
  closed after its run-on. A blocking alarm closes it immediately.
* **§6.2 Lüfter-Regelung.** The fan starts only after the damper is fully open
  (`PS01_PreStartTime_RecircDamper`, reg 1698, default 20 s). It then runs in
  the PF28–PF10 band (dehumidify) or PF27–PF09 (integration).
* **"ohne Umluft" is a hardware variant**, not an operating mode: §2.1
  „Variante ohne Umluft“, §3.7.2 „Anschluss-Schema, Version ohne
  Umluftumwälzung“ and the separate „ohne Umluft“ product codes. Those units
  have no recirculation fan or damper.
* **Modbus.** No register selects "dehumidify without recirculation".
  `FanIntegration_Request` (1112) and `outDO_RecircDamper` (1134) are
  read-only status.

**Vendor statements** (energiesparhaus.at HRDS+ thread, user Murphy08, who
writes for the vendor side):

* #44 (4.12.2025): „Immer wenn der Kompressor läuft, ist auch der Umluftbetrieb
  aktiv.“
* #76 (8.5.2026): „Die Entfeuchtung ist regelungsseitig streng mit dem
  Umluftbetrieb gekoppelt.“ Start order: water valve, recirculation damper and
  VMC output first, then the fan after a delay, then the compressor.
* #78 (8.5.2026): setting the fan to 0 „bringt ja nichts, weil die Klappe dann
  trotzdem aufgeht“.

**Unofficial workaround** (user manuon, #77–#79 and #93, May 2026; untested by
this repository, at your own risk):

* The fan could not be commanded below 30 %.
* Deactivating the fan output (AO4) or the damper output (DO1) stops the
  compressor from starting.
* Fan: deactivate AO4 and assign the spare AO3 as "Supply Fan 0-10V", so the
  real fan stays off while the compressor runs.
* Damper: set `HD01` (DO1 allocation, default `10` = "Recirculation damper
  NO") to `9` = "Recirculation damper NC". This inverts the relay: the damper
  stays closed during operation but is open whenever it would normally be
  closed, which presumably includes standby.
* Reported result: an HRDS+ 50 running on KWL supply air alone at 368 m³/h,
  about 1.7 l/h of condensate.

**Consequences**

* Writing `PM20_SupplyFan_Manual` (1614) = 0 does not produce passive-only
  dehumidification. The damper opens regardless, and the fan is probably
  floored.
* If the recirculation inlet is not open to a room at about room pressure —
  for example, teed into the MVHR extract duct — an open damper with a stopped
  or slow fan short-circuits supply air into the extract. A backdraft valve in
  the recirculation branch, opening towards the unit, prevents that without
  parameter changes. The NC inversion is unsuitable there, because the damper
  would then be open in standby.
* In any fan-off configuration, the compressor's own protection (AL11
  low-pressure / frost thermostat) remains the guard against too little
  airflow.

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
> PH01 (1777) = 0 ("display not present"). Without this the unit stays OFF by
> display and waits for room T/H from a display that is not there (AL28/AL34
> may follow). The handbook (§5.1 and the commissioning checklist) gives the
> same pair: with CNU2 `PH01 = 1, HA00 = 6`; without CNU2 `PH01 = 0, HA00 = 0`.
> The HA integration does this itself unless the `has_display` option is set:
> it re-asserts PH01 = 0 and HA00 = 0 on every poll, like the BMS enables.
> Both are also exposed (`switch.enable_onoff_display`, `select.probe_source`),
> but in headless mode a manual change is undone on the next poll.

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
   **PH01 = 0** (disable display). The HA integration writes both itself when
   `has_display` is off (the default).
2. The HA integration auto-sets **PH02/PH27/PH28** = 1 on every connection,
   so on/off, dehumidify and cooling are controllable immediately.
3. Automatic setpoint-based control (trigger dehumidify when room humidity >
   PU01) does **not** function — there is no room sensor to compare against.
   Issue dehumidify / cooling requests **explicitly via Modbus** (the climate
   entity or individual switches).
4. `current_temperature` and `current_humidity` on the climate entity read
   `None`. An unwired input does not read 0: it reads a sentinel word
   (§14.7), which the integration decodes to "no value" (entity state
   `unknown`). The `temp_probe_ok` / `humidity_probe_ok` binary sensors depend
   on AL28/AL34, which were **not** raised on a real headless unit while it was
   OFF by display, so do not rely on them alone. This is expected, not an error.
5. The evaporator and water-circuit probes remain active (factory-wired) and
   continue to protect the unit against AL03/AL04/AL11/AL12.

### 14.7 Unwired analog inputs read a sentinel, not a temperature

Observed on an HRDS+ 30 with no display and no external probes (HA00 = 2,
PH01 = 1): `AI_TreturnRoom` (499), `AI_Toutdoor` (500), `AI_Texhaust` (502),
`AI_Tdischarge` (503), `AI_HretRoom` (505) and `AI_AirQuality` (506) all read raw
`32772` (`0x8004`); register 507 read `32762` (`0x7FFA`). Decoded as INT16 ×0.1
that is **-3276.4 °C** (and -32764 %RH), which is never a real reading. The
factory-wired `AI_Twater` (501) and `AI_Tevaporation` (511) read normally.

This sentinel is empirical, not in the manufacturer tables. The integration
treats any INT16 word in `0x7FF0..0x800F` (`PROBE_SENTINEL_LOW/HIGH` in
`const.py`) as "no value". Real readings cannot collide: that window is
±3276 °C. Negative temperatures are fine (-1.0 °C = `0xFFF6`).

---

## 15. Control parameters used by the HA integration

Extracted from `HRDS+_Modbus_RTU_RS485_DE.pdf` §6 (FULL MODBUS REGISTER LIST).
These are the parameters an external controller needs in order to reason about
what the unit will do on its own, rather than fighting it.

| Addr HEX | Addr DEC | Name | R/W | Range | Why it matters |
|----------|----------|------|-----|-------|----------------|
| `0x069E` | 1694 | `PU07_Dehumidity_Diff` | R/W | 0-100 %RH | The unit's **own** dehumidify hysteresis: the auto request turns on at `PU01 + PU07` and off at `PU01`. An external controller's hysteresis should not be narrower than this. |
| `0x0761` | 1889 | `PU13_MinTRoom_disableDEU` | R/W | 0-30.0 °C (×0.1) | **Minimum room temperature below which dehumidification is disabled.** This interlock applies to Modbus requests too, so on a unit with no room probe it can silently block a dehumidify command. |
| `0x0762` | 1890 | `PU14_TRoomDIFF_enableDEU` | R/W | 0.1-20.0 °C (×0.1) | Differential above `PU13` at which dehumidification is re-enabled. |
| `0x0666` | 1638 | `PF01_MinTimeOnFan` | R/W | 0-999 s | **Device-side minimum fan runtime.** The fan stays on for this long even if the request clears, so the unit already provides anti-short-cycling. |
| `0x0668` | 1640 | `PF03_MinTimePostFan` | R/W | 0-999 s | Post-ventilation run-on after the compressor stops (`0` disables it). |
| `0x0707` | 1799 | `PG03_EnableFreeCoolingHeating` | R/W | `0=No`, `1=Yes` | Enables the Free-Cooling/Free-Heating function. **While this is `0` (the factory default), `AI_Toutdoor` (500) drives nothing** - it is display-only. |

> The `PF01`/`PF03` unit is inferred from the parameter's 0-999 range and the
> technical manual's description ("Mindestlaufzeit" / "Nachlauf"); it is not
> stated explicitly in the Modbus table. Confirm against the wired display
> before relying on the absolute value.

### 15.1 What this means for an external controller

* **Minimum runtime is already enforced by the unit** (`PF01`). A controller
  does not need its own compressor-protection timer, only hysteresis on its
  *decision* input.
* **`PU13` can veto a Modbus dehumidify request.** If a request appears to be
  accepted but the compressor never starts, read `PU13` and the room
  temperature before looking anywhere else.
* **`PU07` interacts with an external hysteresis band.** If the controller's
  band is narrower than `PU07`, the unit's own auto logic decides the edges.
* **`PG03` decides whether outdoor temperature is a control input.** Leave it
  at `0` if the central MVHR owns free cooling, as is the case when the HRDS+
  sits on that system's supply branch.

---

## 16. Installer-menu parameters (installer device)

Every handbook parameter (§5.3) that has a Modbus address in the RTU
manual's parameter table and is not already listed above. The integration
exposes them on the **installer** child device (`installer_params.py`).
Scaling was checked against a real unit's raw read-back. "shown R/O"
means the integration deliberately does not write it (link settings,
manufacturer I/O allocation, refrigerant, safety bypass, test mode).
Passwords (`PSd*`), `PH15` (restore defaults) and `PH18` (clear alarm
history) are not exposed. Addresses above 1900 are not read. The installer
device is opt-in, and its registers are never part of the regular poll: they
are read at setup and on the device's refresh button.

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
| `0x0662` | 1634 | PC08 | Min water temperature for winter integration | x0.1 | 0…70 °C | R/W |
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
| `0x06FA` | 1786 | PH10 | Winter setpoint max (factory 14 °C blocks auto heating) | x0.1 | -15…70 °C | R/W |
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
| `0x073A` | 1850 | Pb08 | Anti-stagnation valve wait time | x1 | 1…99 h | R/W |
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
