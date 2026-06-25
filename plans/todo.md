# TODO — verify against real hardware

The register map, scaling and behaviour in this integration were distilled from
the manufacturer PDFs in [`references/`](../references/), **not** validated on a
physical unit. This file collects every assumption, caveat and open question
that needs to be confirmed against a real HRDS+ / DEH+ before the integration
can be considered "tested". Tick items off (and fix the code/docs) as they are
verified on hardware.

## Scaling & data types

- [ ] **Fan / percentage registers use ×0.01** (write `4000` for 40 %). Confirm
      on the actual `outAO_SupplyFan` (639), the fan bands (1852/1853/1646/1647)
      and manual fan (1614). If the gateway already returns 0–100, drop `FAKTOR`.
- [ ] **Temperatures use ×0.1 °C** and are **INT16** (negative values possible).
      Verify sign handling on outdoor/water temps below 0 °C.
- [ ] **Humidity is integer %RH (no scale)** on both the room probe (505) and the
      setpoint (1586). Confirm no ×0.1.
- [ ] **`fan_integration_active` (reg 1112) is a 0/1 flag**, not a 0–100 %
      value. It sits next to the 0–100 % fan-request registers; if hardware shows
      a percentage, change it from a binary sensor to a `sensor` with
      `FAKTOR: 0.01`. (See `const.py` `C_FAN_INTEGRATION_ACTIVE`.)
- [ ] **Air quality (506)** unit/scale and whether the probe is even fitted;
      device_class `AQI` + "ppm" is a guess.

## Addressing & transport

- [ ] **Direct PDU addressing — no −1 offset.** Confirm `address=1105` really hits
      `Status_OnOff_byBMS` and not an off-by-one neighbour.
- [ ] **Block-read chunking** (`C_MAX_BLOCK=120`, `C_MAX_GAP=8` in `__init__.py`).
      Confirm the real gateway accepts these block sizes without timeouts or
      "illegal data address" errors across the sparse map; tune if needed.
- [ ] **Modbus slave id / port** defaults (1 / 502) match the deployed gateway.
- [ ] Temp/humidity readings require a **wired display or external probes**.
      Confirm which probes the target install actually has, and which sensors
      read as unavailable without them.

## BMS enables

- [ ] **PH02 (1778) / PH27 (1869) / PH28 (1870) must be set before writes are
      honoured.** Confirm the hub's once-per-connection
      `_enable_bms_control_locked()` actually unlocks on/off, dehumidify and
      cooling, and that the unit doesn't reset them on power-cycle.
- [ ] Confirm an **OFF command always wins** over an ON from any source
      (display/DI/Modbus), per the manual.

## Climate entity behaviour

- [ ] **Mode writes**: DRY = on + dehumidify + active_cooling **off**;
      COOL = on + dehumidify + active_cooling **on**; OFF = unit off. Confirm the
      combinations produce the expected unit behaviour and feedback.
- [ ] **`hvac_action` derivation** from `unit_status` / `compressor_status` /
      `dehumidify_request` reflects reality (DRYING vs COOLING vs IDLE vs OFF).
- [ ] **Target humidity** only acts while on + dehumidifying; **target
      temperature** (summer setpoint) only acts in COOL/summer. Confirm, and
      confirm the PH29/PH30 humidity clamps.
- [ ] **Summer/winter setpoint range**: `const.py` clamps to 15–35 °C, but the
      Modbus PDF lists Max `158.0`. Confirm the real usable range and adjust
      MIN/MAX/STEP if the device accepts more.

## Fan mode — implemented, needs hardware verification

The climate entity now exposes **fan_mode** (off / low / medium / high):

| Mode   | Manual fan speed written to reg 1614 |
|--------|--------------------------------------|
| off    | 0 %  |
| low    | 30 % |
| medium | 55 % |
| high   | 85 % |

Read-back maps `outAO_SupplyFan` (639) back to the nearest preset via midpoint
thresholds (42.5 / 70.0 %).

- [ ] **Core assumption: fan off (0 %) while DRY/COOL is active is supported
      by the unit**, relying on the central MVHR's passive inflow instead of the
      unit's own fan. User confirms this is believed correct — verify on hardware.
- [ ] Confirm that writing `1614 = 0` actually stops the fan while a mode is
      active, and is not clamped up to `MinSpeedFan_Dehum` (1853) /
      `MinSpeedFan_Integ` (1852) by the unit's internal logic.
- [ ] Confirm `SupplyFan_Status` (1119) reports `1` (OFF) when fan mode = off
      and a mode is active, and that `fan_integration_active` (1112) goes 0.
- [ ] Verify the Low / Medium / High percentages (30 / 55 / 85 %) are
      reasonable for the real unit; adjust in `climate.py` `_FAN_MODE_PCT` if
      not. These are nominal choices, not values from the PDF.
- [ ] Check whether `PG01_MachineType` (1797: 0=dehumidifier only, 1=+VMC)
      affects whether the fan can be set to off while a mode is active.

## Entities documented but not yet exposed

- [ ] **Exhaust air temp (502)** and **evaporator temp (511)** are in the
      register map but not in `ENTITIES_DICT` — add as sensors if useful.
- [ ] **Alarm detail**: only the cumulative `alarm_active` (1103) is exposed.
      The per-bit alarm bitmaps `PackedAlarm_1/2/3` (768/769/770) and the
      `BMS_ALxx` reset registers are not decoded into entities yet.
- [ ] **Season / operating-mode change**: only the R/O feedback (1583) is
      exposed. Writing the season via `DI4_Configuration` (1825, only 3/4 valid)
      and the `PriorityChangeMode` (1878) ownership flag are not implemented.
- [ ] **Manual fan request / remote request** (1114 / 1116, R/O) and the
      recirculation damper status (1134) are not exposed.
