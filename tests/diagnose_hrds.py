#!/usr/bin/env python3
"""Read-only bring-up diagnostic for an HRDS+ / Innova DEH+ Modbus TCP gateway.

Run it from a machine that can reach the unit, *before* installing the
integration, to verify the assumptions the integration makes:

* Is the gateway reachable on the given port, and does the unit answer on the
  given Modbus unit/slave id?
* Which identification can we get from the device? (Modbus FC 43/14 "Read
  Device Identification" if the gateway supports it, plus a register
  fingerprint.) The register map has **no serial-number or firmware register**,
  so this prints what is actually available instead of assuming.
* Does every register the integration polls answer, using the *same block plan*
  the integration builds? Are the decoded values plausible?
* Which probes/sensors are actually connected, and which raise a fault alarm?
* Which settings should be reviewed/changed, and **what would the integration
  write to the unit on its first connect?**

The script NEVER writes to the unit: it only uses FC 03, FC 04 and FC 43.
It reuses ``custom_components/innova_hrds/const.py`` for the register map, so it
always checks exactly what the integration would poll.

Requirements:  pip install pymodbus==3.13.1   (the version HA 2026.9 ships)

Examples:
    python3 tests/diagnose_hrds.py 192.168.1.50
    python3 tests/diagnose_hrds.py 192.168.1.50 --port 8899 --unit 1
    python3 tests/diagnose_hrds.py 192.168.1.50 --scan-ids 1-10
    python3 tests/diagnose_hrds.py 192.168.1.50 --sweep 0-300,1700-1900 --json out.json

Exit code: 0 = nothing to act on, 1 = warnings/actions found, 2 = no comms.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import socket
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("pymodbus is required:  pip install pymodbus==3.13.1")

# const.py imports Home Assistant; reuse the stubs from wiring_check.py so this
# script needs nothing but pymodbus. The stubs also replace pymodbus.client, so
# put the real modules back before const.py is imported.
_real_pymodbus = {
    k: v for k, v in sys.modules.items() if k == "pymodbus" or k.startswith("pymodbus.")
}
import wiring_check  # noqa: E402

wiring_check.install_stubs()
sys.modules.update(_real_pymodbus)
const = wiring_check.load_const()

IN, HOLD = const.C_REG_TYPE_INPUT_REGISTERS, const.C_REG_TYPE_HOLDING_REGISTERS

# Registers that are documented (MODBUS_REGISTERS.md) but not entities. They are
# read purely for diagnosis. (name, function-code type, address, note)
EXTRA_REGISTERS: list[tuple[str, int, int, str]] = [
    ("OR_Alarms (any alarm)", IN, 1103, "0/1 cumulative alarm flag"),
    ("PackedAlarm_1", IN, 768, "AL01..AL16"),
    ("PackedAlarm_2", IN, 769, "AL17..AL32"),
    ("PackedAlarm_3", IN, 770, "AL33.."),
    ("FanIntegration_Request", IN, 1112, "fan-integration function active"),
    ("Packed_DO1", IN, 384, "compressor / damper / valve outputs"),
    ("Packed_DO2", IN, 385, "on/off, alarms outputs"),
    ("Packed_logicDI1", IN, 257, "digital inputs"),
    ("Modbus address (serial)", HOLD, 1773, "RTU address of the unit"),
    ("Baud (serial)", HOLD, 1774, "RTU baud code"),
    ("Parity (serial)", HOLD, 1775, "RTU parity code"),
    ("Stop bits (serial)", HOLD, 1776, "RTU stop-bit code"),
    ("PH01 Enable_OnOffByDisplay", HOLD, 1777, "set 0 if no wired display"),
    ("PH05 TemperatureUM", HOLD, 1781, "0=degC 1=degF"),
    ("PM00 Limit_FansHours", HOLD, 1602, "fan hours alarm limit"),
    ("PM01 SupplyFan_Hours", HOLD, 1604, "fan hours counter"),
]

# Alarm names from MODBUS_REGISTERS.md section 9.2 (others print as "ALnn").
ALARM_NAMES = {
    2: "High humidity",
    3: "High summer water temperature",
    4: "Low winter water temperature",
    11: "Compressor low-pressure / frost-thermostat",
    12: "Compressor high-pressure",
    16: "Water-circuit antifreeze",
    18: "Generic alarm",
    19: "Generic warning",
    22: "Dirty filters",
    25: "I/O configuration error",
    26: "RTC clock failed",
    28: "Room/return temperature probe fault",
    29: "External temperature probe fault",
    30: "Water temperature probe fault",
    34: "Room/return humidity probe fault",
    36: "Fan potentiometer fault",
    39: "Evaporator temperature probe fault",
}

OK, INFO, WARN, ACTION = "OK", "INFO", "WARN", "ACTION"
FINDINGS: list[tuple[str, str]] = []


def say(level: str, text: str) -> None:
    """Record a finding and print it."""
    FINDINGS.append((level, text))
    print(f"  [{level:6}] {text}")


def head(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 70 - len(title)))


# --------------------------------------------------------------------------
# Modbus helpers
# --------------------------------------------------------------------------
class Dev:
    """Thin read-only wrapper: every call returns (value, error-string)."""

    def __init__(self, client: ModbusTcpClient, unit: int, delay: float) -> None:
        self.c, self.unit, self.delay = client, unit, delay
        self.requests = 0

    def read(self, rt: int, addr: int, count: int = 1):
        self.requests += 1
        if self.delay:
            time.sleep(self.delay)
        try:
            fn = (
                self.c.read_input_registers
                if rt == IN
                else self.c.read_holding_registers
            )
            resp = fn(address=addr, count=count, device_id=self.unit)
        except Exception as exc:  # noqa: BLE001 - report, keep diagnosing
            return None, f"{type(exc).__name__}: {exc}"
        if resp is None:
            return None, "no response"
        if resp.isError():
            code = getattr(resp, "exception_code", None)
            return None, f"exception {code}" if code else str(resp)
        regs = list(getattr(resp, "registers", []) or [])
        if len(regs) != count:
            return None, f"short reply ({len(regs)}/{count})"
        return regs, None


def build_blocks(addresses, foreign=frozenset()):
    """Copy of ``_build_blocks`` in ``__init__.py`` (keep in sync).

    Duplicated because importing the integration package needs Home Assistant.
    """
    addresses = sorted({a for a in addresses if a is not None})
    if not addresses:
        return []
    blocks = []
    start = prev = addresses[0]
    for addr in addresses[1:]:
        fits = addr - prev <= const.C_MAX_GAP and addr - start + 1 <= const.C_MAX_BLOCK
        spans_foreign = any(a in foreign for a in range(prev + 1, addr))
        if fits and not spans_foreign:
            prev = addr
        else:
            blocks.append((start, prev - start + 1))
            start = prev = addr
    blocks.append((start, prev - start + 1))
    return blocks


def parse_ranges(spec: str) -> list[int]:
    """'1-5,9' -> [1,2,3,4,5,9]."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


# --------------------------------------------------------------------------
# Diagnostic steps
# --------------------------------------------------------------------------
def step_network(host: str, port: int, timeout: float) -> bool:
    head(f"1. TCP connection to {host}:{port}")
    try:
        with socket.create_connection((host, port), timeout=timeout):
            say(OK, "TCP port is open")
            return True
    except OSError as exc:
        say(ACTION, f"Cannot open {host}:{port}: {exc}")
        print("         Check IP, port (gateway default is 502) and firewall.")
        return False


def step_unit(dev: Dev, scan: list[int]) -> bool:
    head("2. Modbus unit (slave) id")
    ok = False
    regs, err = dev.read(IN, 1104)
    if regs is not None:
        say(OK, f"unit id {dev.unit} answers (unit status register 1104 = {regs[0]})")
        ok = True
    else:
        say(ACTION, f"unit id {dev.unit} did not answer register 1104: {err}")
    if scan:
        print(f"  scanning unit ids {scan[0]}..{scan[-1]} (register 1104):")
        found = []
        saved = dev.unit
        for uid in scan:
            dev.unit = uid
            r, _ = dev.read(IN, 1104)
            if r is not None:
                found.append(uid)
        dev.unit = saved
        say(INFO, f"unit ids that answered: {found or 'none'}")
        if found and saved not in found:
            say(ACTION, f"configured unit id {saved} is wrong; use one of {found}")
        if len(found) > 1:
            say(
                WARN,
                "several unit ids answer - the gateway ignores the id; "
                "it cannot be used to tell devices apart",
            )
    return ok


def step_identity(dev: Dev) -> dict[str, Any]:
    head("3. Device identification")
    ident: dict[str, Any] = {}

    # 3a. Standard Modbus Read Device Identification (FC 43 / MEI 14).
    got_fc43 = False
    for level, code in (("basic", 1), ("regular", 2), ("extended", 3)):
        try:
            resp = dev.c.read_device_information(read_code=code, device_id=dev.unit)
        except Exception as exc:  # noqa: BLE001
            say(INFO, f"FC43/14 {level}: not supported ({type(exc).__name__})")
            continue
        if resp is None or resp.isError():
            say(INFO, f"FC43/14 {level}: not supported ({resp})")
            continue
        info = {
            int(k): (v.decode("latin-1", "replace") if isinstance(v, bytes) else v)
            for k, v in getattr(resp, "information", {}).items()
        }
        if not info:
            say(INFO, f"FC43/14 {level}: reply carried no identification objects")
            continue
        ident[f"fc43_{level}"] = info
        got_fc43 = True
        say(OK, f"FC43/14 {level}: {info}")
    if not got_fc43:
        say(
            WARN,
            "no FC43 device identification - the gateway/unit does not "
            "provide vendor/model/firmware strings",
        )

    # 3b. Register fingerprint. These are configuration values that identify
    # the unit variant and its serial settings; they do not change in operation.
    fp_regs = [
        ("PG01_MachineType", HOLD, 1797),
        ("PG02_EnableIntegration", HOLD, 1798),
        ("PG03_EnableFreeCooling", HOLD, 1799),
        ("Serial address", HOLD, 1773),
        ("Serial baud", HOLD, 1774),
        ("Serial parity", HOLD, 1775),
        ("Serial stop bits", HOLD, 1776),
    ]
    parts = []
    for name, rt, addr in fp_regs:
        regs, err = dev.read(rt, addr)
        val = regs[0] if regs else None
        ident[name] = val
        parts.append(f"{addr}={val}")
        print(f"    {name:28} reg {addr:5} = {val if val is not None else err}")
    ident["fingerprint"] = "hrds:" + ",".join(parts)
    say(INFO, f"register fingerprint: {ident['fingerprint']}")

    # 3c. Plausibility: does the status block decode like an HRDS+?
    checks = []
    for key, valid in (
        (const.C_UNIT_STATUS, const.UNIT_STATUS),
        (const.C_MODE_STATUS, const.MODE_STATUS),
        (const.C_SUPPLY_FAN_STATUS, const.FAN_STATUS),
        (const.C_COMPRESSOR_STATUS, const.COMPRESSOR_STATUS),
    ):
        props = const.get_entity_props(key)
        regs, _ = dev.read(IN, const.get_entity_reg(props)[0])
        checks.append(regs is not None and regs[0] in valid)
    ident["status_enums_valid"] = f"{sum(checks)}/{len(checks)}"
    level = OK if all(checks) else WARN
    say(
        level,
        f"status registers hold documented enum values: {ident['status_enums_valid']}",
    )
    say(
        INFO,
        "The register map documents no serial number or firmware "
        "register. Use --sweep to look for undocumented ones.",
    )
    say(
        INFO,
        "Suggested integration identity check: FC43 strings if present, "
        "else PG01/PG02 + serial-address registers above + status enums valid.",
    )
    return ident


def step_read_all(dev: Dev) -> dict[str, dict[str, Any]]:
    head("4. Full read using the integration's own block plan")
    in_addrs = [
        const.get_entity_reg(p)[0]
        for p in const.ENTITIES_DICT.values()
        if const.get_entity_type(p) == IN
    ]
    hold_addrs = [
        const.get_entity_reg(p)[0]
        for p in const.ENTITIES_DICT.values()
        if const.get_entity_type(p) == HOLD
    ]
    plans = {
        IN: build_blocks(in_addrs, frozenset(hold_addrs)),
        HOLD: build_blocks(hold_addrs, frozenset(in_addrs)),
    }
    raw: dict[tuple[int, int], int] = {}
    bad_blocks = 0
    for rt, blocks in plans.items():
        label = "input (FC04)" if rt == IN else "holding (FC03)"
        print(f"  {label}: {len(blocks)} blocks: {blocks}")
        for start, count in blocks:
            regs, err = dev.read(rt, start, count)
            if regs is not None:
                for i, v in enumerate(regs):
                    raw[(rt, start + i)] = v
                continue
            bad_blocks += 1
            say(
                WARN,
                f"{label} block {start}+{count} failed ({err}); the "
                "integration would retry register-by-register",
            )
            for addr in range(start, start + count):
                r, _ = dev.read(rt, addr)
                if r is not None:
                    raw[(rt, addr)] = r[0]
    if not bad_blocks:
        say(OK, "every block read succeeded (integration block plan is valid)")

    rows: dict[str, dict[str, Any]] = {}
    missing = []
    print(f"\n  {'key':32}{'reg':>6} {'raw':>7}  value")
    for key, props in const.ENTITIES_DICT.items():
        reg, dt = const.get_entity_reg(props)
        rt = const.get_entity_type(props)
        if (rt, reg) not in raw:
            missing.append(f"{key}({reg})")
            print(f"  {key:32}{reg:>6} {'-':>7}  NO ANSWER")
            continue
        r = raw[(rt, reg)]
        v = ModbusTcpClient.convert_from_registers(registers=[r], data_type=dt)
        bit = const.get_entity_bitmask(props)
        if const.is_entity_switch(props):
            if bit is not None:
                on = bool((v >> bit) & 1)
                on = (not on) if props.get("BITMASK_INVERT") else on
            else:
                on = v != (const.get_entity_switch(props) or {}).get("off", 0)
            dec: Any = "on" if on else "off"
        elif const.is_entity_select(props):
            dec = (const.get_entity_select(props) or {}).get(v, f"UNMAPPED({v})")
        else:
            dec = round(float(v) * const.get_entity_factor(props), 3)
        unit = const.get_entity_unit(props) or ""
        rows[key] = {"reg": reg, "type": rt, "raw": r, "value": dec, "unit": unit}
        print(f"  {key:32}{reg:>6} {r:>7}  {dec} {unit}")
        if isinstance(dec, str) and dec.startswith("UNMAPPED"):
            say(WARN, f"{key}: raw {r} is not a documented value")
    if missing:
        say(
            WARN,
            f"{len(missing)} integration registers did not answer: "
            f"{', '.join(missing)}",
        )
    else:
        say(OK, f"all {len(rows)} integration registers answered")
    rows["_raw"] = {f"{rt}:{a}": v for (rt, a), v in raw.items()}  # type: ignore
    return rows


def step_extras(dev: Dev) -> dict[str, int | None]:
    head("5. Additional diagnostic registers (not integration entities)")
    out: dict[str, int | None] = {}
    for name, rt, addr, note in EXTRA_REGISTERS:
        regs, err = dev.read(rt, addr)
        out[f"{addr}"] = regs[0] if regs else None
        shown = regs[0] if regs else f"({err})"
        print(f"  {name:30} reg {addr:5} = {shown!s:>8}   {note}")
    return out


def alarms_active(values: dict[str, int | None]) -> list[int]:
    """Decode PackedAlarm_1..3 into active AL numbers."""
    active = []
    for addr, base in (("768", 1), ("769", 17), ("770", 33)):
        word = values.get(addr)
        if word is None:
            continue
        active += [base + b for b in range(16) if (word >> b) & 1]
    return active


def step_sensors(rows: dict, extras: dict) -> None:
    head("6. Sensors / probes: what is actually connected")
    al = set(alarms_active(extras))

    def val(key):
        r = rows.get(key)
        return None if r is None else r["value"], None if r is None else r["raw"]

    # (key, label, alarm that proves a missing probe, plausible low, high)
    probes = [
        (const.C_ROOM_TEMPERATURE, "Room temp (499)", 28, -20, 60),
        (const.C_ROOM_HUMIDITY, "Room humidity (505)", 34, 1, 100),
        (const.C_WATER_TEMPERATURE, "Water temp (501) [factory]", 30, -20, 90),
        (const.C_EVAPORATOR_TEMPERATURE, "Evaporator (511) [factory]", 39, -30, 90),
        (const.C_OUTDOOR_TEMPERATURE, "Outdoor temp (500)", 29, -40, 60),
        (const.C_EXHAUST_TEMPERATURE, "Exhaust temp (502)", None, -40, 80),
        (const.C_SUPPLY_TEMPERATURE, "Discharge temp (503)", None, -40, 80),
        (const.C_AIR_QUALITY, "Air quality (506)", None, 1, 10000),
    ]
    print(f"  {'probe':30}{'value':>10}  verdict")
    for key, label, alarm, lo, hi in probes:
        v, r = val(key)
        if v is None:
            print(f"  {label:30}{'-':>10}  NOT READABLE")
            continue
        sentinel = r in (0x7FFF, 0x8000, 0xFFFF)
        plausible = lo <= v <= hi and not sentinel
        if alarm in al:
            verdict = f"NOT CONNECTED / FAULT (AL{alarm} active)"
            if key in (const.C_ROOM_TEMPERATURE, const.C_ROOM_HUMIDITY):
                say(
                    INFO,
                    f"{label}: AL{alarm} active - automatic dehumidify "
                    "will not run on its own; HA must send explicit requests",
                )
        elif sentinel or not plausible:
            verdict = "implausible value - probably not connected"
        elif alarm is not None:
            verdict = "connected (plausible, no fault alarm)"
        else:
            verdict = "plausible - no fault alarm exists, cannot confirm wiring"
        print(f"  {label:30}{v:>10}  {verdict}")
    if (v := val(const.C_ROOM_TEMPERATURE)[0]) is not None and 28 not in al:
        t_out = val(const.C_OUTDOOR_TEMPERATURE)[0]
        if t_out is not None and v == t_out:
            say(
                WARN,
                "room and outdoor temperature are identical - one may be "
                "a default/placeholder reading",
            )


def step_alarms(extras: dict) -> None:
    head("7. Active alarms")
    active = alarms_active(extras)
    if not active:
        say(OK, "no alarm bits set")
        return
    for n in active:
        say(WARN, f"AL{n:02} active: {ALARM_NAMES.get(n, 'see handbook alarm table')}")


def step_settings(rows: dict, extras: dict, ident: dict, model: str | None) -> None:
    head("8. Settings review and first-connect behaviour")

    def g(key):
        r = rows.get(key)
        return None if r is None else r["value"]

    # --- 8a. What the integration writes on connect ----------------------
    print("  What the integration WRITES when it connects (FC06, value 1):")
    print("    Cycle 1 has no cached data, so it writes ALL of these, even if")
    print("    they are already 1; later cycles only re-write one that reads 0.")
    for key in const.BMS_ENABLE_KEYS:
        props = const.get_entity_props(key)
        reg = const.get_entity_reg(props)[0]
        cur = g(key)
        state = {"on": "already 1 (write is a no-op)", "off": "currently 0 -> CHANGES"}
        print(f"    reg {reg} {const.get_entity_name(props):36} {state.get(cur, '?')}")
        if cur != "on":
            say(
                ACTION,
                f"integration will change {key} (reg {reg}) 0 -> 1 on first connect",
            )
    say(
        INFO,
        "No other register is written on connect; all further writes "
        "happen only on user action (switches, numbers, climate, fan).",
    )
    say(INFO, "Writes are skipped by the unit unless the enables above are 1.")

    # --- 8b. Settings the integration does NOT change ---------------------
    print("\n  Settings to review (the integration does NOT change these):")
    ph01 = extras.get("1777")
    ha00 = g(const.C_PROBE_SOURCE)
    room_t = g(const.C_ROOM_TEMPERATURE)
    unit_status = g(const.C_UNIT_STATUS)
    al = set(alarms_active(extras))

    if extras.get("1781") == 1:
        say(
            ACTION,
            "PH05 temperature unit is degF; the integration assumes degC. "
            "Set PH05=0 on the unit.",
        )
    if unit_status in ("off_by_display", "off_by_di", "off_by_scheduler", "off_by_rtc"):
        say(
            WARN,
            f"unit status is '{unit_status}'. An OFF from another source "
            "wins over Modbus ON; the unit cannot be started from HA until that "
            "source is cleared (e.g. PH01=0 when no display is fitted).",
        )
    elif unit_status == "off_by_bms":
        say(INFO, "unit is OFF by BMS - expected; HA can turn it on.")
    if ph01 == 1 and {28, 34} & al:
        say(
            WARN,
            "PH01 (reg 1777)=1 means a display is expected and the room "
            "probes are missing (AL28/AL34). With no display fitted set PH01=0 "
            "(wired remote installer menu or service tool; the integration "
            "does not expose it).",
        )
    if ha00 is not None and ha00 != "none_or_external" and {28, 34} & al:
        say(
            ACTION,
            f"probe source HA00 is '{ha00}' and probe-fault alarms are "
            "active. With no display and no external probes set HA00=0 "
            "(select entity `probe_source`, or write reg 1803 = 0).",
        )
    elif ha00 == "none_or_external" and {28, 34} & al:
        say(
            INFO,
            "HA00=0 but room probe alarms active: no external probe wired "
            "on AI2/AI3 - expected for a headless setup; HA must send requests.",
        )
    pg01, pg02, pg03 = (
        ident.get("PG01_MachineType"),
        ident.get("PG02_EnableIntegration"),
        ident.get("PG03_EnableFreeCooling"),
    )
    if pg01 == 0:
        say(
            INFO,
            "PG01=0: dehumidifier-only (non-R variant), no recirculation "
            "fan; fan_manual_speed has no effect on airflow.",
        )
    elif pg01 == 1:
        say(INFO, "PG01=1: has recirculation fan/damper (R variant).")
    if pg02 == 0:
        say(
            INFO,
            "PG02=0: active cooling is not enabled/available (non-DC); "
            "keep active_cooling off.",
        )
    if pg03 == 1:
        say(
            WARN,
            "PG03=1: free cooling/heating enabled; the unit may act on "
            "outdoor temperature. Leave 0 if the Comfo owns free cooling.",
        )
    pu13 = g(const.C_MIN_ROOM_TEMP_DEHUM)
    if pu13 is not None and room_t is not None and 28 not in al and room_t < pu13:
        say(
            WARN,
            f"room temp {room_t} < PU13 {pu13}: the unit will refuse to "
            "dehumidify even if HA requests it.",
        )
    elif pu13 is not None and 28 in al:
        say(
            INFO,
            f"PU13={pu13} degC min room temp interlock; no room probe, so "
            "check it does not veto Modbus dehumidify requests (test it).",
        )
    lo, hi, sp = (
        g(const.C_HUMIDITY_SETPOINT_MIN),
        g(const.C_HUMIDITY_SETPOINT_MAX),
        g(const.C_HUMIDITY_SETPOINT),
    )
    if None not in (lo, hi, sp) and not lo <= sp <= hi:
        say(WARN, f"humidity setpoint PU01={sp} is outside PH29..PH30 ({lo}..{hi})")
    fmin, fmax = g(const.C_FAN_MIN_DEHUM), g(const.C_FAN_MAX_DEHUM)
    if fmin is not None and fmax is not None:
        say(
            INFO,
            f"dehumidify fan band PF28..PF10 = {fmin}%..{fmax}% (a manual "
            "request is scaled across this band - verify on hardware)",
        )
    if model:
        say(
            INFO,
            f"configured model '{model}': 30/50 has NO register; the "
            "airflow figure depends on this config option.",
        )
    else:
        say(
            INFO,
            "model 30 vs 50 cannot be read from the unit; read it from the "
            "type plate (HRDS+ 30/50 ...) and set it in the integration config.",
        )


def step_sweep(dev: Dev, spec: str, limit: int) -> dict[str, list[int]]:
    head(f"9. Sweep of undocumented registers ({spec})")
    addrs = parse_ranges(spec)
    if len(addrs) > limit:
        say(WARN, f"sweep truncated to first {limit} addresses (--sweep-max)")
        addrs = addrs[:limit]
    found: dict[str, list[tuple[int, int]]] = {"input": [], "holding": []}
    for addr in addrs:
        for rt, label in ((IN, "input"), (HOLD, "holding")):
            r, _ = dev.read(rt, addr)
            if r is not None:
                found[label].append((addr, r[0]))
    for label, items in found.items():
        print(f"  {label}: {len(items)} readable addresses")
        for addr, v in items:
            ascii_ = (
                chr(v >> 8) + chr(v & 255)
                if all(32 <= b < 127 for b in (v >> 8, v & 255))
                else ""
            )
            print(
                f"    {addr:5} = {v:5} (0x{v:04X}) {ascii_!r}"
                if ascii_
                else f"    {addr:5} = {v:5} (0x{v:04X})"
            )
    say(
        INFO,
        "Look for runs of ASCII-looking words: those would be a serial or "
        "firmware string usable for identity checks.",
    )
    return {k: [a for a, _ in v] for k, v in found.items()}


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read-only HRDS+ Modbus bring-up diagnostic (never writes).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("host", help="IP/hostname of the Modbus TCP gateway")
    ap.add_argument(
        "--port",
        type=int,
        default=const.DEFAULT_PORT,
        help="Modbus TCP port (same value as the integration's port option)",
    )
    ap.add_argument(
        "--unit",
        type=int,
        default=const.DEFAULT_HOSTID,
        help="Modbus unit/slave id (integration option 'hostid')",
    )
    ap.add_argument(
        "--model",
        choices=const.MODELS,
        default=None,
        help="model configured in the integration (30 or 50)",
    )
    ap.add_argument("--timeout", type=float, default=3.0, help="seconds per request")
    ap.add_argument("--retries", type=int, default=1, help="pymodbus retries")
    ap.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="seconds between requests (slow gateways)",
    )
    ap.add_argument(
        "--scan-ids", default="", help="also probe these unit ids, e.g. 1-10"
    )
    ap.add_argument(
        "--sweep",
        default="",
        help="read-only scan of address ranges, e.g. 0-300,1700-1900",
    )
    ap.add_argument(
        "--sweep-max", type=int, default=3000, help="cap on swept addresses"
    )
    ap.add_argument("--json", metavar="FILE", help="write the full result as JSON")
    args = ap.parse_args()

    print(
        f"HRDS+ diagnostic - {args.host}:{args.port} unit {args.unit} "
        "(READ-ONLY: FC03/FC04/FC43 only)"
    )
    if not step_network(args.host, args.port, args.timeout):
        return 2
    client = ModbusTcpClient(
        host=args.host, port=args.port, timeout=args.timeout, retries=args.retries
    )
    if not client.connect():
        say(ACTION, "Modbus client could not connect")
        return 2
    dev = Dev(client, args.unit, args.delay)
    result: dict[str, Any] = {"host": args.host, "port": args.port, "unit": args.unit}
    try:
        if not step_unit(dev, parse_ranges(args.scan_ids)):
            say(
                ACTION,
                "No Modbus answer; stopping. Check unit id, gateway "
                "serial settings (baud/parity) and that the unit is powered.",
            )
            return 2
        result["identity"] = step_identity(dev)
        rows = step_read_all(dev)
        extras = step_extras(dev)
        step_sensors(rows, extras)
        step_alarms(extras)
        step_settings(rows, extras, result["identity"], args.model)
        result.update(registers=rows, extras=extras)
        if args.sweep:
            result["sweep"] = step_sweep(dev, args.sweep, args.sweep_max)
    finally:
        client.close()

    head("Summary")
    counts = {
        lvl: sum(1 for level, _ in FINDINGS if level == lvl)
        for lvl in (OK, INFO, WARN, ACTION)
    }
    print(
        f"  {dev.requests} read requests; "
        + ", ".join(f"{n} {lvl}" for lvl, n in counts.items())
    )
    for lvl in (ACTION, WARN):
        for level, text in FINDINGS:
            if level == lvl:
                print(f"  [{level}] {text}")
    result["findings"] = FINDINGS
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(result, indent=2, default=str))
        print(f"  full result written to {args.json}")
    return 1 if counts[ACTION] or counts[WARN] else 0


if __name__ == "__main__":
    sys.exit(main())
