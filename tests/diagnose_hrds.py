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

Requirements:  pip install 'pymodbus>=3.13.1'   (the version HA 2026.10 ships)

Examples:
    python3 tests/diagnose_hrds.py 192.168.1.50
    python3 tests/diagnose_hrds.py 192.168.1.50 --port 8899 --unit 1
    python3 tests/diagnose_hrds.py 192.168.1.50 --scan-ids 1-10
    python3 tests/diagnose_hrds.py 192.168.1.50 --sweep 0-300,1700-1900 --json tests/devices/<model>_<display|headless>_<state>.json
    python3 tests/diagnose_hrds.py 192.168.1.50 --watch 300 --no-snapshot

Besides the integration's own registers it takes a read-only SNAPSHOT of the
unit's configuration area (holding 1590-1900) and its status/output areas, so
I/O allocations (HD01 damper relay, fan outputs), PS01 and similar parameters can
be inspected. ``--watch SECONDS`` then polls the status/output registers and
prints every change, e.g. while you start a dehumidify from the display or HA,
to see the damper, fan and compressor sequence.

Exit code: 0 = nothing to act on, 1 = warnings/actions found, 2 = no comms.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import socket
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("pymodbus is required:  pip install 'pymodbus>=3.13.1'")

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
    ("PH01 Enable_OnOffByDisplay", HOLD, 1777, "integration sets 0 if headless"),
    ("PH05 TemperatureUM", HOLD, 1781, "0=degC 1=degF"),
    ("PM00 Limit_FansHours", HOLD, 1602, "fan hours alarm limit"),
    ("PM01 SupplyFan_Hours", HOLD, 1604, "fan hours counter"),
]

# Configuration parameters with the handbook's factory default. Addresses are
# from the Modbus manual's full parameter table (0x0640-0x077A); the
# integration's installer device exposes the rest (installer_params.py).
# (address, code, description, handbook default or None)
PARAMS: list[tuple[int, str, str, int | None]] = [
    (1698, "PS01", "Recirculation damper pre-start time (s)", 20),
    (1777, "PH01", "Unit on/off via display", 1),
    (1778, "PH02", "Unit on/off via Modbus", 0),
    (1779, "PH03", "Enable time programs", 0),
    (1780, "PH04", "Unit state in holiday", None),
    (1781, "PH05", "Temperature unit (0=C 1=F)", None),
    (1803, "HA00", "T/H probe source (0=none, 6=CNU2 T+H)", 6),
    (1804, "HA01", "AI1 allocation (M1 fan potentiometer)", 58),
    (1805, "HA02", "AI2 allocation (M2; 45 = room temp probe)", 0),
    (1806, "HA03", "AI3 allocation (M3; 53/54 = room humidity probe)", 0),
    (1807, "HA04", "AI4 allocation (M4 evaporator temp)", 52),
    (1808, "HA05", "AI5 allocation (M5 water temp)", 47),
    (1809, "HA06", "AI6 allocation (M6 dehumidify request DI)", 6),
    (1810, "HA07", "AI7 allocation (M7 integration request DI)", 8),
    (1822, "HB01", "DI1 allocation (high pressure NC)", 27),
    (1823, "HB02", "DI2 allocation (low pressure NO)", 26),
    (1824, "HB03", "DI3 allocation (M8 remote ON/OFF; 2=NO 1=NC)", 2),
    (1825, "HB04", "DI4 allocation (M9 summer/winter; 4=NO 3=NC)", 4),
    (1829, "HC01", "AO1 allocation (0-10 V compressor)", 5),
    (1830, "HC02", "AO2 allocation", 0),
    (1831, "HC03", "AO3 allocation", 0),
    (1832, "HC04", "AO4 allocation (0-10 V supply fan)", 1),
    (1838, "HD01", "DO1 allocation (K1 recirculation damper NO)", 10),
    (1839, "HD02", "DO2 allocation (K2 serious alarm NO)", 26),
    (1878, "PC11", "Season change owner (0=display 1=DI)", None),
    # PC12 is 1894 per the Modbus manual's parameter table (1879 is PE24).
    (1894, "PC12", "Unit on by DI request despite open OFF contact", 0),
    (1889, "PU13", "Min room temp for dehumidify (x0.1 C)", 220),
    (1890, "PU14", "Room temp differential to re-enable (x0.1 C)", 5),
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
    else:
        fc43 = (
            ident["fc43_basic"] if "fc43_basic" in ident else next(iter(ident.values()))
        )
        vendor, product = str(fc43.get(0, "")), str(fc43.get(1, ""))
        if (
            vendor.strip().upper() == const.EXPECTED_VENDOR
            and product.upper().startswith(const.EXPECTED_PRODUCT_PREFIX)
        ):
            say(
                OK,
                f"identity check passes: {vendor} {product} (integration accepts it)",
            )
        else:
            say(
                ACTION,
                f"identity check FAILS: {vendor!r} {product!r}, integration expects "
                f"{const.EXPECTED_VENDOR!r} {const.EXPECTED_PRODUCT_PREFIX}* and would "
                "refuse to set up",
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
        "The register map documents no serial number register (FC43 gives the "
        "firmware revision only). Use --sweep to look for undocumented ones.",
    )
    say(
        INFO,
        "The integration's identity check (identity.py) is: FC43 vendor/product "
        "if the gateway forwards it, AND all status registers hold documented "
        "enum values.",
    )
    return ident


def step_read_all(dev: Dev) -> dict[str, dict[str, Any]]:
    head("4. Full read using the integration's own block plan")
    # Same groups as the hub: the regular poll, and the installer menu (read
    # on its own, at setup and on its refresh button). A block never spans an
    # address of another group or of the other function code.
    all_addrs = {
        rt: frozenset(
            const.get_entity_reg(p)[0]
            for p in const.ENTITIES_DICT.values()
            if const.get_entity_type(p) == rt
        )
        for rt in (IN, HOLD)
    }
    groups = {
        "poll": set(const.ENTITIES_DICT) - const.INSTALLER_KEYS,
        "installer": set(const.INSTALLER_KEYS),
    }
    plans = []
    for group, keys in groups.items():
        for rt in (IN, HOLD):
            addrs = {
                const.get_entity_reg(const.ENTITIES_DICT[k])[0]
                for k in keys
                if const.get_entity_type(const.ENTITIES_DICT[k]) == rt
            }
            if addrs:
                foreign = (all_addrs[IN] | all_addrs[HOLD]) - addrs
                plans.append((group, rt, build_blocks(addrs, foreign)))
    raw: dict[tuple[int, int], int] = {}
    bad_blocks = 0
    for group, rt, blocks in plans:
        label = f"{group} " + ("input (FC04)" if rt == IN else "holding (FC03)")
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
                "integration would retry with smaller blocks or "
                "register-by-register",
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
        if (
            dt == const.C_DT_INT16
            and not const.is_entity_switch(props)
            and not const.is_entity_select(props)
            and const.is_probe_sentinel(r)
        ):
            # Unwired/failed analog input: the integration reports no value.
            dec = None
        elif const.is_entity_switch(props):
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
        shown = f"no probe (0x{r:04X})" if dec is None else f"{dec} {unit}"
        print(f"  {key:32}{reg:>6} {r:>7}  {shown}")
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
        if r is None:
            print(f"  {label:30}{'-':>10}  NOT READABLE")
            continue
        if v is None:
            # The integration decodes this word to "no value" (unknown).
            print(f"  {label:30}{'-':>10}  NO PROBE (input reads 0x{r:04X})")
            if key in (const.C_ROOM_TEMPERATURE, const.C_ROOM_HUMIDITY):
                say(
                    INFO,
                    f"{label}: no probe wired - automatic dehumidify cannot "
                    "run on its own; HA must send explicit requests. The "
                    "climate entity shows no current temperature/humidity.",
                )
            continue
        plausible = lo <= v <= hi
        if alarm in al:
            verdict = f"NOT CONNECTED / FAULT (AL{alarm} active)"
            if key in (const.C_ROOM_TEMPERATURE, const.C_ROOM_HUMIDITY):
                say(
                    INFO,
                    f"{label}: AL{alarm} active - automatic dehumidify "
                    "will not run on its own; HA must send explicit requests",
                )
        elif not plausible:
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


def step_settings(
    rows: dict, extras: dict, ident: dict, model: str | None, has_display: bool
) -> None:
    head("8. Settings review and first-connect behaviour")

    def g(key):
        r = rows.get(key)
        return None if r is None else r["value"]

    # --- 8a. What the integration writes on connect ----------------------
    # Mirrors HrdsModbusHub._required_settings (keep in sync).
    required = []
    if not has_display:
        required += [(k, d, raw) for k, (d, raw) in const.HEADLESS_SETTINGS.items()]
    mode = "display fitted" if has_display else "headless (no display)"
    print(f"  What the integration WRITES when it connects [{mode}]:")
    print("    Only a setting that reads differently (never one that already")
    print("    holds the value); the Modbus enables below are yours to set.")
    if not required:
        print("    nothing")
    for key, want, raw in required:
        props = const.get_entity_props(key)
        reg = const.get_entity_reg(props)[0]
        cur = g(key)
        state = (
            f"already {want} (write is a no-op)"
            if cur == want
            else f"currently {cur} -> CHANGES to {want} ({raw})"
        )
        print(f"    reg {reg} {const.get_entity_name(props):36} {state}")
        if cur != want:
            say(
                ACTION,
                f"integration will change {key} (reg {reg}) {cur} -> {want} "
                "on first connect",
            )
    say(
        INFO,
        "No other register is written on connect; all further writes "
        "happen only on user action (switches, numbers, climate, fan).",
    )
    say(INFO, "Writes are skipped by the unit unless the BMS enables are 1.")

    # --- 8b. Settings the integration does NOT change ---------------------
    print("\n  Settings to review (the integration does NOT change these):")
    room_t = g(const.C_ROOM_TEMPERATURE)
    unit_status = g(const.C_UNIT_STATUS)

    if extras.get("1781") == 1:
        say(
            ACTION,
            "PH05 temperature unit is degF; the integration assumes degC. "
            "Set PH05=0 on the unit.",
        )
    if unit_status == "off_by_display" and not has_display:
        say(
            INFO,
            "unit status is 'off_by_display' with no display. The integration "
            "clears PH01 on connect, but a real unit kept this stored OFF even "
            "after PH01=0 and a power cycle; the first Modbus ON (Unit on/off) "
            "cleared it. Expect 'off_by_bms' only on units that follow the manual.",
        )
    elif unit_status in (
        "off_by_display",
        "off_by_di",
        "off_by_scheduler",
        "off_by_rtc",
    ):
        say(
            WARN,
            f"unit status is '{unit_status}'. An OFF from another source "
            "wins over Modbus ON; the unit cannot be started from HA until that "
            "source is cleared.",
        )
    elif unit_status == "off_by_bms":
        say(INFO, "unit is OFF by BMS - expected; HA can turn it on.")
    if has_display:
        say(
            INFO,
            "display mode: the integration leaves PH01/HA00 alone, so the "
            "display keeps its on/off control and supplies room T/H.",
        )
    # PG01 is the fan arrangement, NOT "has a recirculation fan".
    pg01, pg02, pg03 = (
        ident.get("PG01_MachineType"),
        ident.get("PG02_EnableIntegration"),
        ident.get("PG03_EnableFreeCooling"),
    )
    if pg01 is not None:
        say(
            INFO,
            f"PG01={pg01}: "
            + (
                "supply fan only (this is also what an R unit reads - its "
                "single fan is the recirculation fan)"
                if pg01 == 0
                else "supply and exhaust fan"
            ),
        )
    damper = g(const.C_RECIRCULATION_DAMPER)
    if damper == "disabled":
        say(
            INFO,
            "recirculation damper output is 'disabled': no damper wired "
            "(non-R unit). It dehumidifies on passive MVHR flow only.",
        )
    elif damper is not None:
        say(
            INFO,
            f"recirculation damper output present (state '{damper}'): R unit. "
            "Every dehumidify/integration request opens the damper and runs "
            "the fan; writing fan 0 does not prevent that (UNIT_BEHAVIOUR.md "
            "9.3).",
        )
    if pg02 == 0:
        say(
            INFO,
            "PG02=0: active cooling is not enabled/available (non-DC); "
            "keep the integration request off.",
        )
    if pg03 == 1:
        say(
            WARN,
            "PG03=1: free cooling/heating enabled; the unit may act on "
            "outdoor temperature. Leave 0 if the Comfo owns free cooling.",
        )
    pu13 = g(const.C_MIN_ROOM_TEMP_DEHUM)
    if pu13 is not None and room_t is not None and room_t < pu13:
        say(
            WARN,
            f"room temp {room_t} < PU13 {pu13}: the unit will refuse to "
            "dehumidify even if HA requests it.",
        )
    elif pu13 is not None and room_t is None:
        say(
            INFO,
            f"PU13={pu13} degC min room temp interlock; there is no room "
            "temperature, so check it does not veto Modbus dehumidify "
            "requests (test it; set PU13 to 0 if it does).",
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


def step_inputs(dev: Dev) -> dict[str, Any]:
    """Scan the whole analog-input area: which inputs carry a real value?

    A sensor-less unit still needs to know which sensors it *could* use. The
    named probes are only part of the story (504 and 507-510 are not in the
    register map), so every readable register in the area is classified.
    """
    head("6b. Analog input scan: which inputs carry a real value")
    lo, hi = 480, 512  # 513+ are plain zero registers, not inputs
    got = read_area(dev, IN, lo, hi)
    names = doc_names()
    alloc = {}
    for addr, code in ((1804, "HA01"), (1805, "HA02"), (1806, "HA03")) + tuple(
        (1807 + i, f"HA0{4 + i}") for i in range(4)
    ):
        r, _ = dev.read(HOLD, addr)
        alloc[code] = r[0] if r else None
    live, silent = [], []
    print(f"  {'reg':>5}  {'raw':>6}  {'x0.1':>8}  state / name")
    for addr, raw in sorted(got.items()):
        name = names.get((IN, addr)) or names.get((0, addr)) or "(not in register map)"
        if const.is_probe_sentinel(raw):
            silent.append(addr)
            print(f"  {addr:>5}  {raw:>6}  {'-':>8}  no signal (0x{raw:04X})  {name}")
            continue
        signed = raw - 0x10000 if raw >= 0x8000 else raw
        live.append((addr, raw, signed, name))
        print(f"  {addr:>5}  {raw:>6}  {signed / 10:>8.1f}  REAL VALUE  {name}")
    print(
        "\n  Input allocations (0 = input unused): "
        + ", ".join(f"{k}={v}" for k, v in alloc.items())
    )
    if live:
        say(
            OK,
            "inputs with a real value: "
            + "; ".join(f"{a} ({n}) raw {r}" for a, r, _s, n in live),
        )
    else:
        say(WARN, "no analog input carries a real value")
    unnamed = [a for a, _r, _s, n in live if n == "(not in register map)"]
    if unnamed:
        say(
            WARN,
            f"live inputs {unnamed} are not in the register map: identify them "
            "(compare with a known temperature; x0.1 may not be the scale)",
        )
    say(
        INFO,
        f"{len(silent)} inputs read the 'no signal' word. That means unwired OR "
        "not allocated (AI2/AI3 allocation 0 = unused): a probe attached to an "
        "unallocated input would look the same. Only the factory-wired water (501) "
        "and evaporator (511) probes are expected to be live on a bare unit.",
    )
    return {
        "live": {str(a): r for a, r, _s, _n in live},
        "no_signal": silent,
        "allocations": alloc,
    }


def step_headless(dev: Dev, rows: dict, extras: dict) -> dict[str, Any]:
    """Can this unit run with no display and no room sensors, driven by Modbus?

    Everything here is from the technical handbook (sections 3, 4.5, 6.1, 6.3,
    6.7, 8.1 and the parameter table). Read-only.
    """
    head("9. Readiness for display-less, sensor-less operation over Modbus")
    cfg: dict[str, int | None] = {}
    for addr, _code, _desc, _d in PARAMS:
        r, _ = dev.read(HOLD, addr)
        cfg[str(addr)] = r[0] if r else None

    def c(addr: int) -> int | None:
        return cfg.get(str(addr))

    def g(key):
        r = rows.get(key)
        return None if r is None else r["value"]

    # 9a. Parameters that differ from the factory defaults ------------------
    print("  Parameters that differ from the handbook factory default:")
    differs = 0
    for addr, code, desc, default in PARAMS:
        v = c(addr)
        if default is None or v is None or v == default:
            continue
        differs += 1
        print(f"    {code} (reg {addr}) = {v}, default {default}   {desc}")
    if not differs:
        print("    none")
    print("  (addresses other than PH05/HA00/HB04/HD01 are inferred, see PARAMS)")

    # 9b. The conditions, one by one ---------------------------------------
    print("\n  Conditions for starting the unit from Home Assistant:")
    unit_status = g(const.C_UNIT_STATUS)
    say(INFO, f"current unit status: {unit_status}")

    ph01, ha00 = c(1777), c(1803)
    say(
        OK if ph01 == 0 else INFO,
        f"PH01 (display on/off) = {ph01}: "
        + (
            "off, as needed"
            if ph01 == 0
            else "1 keeps the unit OFF-by-display with no display; the "
            "integration writes 0 in headless mode"
        ),
    )
    say(
        OK if ha00 == 0 else INFO,
        f"HA00 (T/H source) = {ha00}: "
        + (
            "none, as needed"
            if ha00 == 0
            else "expects display sensors; the integration writes 0 in headless mode"
        ),
    )
    ha02, ha03 = c(1805), c(1806)
    if ha02 is None:
        say(WARN, "HA02 (AI2, reg 1805) did not answer")
    elif ha02 != 0:
        say(
            WARN,
            f"HA02 (AI2) = {ha02}: a room temperature probe is configured. With "
            "no probe wired the unit raises AL28 and disables the controls that "
            "depend on it. Set HA02 = 0 for a sensor-less unit (the integration "
            "does not change it).",
        )
    else:
        say(OK, f"HA02 (AI2) = {ha02}: no room temperature probe configured")
    if ha03 is None:
        say(WARN, "HA03 (AI3, reg 1806) did not answer")
    elif ha03 != 0:
        say(
            WARN,
            f"HA03 (AI3) = {ha03}: a room humidity probe is configured. With no "
            "probe wired the unit raises AL34. Set HA03 = 0 for a sensor-less unit.",
        )
    else:
        say(OK, f"HA03 (AI3) = {ha03}: no room humidity probe configured")

    for key, code in (
        (const.C_ENABLE_ONOFF_BMS, "PH02 on/off"),
        (const.C_ENABLE_DEHUM_BMS, "PH28 dehumidify"),
        (const.C_ENABLE_INT_BMS, "PH27 integration"),
    ):
        v = g(key)
        say(
            OK if v == "on" else INFO,
            f"{code} via Modbus = {v}"
            + (
                ""
                if v == "on"
                else ": Home Assistant can only observe this function; turn the "
                "matching 'Enable ... via Modbus' switch on to control it"
            ),
        )

    # Remote ON/OFF contact (DI3, OFF/OFF terminals): open = forced OFF.
    di_word = extras.get("257")
    hb03 = c(1824)
    if di_word is not None:
        remote = di_word & 3
        say(
            INFO,
            f"remote ON/OFF contact field in Packed_logicDI1 = {remote} "
            f"(HB03 = {hb03}; 2 = normally-open, active when closed)",
        )
        if remote == 0:
            say(
                ACTION,
                "the remote ON/OFF contact (DI3, terminals OFF/OFF) looks OPEN: "
                "an open contact forces the unit OFF and beats display and "
                "Modbus. Fit the wire bridge (factory state) or set PC12 = 1 "
                "for DI-driven requests.",
            )
        else:
            say(
                OK,
                "remote ON/OFF contact reads closed/active (bridge fitted) - "
                "this is inferred from the field value 1; confirm once on the "
                "unit.",
            )
    if c(1779) == 1:
        say(
            WARN,
            "PH03 = 1: time programs are enabled and can block the compressor "
            "or turn the unit off (unit status 'off_by_scheduler').",
        )
    if c(1825) not in (None, 3, 4):
        say(
            ACTION,
            f"HB04 = {c(1825)}: only 3 or 4 are valid for the season input; "
            "anything else raises AL25 (I/O configuration error).",
        )
    pu13 = c(1889)
    if pu13 is not None:
        say(
            INFO,
            f"PU13 = {pu13 / 10:.1f} C (factory 22.0). The compressor does not "
            "start below it, and the handbook does not say what happens with no "
            "room temperature at all. This is the main open question: it can "
            "only be answered with the unit ON (dehumidify request over Modbus "
            "and see whether the compressor starts).",
        )
    say(
        INFO,
        "Fallback if PU13 vetoes: give AI2 a fixed ~25 C reading (10 kOhm NTC "
        "resistor, HA02 = 45) - an idea, not from the manual.",
    )
    say(
        INFO,
        "Season (summer/winter) comes from DI4 (HB04, open = summer) when no "
        "display owns it; 'summer_di' in the mode status is therefore expected.",
    )
    return {"params": cfg}


def step_sweep(dev: Dev, spec: str, limit: int) -> dict[str, list[int]]:
    head(f"Sweep of undocumented registers ({spec})")
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


# Areas read for the snapshot / watch: (function type, first, last).
SNAPSHOT_AREAS = [
    (HOLD, 1590, 1900),  # configuration parameters (PF, PG, PH, PU, HA..HD ...)
    (IN, 255, 260),  # packed digital inputs
    (IN, 380, 390),  # packed digital outputs
    (IN, 495, 515),  # analog inputs
    (IN, 630, 645),  # analog outputs (fan, compressor)
    (IN, 768, 775),  # packed alarms
    (IN, 1100, 1140),  # status / request registers
]
WATCH_AREAS = [a for a in SNAPSHOT_AREAS if a[0] == IN and a[1] >= 380] + [
    (HOLD, 1614, 1614),  # PM20 manual fan setpoint: does a written value stay?
    (HOLD, 1644, 1647),  # PF07, PF08, PF09, PF10 fan band limits
    (HOLD, 1852, 1853),  # PF27, PF28 fan band minima
]
SNAPSHOT_CHUNK = 10


def doc_names() -> dict[tuple[int, int], str]:
    """{(function type, address): name} from the reference doc and entity table."""
    names: dict[tuple[int, int], str] = {}
    text = (HERE.parent / "doc/references/MODBUS_REGISTERS.md").read_text(
        encoding="utf-8"
    )
    for _hex, dec, name in re.findall(
        r"`0x([0-9A-Fa-f]{4})`\s*\|\s*(\d+)\s*\|([^|]+)\|", text
    ):
        # The doc does not say which function code, so key by address only and
        # let the caller try both.
        names[(0, int(dec))] = name.strip().replace("`", "")
    for addr, code, desc, _default in PARAMS:
        names[(HOLD, addr)] = f"{code} {desc}"
    for key, props in const.ENTITIES_DICT.items():
        names.setdefault(
            (const.get_entity_type(props), const.get_entity_reg(props)[0]), key
        )
    return names


def read_area(dev: Dev, rt: int, lo: int, hi: int) -> dict[int, int]:
    """Read lo..hi in small chunks; only a failed chunk is retried per register."""
    out: dict[int, int] = {}
    for start in range(lo, hi + 1, SNAPSHOT_CHUNK):
        count = min(SNAPSHOT_CHUNK, hi - start + 1)
        regs, _ = dev.read(rt, start, count)
        if regs is not None:
            out.update({start + i: v for i, v in enumerate(regs)})
            continue
        for addr in range(start, start + count):
            r, _ = dev.read(rt, addr)
            if r is not None:
                out[addr] = r[0]
    return out


def pairs(word: int, fields: dict[str, int]) -> str:
    """Decode the 2-bit fields of a packed I/O word: {name: first bit}."""
    return ", ".join(f"{n}={(word >> b) & 3}" for n, b in fields.items())


def step_snapshot(dev: Dev) -> dict[str, dict[int, int]]:
    head("10. Read-only snapshot of configuration and status areas")
    names = doc_names()
    snap: dict[str, dict[int, int]] = {"input": {}, "holding": {}}
    for rt, lo, hi in SNAPSHOT_AREAS:
        label = "holding" if rt == HOLD else "input"
        got = read_area(dev, rt, lo, hi)
        snap[label].update(got)
        print(f"\n  {label} {lo}-{hi}: {len(got)} of {hi - lo + 1} addresses answer")
        for addr, v in sorted(got.items()):
            name = names.get((rt, addr)) or names.get((0, addr)) or "(undocumented)"
            sentinel = "  <sentinel: no probe>" if const.is_probe_sentinel(v) else ""
            print(f"    {addr:5} (0x{addr:04X}) = {v:5} (0x{v:04X})  {name}{sentinel}")
    inp, hold = snap["input"], snap["holding"]
    print("\n  Packed I/O words (2-bit fields; meaning of the values is per manual):")
    if 384 in inp:
        say(
            INFO,
            "Packed_DO1 (384): "
            + pairs(inp[384], {"compressor": 4, "recirc_damper": 8, "water_valve": 12}),
        )
    if 385 in inp:
        say(
            INFO,
            "Packed_DO2 (385): "
            + pairs(
                inp[385],
                {
                    "on_off": 4,
                    "summer_winter": 6,
                    "serious_alarm": 8,
                    "light_alarm": 10,
                },
            ),
        )
    if 257 in inp:
        say(
            INFO,
            "Packed_logicDI1 (257): "
            + pairs(
                inp[257],
                {
                    "remote_on_off": 0,
                    "summer_winter": 2,
                    "dehum_req": 4,
                    "integ_req": 6,
                },
            ),
        )
    for addr, what in (
        (1838, "HD01 DO1 allocation (10 = recirculation damper NO, 9 = NC)"),
        (1698, "PS01 recirculation-damper pre-start time (s)"),
        (1614, "PM20 manual fan setpoint"),
    ):
        if addr in hold:
            say(INFO, f"reg {addr} {what} = {hold[addr]}")
    # actRPMsupplyFan (1117) needs an input allocated to the fan tachometer:
    # code 45 (supply fan) or 46 (return fan) on a DI, HB 6 input table; the
    # same codes on an analog input mean room / outdoor temperature.
    alloc = {
        **{1803 + n: f"HA{n:02}" for n in range(1, 19)},
        **{1821 + n: f"HB{n:02}" for n in range(1, 8)},
    }
    tacho = [f"{alloc[a]}={hold[a]}" for a in alloc if hold.get(a) in (45, 46)]
    if any(a in hold for a in alloc):
        say(
            INFO,
            "fan tachometer input: "
            + (", ".join(tacho) if tacho else "none allocated (1117 cannot count)")
            + f"; actRPMsupplyFan 1117 = {inp.get(1117)}",
        )
    print(
        "  Unmapped analog-output allocations (HC03 AO3, HC04 AO4 = supply fan) and\n"
        "  the other HD0x relay allocations sit in the holding dump above; compare\n"
        "  against the handbook parameter table (doc/references/*Handbuch*.txt)."
    )
    return snap


def step_watch(dev: Dev, seconds: float, interval: float) -> None:
    head(f"11. Watching status/output registers for {seconds:.0f}s (read-only)")
    names = doc_names()
    prev: dict[tuple[int, int], int] = {}
    t0 = time.monotonic()
    print("  Start or stop dehumidify / change the fan now; changes print below.")
    try:
        while time.monotonic() - t0 < seconds:
            cur: dict[tuple[int, int], int] = {}
            for rt, lo, hi in WATCH_AREAS:
                cur.update({(rt, a): v for a, v in read_area(dev, rt, lo, hi).items()})
            for k, v in sorted(cur.items()):
                if k in prev and prev[k] != v:
                    name = names.get(k) or names.get((0, k[1])) or ""
                    extra = ""
                    if k[1] in (384, 385, 257):
                        extra = f"  [{bin(prev[k])} -> {bin(v)}]"
                    print(
                        f"  t+{time.monotonic() - t0:6.1f}s  {k[1]:5}: "
                        f"{prev[k]:5} -> {v:5}  {name}{extra}"
                    )
            if not prev:
                print(f"  baseline read: {len(cur)} registers")
            prev = cur
            time.sleep(interval)
    except KeyboardInterrupt:
        print("  watch stopped")


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
    ap.add_argument(
        "--display",
        action="store_true",
        help="a wired CNU2 display is fitted (integration option 'has_display'); "
        "default is headless, where the integration writes PH01=0 and HA00=0",
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
    ap.add_argument(
        "--no-snapshot",
        action="store_true",
        help="skip the configuration/status snapshot (step 10)",
    )
    ap.add_argument(
        "--watch",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="after the checks, poll status/output registers and print changes",
    )
    ap.add_argument(
        "--interval", type=float, default=2.0, help="seconds between --watch polls"
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
        result["inputs"] = step_inputs(dev)
        step_alarms(extras)
        step_settings(rows, extras, result["identity"], args.model, args.display)
        result.update(registers=rows, extras=extras)
        result["headless"] = step_headless(dev, rows, extras)
        if not args.no_snapshot:
            result["snapshot"] = step_snapshot(dev)
        if args.sweep:
            result["sweep"] = step_sweep(dev, args.sweep, args.sweep_max)
        if args.watch:
            step_watch(dev, args.watch, args.interval)
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
