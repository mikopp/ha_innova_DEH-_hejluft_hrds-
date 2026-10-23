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
- [x] **`recirculation_active` (reg 1112) is a 0/1 flag**, not a 0–100 %
      value. No: the Modbus manual's full map gives `FanIntegration_Request`
      the range 0.00–100.00 like the fan requests 1113–1116 next to it
      [MB p.14], so it is a fan request in % (`MODBUS_REGISTERS.md` §6). It
      stayed 0 through two recirculating DEU runs (T16, T18). The entity PR
      shows it as a % sensor. Still to see on hardware: a non-zero value during
      an INT run ([`fan-speed-tests.md`](fan-speed-tests.md) test E).
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
      honoured.** They are the user's switches now (the integration never
      writes them). Confirm on hardware that with one off the unit ignores
      the matching request register, that it keeps a request written while
      the enable was off, and that a power cycle keeps the enables and the
      requests (1105/1139/1140).
- [ ] Confirm an **OFF command always wins** over an ON from any source
      (display/DI/Modbus), per the manual.
- [ ] **`PU13_MinTRoom_disableDEU` (1889) can veto a Modbus dehumidify request.**
      The unit disables dehumidification below this room temperature. On a unit
      with no room probe, confirm whether a Modbus request still starts the
      compressor, and whether setting PU13 to 0 lifts the interlock. This is the
      most likely cause of "the write was accepted but nothing happened".
      Update 2026-10-22: at the shipped `PU13` (10 °C) a Modbus dehumidify request
      started the compressor with no room probe, so no veto there. Open: at the
      handbook default (22 °C), and for a DI request.

## Request read-back lag (added 2026-10-21)

- [ ] **How late does the unit mirror a request?** A real unit read the on/off
      request back as ON for several polls after OFF was written (switch and
      `unit_status` changed together at the same poll). The hub now shows the
      command until confirmed and re-reads at 3/6/12/25 s (`PENDING_RECHECK_SECONDS`).
      With debug logging for `custom_components.innova_hrds`, the line
      "HRDS+ confirmed <key>=<value> after N s" gives the real lag: size the
      schedule from it (and check whether OFF and ON lag alike).
      Data point 2026-10-22: a dehumidify request (1140) showed in `DehumRequest`
      (1121) within 28 s, so the lag differs between registers.

## First dehumidify run, 2026-10-22 (open points)

A Modbus dehumidify (DEU) request on the headless HRDS+ 30 R worked: damper, fan,
compressor and water valve came on in order, the evaporator settled on its
setpoint, no alarm. A second run followed on 2026-10-23. Data:
`tests/devices/runs/hrds_30+_first_dehumidify_run_2026-10-22.json` and
`tests/devices/runs/hrds_30+_dehumidify_run_2026-10-23.json`; evidence T11–T22
in `doc/references/UNIT_BEHAVIOUR.md` §13. What they left open:

- [x] **Fan RPM (1117) reads 0 with the fan running.** Answered 2026-10-23: the
      speed needs an input allocated to the tachometer (input function 45/46),
      and none is (T21); the 0 is the unit's value, not a wrong read
      (`UNIT_BEHAVIOUR.md` §9.1). The fan's running is confirmed by the owner
      and by the MVHR flow dip at its start (T18). `diagnose_hrds.py` now prints
      the tachometer allocation in its snapshot; one read of the running unit
      confirms the dump. Whether the fan's tachometer wire could be connected to
      a free input is an installer question. Integration side: show the speed
      only when an input is allocated (entity PR).
- [ ] **What is 1112 (`FanIntegration_Request`)?** It stayed 0 through two
      recirculating DEU runs (T16, T18), so it is neither "fan running" nor
      "recirculating". The Modbus map makes it a 0–100 % fan request (see the
      scaling item above). Hypothesis: the request of the INT fan control
      (`PF31`, `PF12`/`PF13`), non-zero only during an INT request. Read it
      during the first INT run ([`fan-speed-tests.md`](fan-speed-tests.md)
      test E). Integration side: derive `recirculation_active` from the
      damper (1134) and fan status (1119) and show 1112 under its own name
      (entity PR).
- [x] **Who wrote `PM20` (1614) and the display request (1114)?** The unit: both
      went 0 → 50 % at the fan start of both runs and 50 → 0 at the stop, with no
      write from Home Assistant (T22). So `commanded_percent` and
      `number.manual_fan_speed` show the unit's value, a percentage written while
      idle is overwritten at the next start, and the rescale/clamp sweep below
      has to write `PM20` while a request runs. Open: does a `PM20` written
      during a request hold until its end? **No** (T23, 2026-10-23): a value
      inside the band written during a run was acknowledged and read back as
      50 %. How fast the unit overwrites it: [`fan-speed-tests.md`](fan-speed-tests.md)
      test C. Seen again on 2026-10-23: 0 at the end of a request (11:29:56),
      50 at the next fan start (11:43:12), and `PM20` follows a raised `PF28`
      (T25): it mirrors the unit's own manual request.
- [ ] **Which timer held the compressor?** It came on 6.5–8 min after the
      request and 5–7 min after the fan; `PE04` ships at 180 s, so something else
      held it. `PE03` (420 s) fits numerically, but it is defined between two
      compressor starts. Poll `CmpStatus` (1122, has a "Wait ON" state) and
      `SupplyFan_Status` (1119) every 5 s through the next start to see the stages,
      and repeat a start soon after a compressor stop to see whether `PE03` counts
      from the last start.
- [ ] **Record the stop sequence.** Seen at 1-minute resolution (T19): the
      compressor, V3V + PM and damper were off within 61 s, the fan ran on at
      `PF26` (40 %) for up to a minute more. Still to log every 5 s
      (`diagnose_hrds.py --watch`): compressor stop against `PE02`, the
      ramp-down (`PE25`), V3V + PM closing against `Pb01`, fan run-on against
      `PF03`. Check the climate `hvac_action` and `supply_fan_running` follow.
- [ ] **First anti-stagnation pulse after a request: why 2 hours?** After the
      2026-10-22 stop the valve stayed shut from 07:37:58 to 09:39:57, then
      pulsed hourly again (T20); HB 6.4 says `Pb08` (60 min) after the valve
      closes. Repeat after the next stop and see whether it is again 2 hours.
- [ ] **Does the unit judge the first, standing brine reading?** At the request
      start the probe read the warm standing brine (18.3 °C) and 14.8 °C two polls
      after V3V + PM opened. If the brine ever flows below `PU08` but stands above
      it, does the unit take the passive path or start the compressor, and do
      `PC07`/AL03 judge the standing value? Watch `water_temperature` and
      `compressor_status` at the start of a request in early summer.
- [x] **Evaporator undershoot to −3.1 °C with the MVHR on its lowest preset
      (about 100 m³/h).** Answered 2026-10-23: with the MVHR at 140–163 m³/h the
      start dipped further, to −9.6 °C, and settled on `PU11` within 6 minutes,
      AL11 clear (T18). It is the start transient, not too little airflow.
- [ ] **Supply-air temperature.** The unit's supply probe reads unknown, so "DEU
      gives dry air at about room temperature" (HB 2.6.1) is unverified. Log an
      external sensor downstream of the HRDS through a run; that also shows what
      the internal valve K4 does to the air. Nothing on the unit can stand in:
      the water probe reads the water before the condenser (T18), and the
      ComfoAir supply sensor sits before the HRDS. With about 16.5 °C brine
      expect below room temperature (HB 3.8.5: more flow, cooler supply).
- [ ] **Second dump while running.** Take a read-only dump with
      `diagnose_hrds.py` during a DEU request and diff it against
      `hrds_30+_headless_factory_state.json`: every register that changed should be
      documented, or flagged.
- [ ] **`PU13` at the handbook default.** At the shipped value the compressor
      started without a room probe. Does it still start with `PU13` at the
      handbook default? Only worth testing if `PU13` is ever raised.

## Headless operation, identity, sentinel (added 2026-10-19)

- [x] **PH01 = 0 does not clear `off_by_display` by itself** (2026-10-20, real
      unit, EPB9ORSINDEU V01.00.09.02). PH01 = 0, HA00 = 0, PH02 = 1 and a power
      cycle still read `off_by_display`; the first Modbus ON (`switch.unit_on_off`)
      moved it to `on` at once. The setup check now reports
      `unit_waiting_for_first_on` for this. A Modbus OFF then reads `off_by_bms`
      (seen 2026-10-21). Still open: does it stay so across a power cycle.
- [ ] **HA00 = 0 on a unit that read 2** (the manual says the factory value is
      6). Confirm it is accepted and whether AL28/AL34 appear afterwards.
- [ ] **PH01 / HA00 are config parameters**: confirm that re-writing them only
      when the read-back differs (never blindly each poll) does not wear the
      controller's memory, and that the unit does not reset them on its own.
- [ ] **Sentinel window** `0x7FF0..0x800F`: only `0x8004` and `0x7FFA` have been
      seen. Confirm what a *failed* (wired but broken) probe reads, and whether
      it also raises AL28/AL34.
- [x] **AL28/AL34 were not set** while the unit was OFF by display with no
      probes (PackedAlarm_2/3 = 0). Confirm they appear once the unit is ON.
      Done 2026-10-22: still clear with the unit ON and dehumidifying.
- [x] **PU13 with no room temperature**: does the interlock veto a Modbus
      dehumidify when the room input is the sentinel? If yes, set PU13 to 0.
      Done 2026-10-22: no veto at the shipped `PU13` (handbook default: see
      *First dehumidify run*).
- [ ] **Identity check**: the product-code prefix `EPB9` comes from one unit
      (`EPB9ORSINDEU`). Confirm other HRDS+ variants (30/50, non-R, non-DC)
      report an `EPB9…` code; loosen `EXPECTED_PRODUCT_PREFIX` if not. Also
      confirm what a gateway that does not forward FC 43 returns.

## Climate entity behaviour

- [ ] **Mode writes** (ADR-0025): DRY = on + dehumidify + integration_request
      **off**; COOL = on + dehumidify + integration_request **on**; HEAT = on +
      integration_request, dehumidify off; OFF = both requests off and the unit
      off. Confirm the combinations produce the expected unit behaviour and
      feedback.
- [ ] **`hvac_action` derivation** from `unit_status` / `compressor_status` /
      `dehumidify_request` reflects reality (DRYING vs COOLING vs IDLE vs OFF).
- [ ] **What does the condenser valve (1124, K4) read while cooling?** The
      Modbus manual says ON = all compressor heat to the water (summer
      integration), but the real HRDS+ 30 read `1` in standby, where the
      handbook (§6.4) says the valve stays deactivated. Note its value in
      standby, while dehumidifying and while cooling (COOL). If it reliably
      tells cooling from dehumidifying, `hub.is_cooling` can use it.
      Update 2026-10-22: it read 1 while dehumidifying too (same as standby); the
      cooling reading is still missing.
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

> **2026-10-23: the integration's fan write does not work.** `PM20` (1614) is
> the display's setpoint ("via Display (read only)", handbook §5.3); the unit
> overwrites a Modbus write (T22, T23). No register takes a fan-speed request
> from the BMS; the documented Modbus lever is the band (`PF28`/`PF27`,
> `UNIT_BEHAVIOUR.md` §9.1). Seen on hardware: raising `PF28` above the
> running speed raises it within a poll, lowering `PF28` does not lower it
> (T24–T26). The remaining hardware tests are in
> [`fan-speed-tests.md`](fan-speed-tests.md); the code change waits for them
> (item *Fan write target* below).

> The simulator (`tests/sim/device.py`) now models what the hardware showed:
> the unit owns `PM20`, clamps it into the band and drives the fan at it; a
> write is acknowledged and not kept, one outside the band is refused (T22–T28).
> There is no fan entity any more, and the climate entity has no fan mode
> (ADR-0034).

- [x] **Core assumption: compressor/dehumidify can run on passive MVHR flow
      alone (no unit fan running)** — this is architecturally confirmed: the
      non-`R` variant (no recirc fan installed) always operates this way. The
      compressor dehumidifies and cools with MVHR passive flow only, by design.
      **On the `R` variant the stock controller does not allow it:** the damper
      opens and the fan starts on every dehumidification/integration request,
      regardless of PM20 (`doc/references/UNIT_BEHAVIOUR.md` §9.3). A user
      reports the fan would not go below 30 %, and an unofficial I/O
      reassignment as the only way around it.
- [x] **Fan write target.** Decided by the owner on 2026-10-23 (ADR-0034,
      supersedes ADR-0008): the fan is read-only, the climate entity has no fan
      mode, and `fan_manual_speed` (PM20) is a read-only sensor. A write to
      `PM20` never acts without a display (T23, T27, T28), and whether it acts
      with one is unknown. The band numbers stay the user's lever. A speed
      control built on the band (raise via the minimum, lower via the maximum,
      [`fan-speed-tests.md`](fan-speed-tests.md) test G) can be proposed once
      G is run; it costs EEPROM writes per change (ADR-0023).
- [x] **Rescale or clamp? (R variant only) — the key fan question.**
      **Answered (T23–T26).** The unit does not take `PM20` from Modbus at
      all (T23). Its own manual request, which `PM20` mirrors, is an absolute
      percentage **clamped** into the band, not rescaled: a lowered minimum
      left the fan at 50 and later 55 %, a raised one pushed it up (T24–T26).
      The 0–10 V input is still scaled linearly by the handbook (untested).
      The question below is kept for the record. The technical
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
- [ ] **Does the fan stand still while 1119 reads `2` (wait_on, "Starting")
      and turn while it reads `4` (wait_off, "Stopping")?** Record 1119 and 639
      from a request's start to the end of the PF03 run-on, and look at the
      fan. ADR-0028 counts On and Wait OFF as running (T19 saw 40 % in Wait
      OFF); Wait ON as stopped is [INFERRED].
- [x] ~~Verify the Low / Medium / High fan mode percentages~~: the climate
      entity has no fan mode any more (ADR-0034).

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
         1139 ← 0 (no active cooling). Turn on the PH02/PH28 enables first (the integration never sets them).
      4. **Pass 1:** write 1614 ← 0 with the factory band (PF28 = 50 %,
         PF10 = 85 %). Expected to change nothing: `PM20` does not hold a
         write (T23).
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
- [x] Watch `water_valve_pump` (1126) during a dehumidify request on the brine
      installation: expect On with the request, Off after Pb01. On with the
      request and the pump on `PM` runs [T10]; the Off after `Pb01` was not
      logged.
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
- [x] **Anti-stagnation while OFF.** Do V3V + PM still pulse every Pb08 interval
      with the unit OFF (handbook §4.5 "independent of operation") or only
      while ON (§2.7, and §3.8.7 recommends OFF on brine)? Done 2026-10-21/22:
      no pulse in 8.5 h of `off_by_bms`, hourly pulses while ON; `Pb08` is in
      minutes, not hours (T13, T14).
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
