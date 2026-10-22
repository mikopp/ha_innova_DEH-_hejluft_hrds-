# Tested units and installations

Which units and installation scenarios are known to work with this
integration, and which are not tested yet. This page describes **installations
the integration has been used in**; how the unit itself behaves, for any
installation, is in [`references/UNIT_BEHAVIOUR.md`](references/UNIT_BEHAVIOUR.md).
The open hardware questions are in [`../plans/todo.md`](../plans/todo.md).

## What the status means

| Status | Meaning |
|--------|---------|
| **Works** | Used on a real unit in this setup by the maintainer or by a reporter, and behaved as described. The row says what was seen. |
| **Partly** | Part of it was seen on a real unit; the row says what is still open. |
| Context | Not a feature: where the reference unit is installed. |
| **Not tested** | Only covered by the handbooks and by CI (a simulated unit and a real Home Assistant container). It may work; nobody has confirmed it. |

CI alone never makes a row **Works**. Evidence from the unit itself is logged
in [`references/UNIT_BEHAVIOUR.md` §13](references/UNIT_BEHAVIOUR.md#13-evidence-log-what-was-seen-on-real-hardware)
(`T1`, `T2`, …); a row here cites it.

## Units

| Unit | Status | Notes |
|------|--------|-------|
| hej.luft **HRDS+ 30** `H R K DC` (Innova DEH+ 30 H), headless | **Works** | The maintainer's unit (reference unit). Seen: identity and the whole register map read, the required settings and the first Modbus ON, OFF written over Modbus, a request starting the brine pump [T1 to T8, T10]. A full dehumidify or integration cycle with fan, damper, compressor and valve read-backs is not recorded yet |
| HRDS+ 50 / DEH+ 50 H | Not tested | The size has no register (the `model` option sets it). Only the airflow estimate differs |
| Units without recirculation (non-`R`) | Not tested | No fan, damper or fan entities are created when the damper output (1134) reads *disabled* |
| Units without the integration function (no `DC`, PG02 = 0) | Not tested | *Cool* and *Heat* are not offered |
| Unit with a CNU2 display | Not tested | The display and `HA00 = 1/2` path, the headless sync skipped |
| Unit with external room or outdoor probes | Not tested | Target humidity and temperature, climate *Auto* mode (CI only) |

## Installation scenarios

### Control path

| Scenario | Status | Notes |
|----------|--------|-------|
| Headless (`PH01 = 0`, `HA00 = 0`), no display, no probes | **Works** | Home Assistant is the controller: requests over Modbus. First Modbus ON takes the unit out of *off by display* [T7] |
| Modbus RTU (RS-485) to TCP gateway | **Works** | Reads must be small: a 120-register read got no reply, 10-register reads cover the map [T9]. Which gateway: not recorded |
| Native Modbus TCP, no gateway | Not tested | |
| Installed behind a Zehnder ComfoAir Q350 (MVHR) | Context | Where the reference unit is installed. Nothing about coupling to the MVHR is recorded |

### Water circuit

The unit's water source decides what it can do (see
[`references/UNIT_BEHAVIOUR.md` §2.2](references/UNIT_BEHAVIOUR.md) for the
handbook's variants 1 to 6 and the separate ground loop).

| Scenario | Status | Notes |
|----------|--------|-------|
| **Brine circuit of a ground-source heat pump, handbook variant 6**: the unit sits in a branch **parallel** to the heat pump, with its own small brine pump on the `PM` output. It runs independently of the heat pump and also at the same time | **Partly** | Seen: the unit starts the pump on a request, the pump runs and `sensor.water_valve_pump` follows [T10]. Not yet confirmed: the run-on `Pb01` and the Off edge, the passive cold-water path with early-summer brine, the brine temperature guard (default 8 °C), AL16, the anti-stagnation pulses ([`plans/todo.md`](../plans/todo.md)) |
| Brine circuit, variant 4 or 5 (in series with the heat pump, inlet or outlet side) | Not tested | Same wiring of `PM`; the brine temperatures differ |
| Separate ground loop (handbook §3.8.8) | Not tested | |
| Heating/cooling circuit of a heat pump, variants 1 to 3 | Not tested | The heat pump must be in cooling mode in summer; water about 16 to 20 °C, so the compressor runs |

### Operating modes

| Mode | Status | Notes |
|------|--------|-------|
| Dehumidify (DEU) and integration (INT) requests over Modbus, summer | **Partly** | A request starts the brine pump on the circuit above [T10]. The whole cycle and the passive cold-water path (water below `PU08`, compressor off) are open |
| Manual fan speed | Not tested | How the manual speed maps to the real fan output is open |
| Winter integration (heating) | Not tested | Impossible on brine. Needs a warm heating circuit |
| Free cooling | Not tested | |
| Automatic setpoint control (display or room probe), climate *Auto* | Not tested | Simulated display unit in CI only |

## Add your setup

A report from another unit or installation is what moves a row from *Not
tested* to *Works*. Attach the diagnostic output as described under
[Reporting issues](../README.md#reporting-issues) and say which unit, water
circuit, control path and operating modes you used; the maintainer adds the
row with the evidence.
