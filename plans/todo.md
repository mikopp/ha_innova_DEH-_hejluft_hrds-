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
- [ ] **`recirculation_active` (reg 1112) is a 0/1 flag**, not a 0–100 %
      value. It sits next to the 0–100 % fan-request registers; if hardware shows
      a percentage, change it from a binary sensor to a `sensor` with
      `FAKTOR: 0.01`. (See `const.py` `C_RECIRCULATION_ACTIVE`.)
- [ ] **Air quality (506)** unit/scale and whether the probe is even fitted.
      The device class is now left unset: `AQI` accepts only a `None` unit in
      Home Assistant, so pairing it with "ppm" was invalid. If the probe turns
      out to be CO₂, `SensorDeviceClass.CO2` is the right pairing for ppm.
- [ ] **`PF01_MinTimeOnFan` (1638) / `PF03_MinTimePostFan` (1640) are in
      seconds.** The unit is inferred from the parameter's 0–999 range and the
      technical manual's wording ("Mindestlaufzeit" / "Nachlauf"); the Modbus
      table does not state it. Confirm against the wired display.

## Addressing & transport

- [ ] **Direct PDU addressing — no −1 offset.** Confirm `address=1105` really hits
      `Status_OnOff_byBMS` and not an off-by-one neighbour.
- [ ] **Block-read chunking** (`C_MAX_BLOCK=120`, `C_MAX_GAP=8` in `__init__.py`).
      Confirm the real gateway accepts these block sizes without timeouts across
      the sparse map; tune if needed. Blocks no longer span an address belonging
      to the other function code, and a block that errors now falls back to
      per-register reads, so a single "illegal data address" no longer blanks
      every entity — but it is still worth knowing which addresses do that.
- [ ] **Modbus slave id / port** defaults (1 / 502) match the deployed gateway.
- [ ] Temp/humidity readings require a **wired display or external probes**.
      Confirm which probes the target install actually has, and which sensors
      read as unavailable without them.

## BMS enables

- [ ] **PH02 (1778) / PH27 (1869) / PH28 (1870) must be set before writes are
      honoured.** Confirm `_sync_bms_enables_locked()` actually unlocks on/off,
      dehumidify and cooling. The hub now re-asserts these every poll from the
      read-back, so a power-cycle that clears them should self-heal within one
      scan interval — verify that it does, by power-cycling the unit and then
      issuing a write.
- [ ] Confirm an **OFF command always wins** over an ON from any source
      (display/DI/Modbus), per the manual.
- [ ] **`PU13_MinTRoom_disableDEU` (1889) can veto a Modbus dehumidify request.**
      The unit disables dehumidification below this room temperature. On a unit
      with no room probe, confirm whether a Modbus request still starts the
      compressor, and whether setting PU13 to 0 lifts the interlock. This is the
      most likely cause of "the write was accepted but nothing happened".

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

Read-back maps the **commanded** speed (`PM20_SupplyFan_Manual`, 1614) to the
nearest preset via midpoint thresholds (42.5 / 70.0 %). `fan.hrds_supply_fan`
reads the same register, so the two entities always agree; `outAO_SupplyFan`
(639) is the unit's *actual* modulated output and is exposed separately as a
sensor and as the fan entity's `actual_output_percent` attribute.

The gap between those two is the interesting measurement: if 639 does not track
1614, the unit is clamping the commanded speed into its own band.

- [x] **Core assumption: compressor/dehumidify can run on passive MVHR flow
      alone (no unit fan running)** — this is architecturally confirmed: the
      non-`R` variant (no recirc fan installed) always operates this way. The
      compressor dehumidifies and cools with MVHR passive flow only, by design.
- [ ] **Open firmware question (R variant only):** When `Status_Dehum_byBMS`
      (1140) = 1 with fan mode set to off, does the firmware honour `1614 = 0`
      or silently clamp the fan output up to `MinSpeedFan_Dehum` (1853)?
      Verify: write 0 to 1614 while dehumidify is active, then read
      `outAO_SupplyFan` (639). Non-zero = firmware clamped.

      Easiest way to run this now: `fan.hrds_supply_fan` reports the
      **commanded** percentage and carries the unit's actual output in its
      `actual_output_percent` attribute, so sweep `fan.set_percentage` across
      30 / 60 / 95 % and watch the two diverge on a single entity. If the
      firmware clamps, an external controller cannot use PM20 as its airflow
      lever and must drive the band registers (`fan_min_speed_dehumidify` 1853 /
      `fan_max_speed_dehumidify` 1647) instead — `fan.py` keeps the write in one
      method so that fallback can be added there.
- [ ] Confirm `SupplyFan_Status` (1119) reports `1` (OFF) when fan mode = off
      and a mode is active, and that `recirculation_active` (1112) goes 0.
- [ ] Verify the Low / Medium / High percentages (30 / 55 / 85 %) are
      reasonable for the real unit; adjust in `climate.py` `_FAN_MODE_PCT` if
      not. These are nominal choices, not values from the PDF.

## Entities documented but not yet exposed

- [ ] **Exhaust air temp (502)** and **evaporator temp (511)** are in the
      register map but not in `ENTITIES_DICT` — add as sensors if useful.
- [ ] **Alarm detail**: only the cumulative `alarm_active` (1103) is exposed.
      The per-bit alarm bitmaps `PackedAlarm_1/2/3` (768/769/770) and the
      `BMS_ALxx` reset registers are not decoded into entities yet.
- [ ] **Season / operating-mode change**: only the R/O feedback (1583) is
      exposed. Writing the season via `DI4_Configuration` (1825, only 3/4 valid)
      and the `PriorityChangeMode` (1878) ownership flag are not implemented.
- [ ] **Manual fan request / remote request** (1114 / 1116, R/O) are not exposed.
- [x] Recirculation damper status (1134) — now exposed as `sensor.recirculation_damper`.
