# TODO — verify against real hardware

Most of the register map, scaling and unit behaviour was distilled from the
manufacturer PDFs in [`doc/references/`](../doc/references/). What has been seen on the
real unit so far is recorded in the evidence log of
[`doc/references/UNIT_BEHAVIOUR.md` §13](../doc/references/UNIT_BEHAVIOUR.md#13-evidence-log-what-was-seen-on-real-hardware).
This file collects the assumptions and open questions that still need a real
HRDS+ / DEH+. When an item is verified: tick it here, add a `T` row to that
evidence log, replace the `[INFERRED]` tags it settles, and fix the code/docs.

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
- [ ] **Block-read chunking** (`C_MAX_BLOCK=10`, `C_MAX_GAP=8` in `const.py`).
      120 failed on the real unit/gateway (no reply to `holding @ 1602+120`, so
      0.9.0 never loaded); 10 is what `diagnose_hrds.py` read the whole map
      with. The hub halves it on its own if a block is not answered. Find out
      the real limit (gateway or controller) and raise the cap if it is safe.
      Blocks no longer span an address belonging to the other function code, and a block that errors now falls back to
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

## Request read-back lag (added 2026-10-21)

- [ ] **How late does the unit mirror a request?** A real unit read the on/off
      request back as ON for several polls after OFF was written (switch and
      `unit_status` changed together at the same poll). The hub now shows the
      command until confirmed and re-reads at 3/6/12/25 s (`PENDING_RECHECK_SECONDS`).
      With debug logging for `custom_components.innova_hrds`, the line
      "HRDS+ confirmed <key>=<value> after N s" gives the real lag: size the
      schedule from it (and check whether OFF and ON lag alike).

## Headless operation, identity, sentinel (added 2026-10-19)

- [x] **PH01 = 0 does not clear `off_by_display` by itself** (2026-10-20, real
      unit, EPB9ORSINDEU V01.00.09.02). PH01 = 0, HA00 = 0, PH02 = 1 and a power
      cycle still read `off_by_display`; the first Modbus ON (`switch.unit_on_off`)
      moved it to `on` at once. The setup check now reports
      `unit_waiting_for_first_on` for this. Still open: does a Modbus OFF then read
      `off_by_bms`, and does it stay so across a power cycle.
- [ ] **HA00 = 0 on a unit that read 2** (the manual says the factory value is
      6). Confirm it is accepted and whether AL28/AL34 appear afterwards.
- [ ] **PH01 / HA00 are config parameters**: confirm that re-writing them only
      when the read-back differs (never blindly each poll) does not wear the
      controller's memory, and that the unit does not reset them on its own.
- [ ] **Sentinel window** `0x7FF0..0x800F`: only `0x8004` and `0x7FFA` have been
      seen. Confirm what a *failed* (wired but broken) probe reads, and whether
      it also raises AL28/AL34.
- [ ] **AL28/AL34 were not set** while the unit was OFF by display with no
      probes (PackedAlarm_2/3 = 0). Confirm they appear once the unit is ON.
- [ ] **PU13 with no room temperature**: does the interlock veto a Modbus
      dehumidify when the room input is the sentinel? If yes, set PU13 to 0.
- [ ] **Identity check**: the product-code prefix `EPB9` comes from one unit
      (`EPB9ORSINDEU`). Confirm other HRDS+ variants (30/50, non-R, non-DC)
      report an `EPB9…` code; loosen `EXPECTED_PRODUCT_PREFIX` if not. Also
      confirm what a gateway that does not forward FC 43 returns.

## Climate entity behaviour

- [ ] **Mode writes**: DRY = on + dehumidify + integration_request **off**;
      COOL = on + dehumidify + integration_request **on**; OFF = both requests off
      (unit off only if it could still act on its own). Confirm the
      combinations produce the expected unit behaviour and feedback.
- [ ] **`hvac_action` derivation** from `unit_status` / `compressor_status` /
      `dehumidify_request` reflects reality (DRYING vs COOLING vs IDLE vs OFF).
- [ ] **What does the condenser valve (1124, K4) read while cooling?** The
      Modbus manual says ON = all compressor heat to the water (summer
      integration), but the real HRDS+ 30 read `1` in standby, where the
      handbook (§6.4) says the valve stays deactivated. Note its value in
      standby, while dehumidifying and while cooling (COOL). If it reliably
      tells cooling from dehumidifying, `hub.is_cooling` can use it.
- [ ] **Winter heating evidence.** `hub.is_heating` needs the valve/pump output
      on, no AL04, compressor off and water at or above PC08. Confirm on a unit
      on a heating circuit that this is when the supply air actually warms, and
      that AL04 raises below PC08.
- [ ] **Target humidity** only acts while on + dehumidifying; **target
      temperature** (summer setpoint) only acts in COOL/summer. Confirm, and
      confirm the PH29/PH30 humidity clamps.
- [ ] **Summer/winter setpoint range**: `const.py` clamps to 15–35 °C, but the
      Modbus PDF lists Max `158.0`. Confirm the real usable range and adjust
      MIN/MAX/STEP if the device accepts more.

## Fan mode — implemented, needs hardware verification

> The test simulator (`tests/sim/device.py`) models all three hypotheses below
> as `fan_model` = `rescale` (default) / `clamp` / `direct`. Once the hardware
> answer is known, make that one the default and drop the others.

The climate entity now exposes **fan_mode** (off / low / medium / high):

| Mode   | Manual fan speed written to reg 1614 |
|--------|--------------------------------------|
| off    | 0 %  |
| low    | 30 % |
| medium | 55 % |
| high   | 85 % |

Read-back maps the **actual** output (`outAO_SupplyFan`, 639) to the nearest
preset via midpoint thresholds (42.5 / 70.0 %). `fan.hrds_supply_fan` reads the
same register, so the two entities always agree about what the fan is doing.
The **commanded** setpoint is `number.fan_manual_speed` (1614) and the fan
entity's `commanded_percent` attribute.

The gap between commanded and actual is the interesting measurement — see the
rescale-vs-clamp item below. Note the presets are written to 1614 as-is, so if
the band scales them, "low" will not read back as `low` until PF28/PF10 are
opened to 0/100.

- [x] **Core assumption: compressor/dehumidify can run on passive MVHR flow
      alone (no unit fan running)** — this is architecturally confirmed: the
      non-`R` variant (no recirc fan installed) always operates this way. The
      compressor dehumidifies and cools with MVHR passive flow only, by design.
      **On the `R` variant the stock controller does not allow it:** the damper
      opens and the fan starts on every dehumidification/integration request,
      regardless of PM20 (`doc/references/UNIT_BEHAVIOUR.md` §9.3). A user
      reports the fan would not go below 30 %, and an unofficial I/O
      reassignment as the only way around it.
- [ ] **Rescale or clamp? (R variant only) — the key fan question.** The technical
      handbook says manual fan control is *„linear zwischen den jeweiligen
      Minimal- und Maximalwerten (PF28/PF10 bzw. PF27/PF09) skaliert"*, i.e. the
      request is a **position within the band**, not an absolute percentage. If
      PM20 (1614) shares that logic — likely, since 1114 is the "manual display
      request" — then at the factory 50–85 % band a request of 30 yields ≈60.5 %
      output, and a request of 0 yields 50 %, not a stopped fan.

      Distinguish the three possibilities by sweeping PM20 with the band at its
      defaults and reading `outAO_SupplyFan` (639):

      | PM20 = 0 / 30 / 100 → actual | Interpretation |
      |------------------------------|----------------|
      | 50 / 60.5 / 85 | **rescaling** — request is a band position |
      | 50 / 50 / 85 | **clamping** — request is absolute, clipped to the band |
      | 0 / 30 / 100 | band does not apply to the Modbus setpoint at all |

      Then set PF28 = 0 and PF10 = 100 and repeat: under either of the first two
      the output should now track PM20 one-for-one. That is the configuration an
      external controller wants, and both bounds are writable numbers
      (`fan_min_speed_dehumidify` / `_cooling` / `_vmc`, `fan_max_speed_*`).

      This decides whether an external airflow controller can command percent
      directly or must open the band first.
- [ ] Confirm `SupplyFan_Status` (1119) reports `1` (OFF) when fan mode = off
      and a mode is active, and that `recirculation_active` (1112) goes 0.
      Covered by the fan = 0 test below.
- [ ] Verify the Low / Medium / High percentages (30 / 55 / 85 %) are
      reasonable for the real unit; adjust in `climate.py` `_FAN_MODE_PCT` if
      not. These are nominal choices, not values from the PDF.

## Fan = 0 during dehumidification, and keeping the damper closed (Modbus only)

Background: `doc/references/UNIT_BEHAVIOUR.md` §9.3. On the `R` variant the
handbook couples dehumidification to recirculation (§2.7, §6.2, §6.5), and the
vendor confirms it in the energiesparhaus.at HRDS+ thread. Everything below is
**untested on hardware** and **expected not to work**, unless noted otherwise.
It is listed so the test is run once and the result recorded, not because any
option is recommended.

- [ ] **Test: what does the unit do when the fan is set to 0 while
      dehumidifying?**
      Expected from the forum: the fan does not go below about 30 % output, and
      the damper opens anyway.

      Procedure, all over Modbus:
      1. **Record the original values** of every register this section
         touches, so they can be restored afterwards: 1614 (PM20), 1853 (PF28),
         1647 (PF10), 1698 (PS01), 1831 (HC03), 1832 (HC04), 1838 (HD01).
      2. **Make sure there is airflow through the coil** while the fan may be
         off. Run the central MVHR at 150 m³/h or more (the lowest flow in the
         handbook's capacity table for the HRDS+ 30).
      3. **Start dehumidification:** 1105 ← 1 (on), 1140 ← 1 (dehumidify),
         1139 ← 0 (no active cooling). The hub sets the BMS enables PH02/PH28.
      4. **Pass 1:** write 1614 ← 0 with the factory band (PF28 = 50 %,
         PF10 = 85 %).
      5. **Pass 2:** write 1853 (PF28) ← 0, then 1614 ← 0 again.
      6. **In each pass,** wait for the damper pre-start time (PS01, default
         20 s) plus the fan and compressor start delays. Then read:
         * `outAO_SupplyFan` (639) and `actRPMsupplyFan` (1117)
         * `SupplyFan_Status` (1119) and `FanIntegration_Request` (1112)
         * `outDO_RecircDamper` (1134) and `Packed_DO1` (384), bits 8–9
         * `CmpStatus` (1122) and `DehumRequest` (1121)
         * `PackedAlarm_1` (768), bit 10 = AL11 (low pressure / frost)
      7. **Check physically** whether the fan is turning, and whether air is
         drawn in at the recirculation grille, which would mean the damper is
         open.
      8. **Restore** the recorded values.

- [ ] **Options to keep the recirculation damper closed with the fan off.**
      Modbus only, no rewiring. Each one is **untested and likely not
      working**.

      **A. The repository's original assumption:** write PM20 (1614) ← 0,
      optionally opening the band with PF28 (1853) ← 0 and PF10 (1647) ← 100.
      The idea was that the fan stops and the unit dehumidifies on passive
      MVHR flow, with the damper staying closed.
      *Likely not working:*
      * §6.5 opens the damper on every dehumidification or integration
        request.
      * The vendor (#78): fan 0 „bringt ja nichts, weil die Klappe dann
        trotzdem aufgeht“.
      * A user (#77) could not get the fan below 30 %.

      **B. Invert the damper relay** (forum, manuon #79): HD01 (1838, DO1
      allocation) from 10 = "Recirculation damper NO" to 9 = "Recirculation
      damper NC".
      *Likely not working as wanted:*
      * The damper would be closed during operation but open whenever it
        should be closed, which presumably includes standby. That only moves
        the open-damper period.
      * Whether it takes effect without a restart is unknown.

      **C. Disable the damper output** (vendor suggestion, Murphy08 #78): set
      HD01 (1838) ← 0.
      *Likely not working:*
      * The vendor was unsure it works without a restart.
      * The user reports (#79) that the compressor does not start with DO1
        disabled.

      **D. Fan side, needed alongside B** (forum, manuon #79):
      * HC04 (1832, AO4 allocation) from 1 = "0-10 V supply fan" to 0 =
        disabled, which takes the real fan's signal away.
      * HC03 (1831, AO3 allocation) from 0 to 1 = "0-10 V supply fan", so the
        controller drives a "fan" on the empty AO3 and the compressor is
        allowed to start.
      * HC04 ← 0 on its own stops the compressor from starting (#79).
      *Untested here.* manuon reports B + D working on an HRDS+ 50 (#93, KWL
      supply only, 368 m³/h). Treat it as unconfirmed for this integration.

      **Side effects to record if any option is tried:**
      * After D, the controller believes its fan is running. 639, 1119, 1112
        and `sensor.supply_fan_airflow` then report a fan that is not
        turning. 1117 (RPM) is the honest reading, if the fan reports RPM.
      * It is unknown whether HC/HD writes go to memory with limited write
        cycles. Do not toggle them per dehumidification run.
      * Restore the original values afterwards.

## Entities documented but not yet exposed

- [x] **Exhaust air temp (502)** and **evaporator temp (511)** — now exposed as
      sensors.
- [ ] **Alarm detail**: AL03, AL04, AL11, AL12, AL16, AL22 and the probe
      alarms AL28/AL34 are exposed as binary sensors. Other alarm bits and the
      `BMS_ALxx` reset registers (785/786/791) are not.
- [x] **Season change**: `select.season` writes `DI4_Configuration` (1825,
      3/4 only); `PriorityChangeMode` (1878) is shown read-only. (Whether the
      write switches the season on hardware is under *Installer device /
      season / water circuit* below.)
- [ ] **Remote fan request** (1116, R/O) is not exposed; the display's manual
      request (1114) is (`sensor.fan_manual_request`).
- [x] Recirculation damper status (1134) — now exposed as `sensor.recirculation_damper`.

## Setup check / operation gate (added 2026-10-19)

- [ ] Verify on hardware that every setup-check issue clears as described in the
      README checklist (remote contact, PH03, HA02/HA03 = 0).
- [ ] Confirm the `remote_contact_closed` bit (257 bit 0) meaning by opening the
      contact.
- [ ] Decide whether the gate should also refuse climate `hvac_mode` writes with
      a friendlier message (currently surfaces the `ServiceValidationError`).

## Installer device / season / water circuit (added 2026-10-19)

- [ ] Confirm on hardware that writing HB04 = 3 switches `operating_mode` to
      winter and 4 back to summer (no contact wired to DI4).
- [ ] Watch `water_valve_pump` (1126) during a dehumidify request on the brine
      installation: expect On with the request, Off after Pb01.
- [ ] Verify the enum meaning of 1124 / 1126 (0/1/2 inferred from the
      misaligned PDF table).
- [ ] Spot-check installer scaling for rows not covered by the snapshot
      (PM81 1617) and the PA20 address (1736 is not in the PDF table).
- [ ] Check whether registers above 1900 (PT05-PT11, PH31-PH35, PA61/PA62)
      are readable; add them to the installer device if they are.

## Operating modes and the passive cold-water path (added 2026-10-21)

The README section *How the unit works* describes these from handbook §6.3;
none of them has been seen on the real unit yet.

- [ ] **Passive path (water below PU08).** With water (`water_temperature`,
      501) below PU08 (1695, factory 10 °C) and a DEU or INT request in
      summer: `compressor_status` (1122) stays off, `water_valve_pump` (1126)
      is On, supply air gets colder and drier (watch room humidity with an HA
      sensor). Note which way `water_condenser_valve` (1124) goes.
- [ ] **PU09 second step.** In the same state, does the compressor join after
      PU10 (1697, factory 120 min) while the request is still on, and does it
      stop again when the request is satisfied?
- [ ] **INT with PU05 off (water above PU08).** Set
      `switch.force_dehumidify_in_cooling` off, request Cool with no DEU and
      (with a probe) room humidity under PU01: compressor should stay off. Does
      the valve/pump run and does the supply air cool? This is the undocumented
      "passive cooling" mode; restore PU05 on afterwards.
- [ ] **INT + DEU with PU05 off.** Is it the same as INT with PU05 on
      (internal valve closed, cold air), or does DEU's reheat win (air at room
      temperature)? Read 1124 and the supply air temperature.
- [ ] **Brine guard default 8 °C** (was 10). On the brine installation in early
      summer, brine at 8–10 °C: requests start, the unit runs the passive path,
      AL16 (PA43 = 3 °C) does not trip, and the register does not ice up.
- [ ] **`water_below_compressor_limit` puts the water check on `attention`**
      during normal passive operation. Decide whether it should become an
      informational attribute instead of an issue once the passive path is
      confirmed.

## Release housekeeping (added 2026-10-20)

- [ ] **Manifest `categories`.** HACS warns "manifest has no categories". The
      value belongs in `manifest.json`: `["climate.air_purifiers_humidifiers",
      "climate.fans_ventilation"]`. It cannot go in yet because the hassfest
      action runs `hassfest:latest`, which Home Assistant only updates for beta
      and stable releases, and the key reached core `dev` on 2026-10-17: hassfest
      fails with "not a valid option at 'categories'". Add it, with the CHANGELOG
      line, once `hassfest:latest` knows the key (check `script/hassfest/manifest.py`
      of the newest release tag for `categories`). Alternative if it should not
      wait: add it now and strip the key from the CI checkout in `hassfest.yaml`
      and the `hassfest` job of `release.yaml` until then.

## Unit behaviour marked `[INFERRED]` in UNIT_BEHAVIOUR.md (added 2026-10-21)

Open points found while writing
[`doc/references/UNIT_BEHAVIOUR.md`](../doc/references/UNIT_BEHAVIOUR.md). The
handbook is silent or contradicts itself on these.

- [ ] **K4 / 1124 meaning.** The reference unit reads 1124 = 1 and
      `Packed_DO1` bits 12–13 = 1 in standby; the Modbus manual labels those
      bits `0 = Integration, 1 = Dehumidify`. Hypothesis: 1 = open (reheat)
      position. Read both while cooling (INT, compressor on): expect 0.
      (Same test as the condenser valve item under *Climate entity behaviour*.)
- [ ] **Anti-stagnation while OFF.** Do V3V + PM still pulse every Pb08 hours
      with the unit OFF (handbook §4.5 "independent of operation") or only
      while ON (§2.7, and §3.8.7 recommends OFF on brine)? Watch 1126 over a
      Pb08 interval (reference unit: 60 h) with the unit OFF.
- [ ] **PU02 "with water" / "without water".** What changes between 1 and 2
      (does V3V/PM open)? And does PU02 = 0 also block a Modbus or DI
      dehumidify request in winter, or only the automatic one?
- [ ] **Automatic season with the water probe** (PC05 = 2, PC06 = 0): which
      thresholds decide? Not described in the handbook.
- [ ] **Non-`R` unit read-back.** Does `outDO_RecircDamper` (1134) read
      `2 = Disable` on a unit without recirculation, and what do the fan
      registers read?
- [ ] **Other units' product code** (FC 43): does an HRDS+ 50 or a non-`R`
      unit also report `EPB9…`? (Also listed under *Headless operation*.)
- [ ] **As-delivered settings.** The reference unit shipped with values that
      differ from the handbook defaults (`UNIT_BEHAVIOUR.md` §15). A second
      unit's dump would show whether these are the distributor's presets.
