# Fan speed over Modbus: hardware test plan

For an agent (or the owner) with access to the reference unit, HRDS+ 30 `R` `DC`,
headless. Each test checks one assumption from
[`doc/references/UNIT_BEHAVIOUR.md` §9.1](../doc/references/UNIT_BEHAVIOUR.md#91-bands-and-sources).
Tags (`[HB 6.2]`, `[MB p.7]`, `T23`) are explained in §0 of that file.

## Status (2026-10-23)

* Test A is partly done: raising `PF28` mid-run raises the fan within one
  poll (T25), and lowering `PF28` does not lower it (T24, T26). The unit
  **clamps** its own manual request into the band, and does not rescale it
  ([run file](../tests/devices/runs/hrds_30+_fan_band_2026-10-23.json)).
* Still open:
  * A: jump or ramp, at 5 s resolution;
  * B, C, D (optional), E, F;
  * new test G: lowering through the maximum.

## Why

* A fan speed written to `PM20` (1614) inside the band was acknowledged, but
  the unit kept the fan at 50 % (T23).
* The handbook defines `PM20` as the display's setpoint, "via Display (read
  only)" [HB 5.3].
* No register takes a fan-speed request from the BMS [MB p.5, p.14–15]. The
  documented Modbus lever is the band itself [HB 4.5; MB p.7].
* The integration's fan write path (`fan.set_percentage`,
  `climate.set_fan_mode`, `number.fan_manual_speed`) writes `PM20`, so today
  it does nothing.
* These tests decide what replaces it: `plans/todo.md`, item *Fan write
  target*.

## Assumptions under test

| # | Assumption | Source | Test |
|---|------------|--------|------|
| A1 | With every fan request at 0 (headless), the output is the band minimum | [HB 6.2; T16] | A, **seen** (T16, T22) |
| A2 | A new `PF28` written while the fan runs moves the output | [INFERRED from HB 4.5] | A, **seen when raised** (T25); a lowered `PF28` does not move it (T24, T26) |
| A3 | The output jumps to a new minimum, or ramps in `PF11` steps | [INFERRED] | A, open |
| A4 | `PM20`/1114 follow the band minimum (they show the scaled manual request) | [INFERRED from T22] | A, **seen** (T25): they mirror the clamped manual request |
| A5 | `PF28 = PF10` is accepted and gives that speed | [INFERRED] | B |
| A6 | A write to `PM20` is overwritten within one controller cycle, and 639 never moves | [T23; INFERRED] | C |
| A7 | 0–10 V on FAN+ raises 639 and 1116, but not 1114/1614 | [HB 6.2] | D |
| A8 | 1112 is a 0–100 % request that is non-zero only during INT | [MB p.14; INFERRED] | E |
| A9 | A `PF28` written while idle applies from the next fan start | [INFERRED] | F |
| A10 | Lowering `PF10` below the running speed pulls it down; restoring `PF10` keeps the lower speed | [INFERRED from T24–T26] | G |

## Tools and rules

* **Writes only through Home Assistant**, never a second Modbus master. Every
  write goes through the integration's guards (ADR-0006, ADR-0012).
  Entities used (keys from [`doc/entity-reference.md`](../doc/entity-reference.md);
  the real entity id may carry the device prefix):

  | Entity | Register | Parameter |
  |--------|----------|-----------|
  | `number.fan_min_speed_dehumidify` | 1853 | PF28 |
  | `number.fan_max_speed_dehumidify` | 1647 | PF10 |
  | `number.fan_min_speed_cooling` | 1852 | PF27 |
  | `number.fan_max_speed_cooling` | 1646 | PF09 |
  | `number.fan_manual_speed` | 1614 | PM20 |
  | `switch.dehumidify` | 1140 | DEU |
  | `switch.integration_request` | 1139 | INT |

* **Reads:**
  * Home Assistant polls about once a minute: `sensor.supply_fan_output`
    (639), `sensor.fan_manual_request` (1114), `number.fan_manual_speed`
    (1614), `sensor.supply_fan_status` (1119).
  * For 1–5 s resolution, and for registers without an entity (1113, 1115,
    1116), run a read-only pymodbus loop with FC 04, plus FC 03 for 1614 and
    1853. Use the same host, port and unit id as `tests/diagnose_hrds.py`.
  * Keep each request at 10 registers or fewer (T9): read 639, then
    1112–1119, then 1614 and 1853.
  * Never write from that script.
* **Preconditions, all set by the owner; the integration never sets them:**
  * the unit is ON;
  * `PH02`/`PH28` (and `PH27` for test E) are on;
  * the gate `switch.operation_allowed` is on;
  * the MVHR runs at 150 m³/h or more;
  * the season is summer.
* **EEPROM:** PF28/PF10/PF27 are EEPROM parameters (ADR-0023). The whole plan
  needs about 12 parameter writes. Count them, and do not loop or automate
  them.
* **Before the first write,** record 1853, 1647, 1852, 1646 and 1614.
  Restore them at the end. Shipped values: 5000, 8500, 5000, 8500 (§15).
* **Never set a minimum above its maximum.** What the unit does then is
  unknown.

## Tests

### A. Band minimum during a run (A1–A4)

**Partly done (T24–T26):** 65 → 50 was not run as written. Instead, during a
run with the fan at 50, `PF28` went 50 → 45 (no change), then 45 → 55 (55 in
the same poll), then 55 → 50 (stayed at 55). What remains is the 5 s log of a
raise, to tell a jump from a ramp. The expected values below assume the fan
is at 50 before step 3; after step 4 it stays at 65, as T26 shows.

1. Start DEU (`switch.dehumidify` on). Wait until 1119 = ON and 639 is
   steady (≈ 2 min after the damper opens).
2. Start the 5 s read loop: 639, 1114, 1614, 1116, 1119.
3. Set `number.fan_min_speed_dehumidify` to 65. Log for 2 minutes.
4. Set it back to 50. Log for 2 minutes.

Expected: 639 reads 65 within one or two controller cycles, and 1114/1614 read
65 too. After step 4 all three stay at 65 until the request ends (T26).

What the results mean:

| 639 after step 3 | Meaning |
|------------------|---------|
| Reads 65 at once | The band is a live lever |
| Steps up by `PF11` (7 %) every few seconds | Ramp. Note the interval |
| Stays 50 | Contradicts T25. Stop and report |

### B. Top of the band (A5)

During the same run:

1. Set `number.fan_min_speed_dehumidify` to 85 (= PF10). Log 639 for
   1 minute.
2. Set it back to 50.

Expected: 639 reads 85 and stays there after step 2 (T26). Use test G to bring
it down. Do not write a minimum above 85.

### C. PM20 overwrite timing (A6)

1. During a run with the band at 50–85, start a 1–2 s read loop on 1614, 1114
   and 639.
2. Set `number.fan_manual_speed` to 70.

Expected: 1614 shows 70 for one read or not at all, then reads 50 again. 639
stays 50. Record how long 1614 held 70.

### D. 0–10 V on FAN+ (A7, optional, needs hardware)

* Needs a 10 kΩ linear potentiometer on the display terminal block: 12 V
  output with series resistor, FAN+ and FAN− [HB 4.5]. `HA01 = 58` (fan
  potentiometer 0–10 V) is already allocated (T21).
* The owner wires it; an agent does not.

1. During a run, turn the potentiometer to about 50 %.
2. Log 507, 1116, 1114, 1614 and 639.

Expected:
* 507 leaves its no-signal value `0x7FFA`.
* 1116 rises, and 639 rises to about 67.5 % (the middle of 50–85).
* 1114/1614 stay at 50.

Also record whether 1116 reads the raw signal (≈ 50) or the value scaled into
the band (≈ 67.5).

### E. INT request (A8)

1. With `PG02 = 1`, `PH27` on and summer, start INT
   (`switch.integration_request` on). Leave DEU off.
2. Log 1112, 1113, 1114, 1115, 1116 and 639 for 10 minutes.
3. Read `PF31` (1856; it ships at 1), `PF27` and `PF09`.

Expected: 1112 reads a percentage inside `PF27..PF09`, not only 0 or 1.

### F. Band written while idle (A9)

1. With no request, set `number.fan_min_speed_dehumidify` to 60.
2. Start DEU and read 639 at fan start.
3. Restore 50.

Expected: 639 reads 60 from the start, since the request starts at 0 and is
clamped up to the minimum (T22).

### G. Lower through the maximum (A10)

1. During a run with the fan above 50 (for example at 55 after a test-A
   raise), start the 5 s read loop on 639, 1114, 1614.
2. Set `number.fan_max_speed_dehumidify` (PF10) to 52. Log for 1 minute.
   Expected: 639, 1114 and 1614 read 52.
3. Set PF10 back to 85. Log for 1 minute. Expected: they stay at 52.
4. Never set PF10 below PF28.

This decides whether the integration can set any speed within the band with
two band writes, or only raise it (`plans/todo.md`, *Fan write target*).

## Recording the results

* For each test, add a `T` row to `UNIT_BEHAVIOUR.md` §13, starting at T27.
  Replace the `[INFERRED]` tags it settles in §3.5, §9.1 and §14.
* Put a run file in `tests/devices/runs/`, named
  `hrds_30+_fan_speed_tests_<date>.json`. Use the same layout as the two run
  files there: `_about`, `timeline`, `findings`, `open`.
* `plans/todo.md`:
  * tick the items these tests answer;
  * add the result to *Fan write target*;
  * the code change is decided there and recorded with `/adr supersede` on
    ADR-0008.
* Do not change integration code in the same PR as the evidence.
