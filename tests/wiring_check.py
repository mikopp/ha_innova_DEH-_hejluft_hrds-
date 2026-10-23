"""Wiring / consistency checks that do not need Home Assistant installed.

Home Assistant is a heavy dependency and this repo has no test harness, so this
script stubs just enough of the HA API to import ``const.py``, then asserts the
things that have actually broken before:

* every ``ENTITIES_DICT`` entry is classified into a typed dict - an
  unclassified entry silently produces no entity at all
* every ``Platform`` in ``PLATFORMS`` has a matching module - ``select`` was
  declared for a while with no ``select.py``, so that entity was never created
* every entity key has an ``en`` and ``de`` translation
* every ``REG`` appears in ``doc/references/MODBUS_REGISTERS.md`` with a
  self-consistent hex/decimal pair
* no input-register block spans a holding-register address, because reading a
  holding register with FC 04 can fail the entire block

Run with:  python3 tests/wiring_check.py
"""

from __future__ import annotations

import enum
import importlib.util
import json
import pathlib
import re
import struct
import sys
import types
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components/innova_hrds"


# --------------------------------------------------------------------------
# Minimal Home Assistant stubs
# --------------------------------------------------------------------------
class EntityCategory:
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


@dataclass
class EntityDescription:
    """Stand-in for HA's description base.

    Real HA uses ``metaclass=FrozenOrThawed``, which is what allows the
    integration's plain ``@dataclass`` subclasses. A plain dataclass here has
    the same effect for our purposes.
    """

    key: str = ""
    name: str | None = None
    translation_key: str | None = None
    device_class: object = None
    entity_category: object = None
    entity_registry_enabled_default: bool = True


@dataclass
class SensorEntityDescription(EntityDescription):
    native_unit_of_measurement: str | None = None
    state_class: object = None
    options: list | None = None


@dataclass
class BinarySensorEntityDescription(EntityDescription):
    pass


@dataclass
class SelectEntityDescription(EntityDescription):
    options: list | None = None


@dataclass
class NumberEntityDescription(EntityDescription):
    native_min_value: float | None = None
    native_max_value: float | None = None
    native_step: float | None = None
    native_unit_of_measurement: str | None = None
    mode: object = None


@dataclass
class ClimateEntityDescription(EntityDescription):
    pass


@dataclass
class ButtonEntityDescription(EntityDescription):
    pass


class ClimateEntityFeature(enum.IntFlag):
    TARGET_TEMPERATURE = 1
    TARGET_HUMIDITY = 2
    FAN_MODE = 4
    TURN_ON = 8
    TURN_OFF = 16


class NumberMode(enum.StrEnum):
    BOX = "box"
    SLIDER = "slider"
    AUTO = "auto"


class SensorDeviceClass(enum.StrEnum):
    HUMIDITY = "humidity"
    TEMPERATURE = "temperature"
    AQI = "aqi"
    ENUM = "enum"
    VOLUME_FLOW_RATE = "volume_flow_rate"
    TIMESTAMP = "timestamp"


class SensorStateClass(enum.StrEnum):
    MEASUREMENT = "measurement"


class Platform(enum.StrEnum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    SWITCH = "switch"
    NUMBER = "number"
    SELECT = "select"
    CLIMATE = "climate"


class UnitOfTemperature(enum.StrEnum):
    CELSIUS = "°C"


class UnitOfVolumeFlowRate(enum.StrEnum):
    CUBIC_METERS_PER_HOUR = "m³/h"


class _DataType(enum.Enum):
    INT16 = "i"
    UINT16 = "H"


def _stub(name: str, is_package: bool = False, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    if is_package:
        module.__path__ = []  # type: ignore[attr-defined]
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def install_stubs() -> None:
    """Register fake ``homeassistant`` / ``pymodbus`` modules in sys.modules."""
    _stub("homeassistant", is_package=True)
    _stub("homeassistant.components", is_package=True)
    _stub(
        "homeassistant.components.binary_sensor",
        BinarySensorDeviceClass=types.SimpleNamespace(
            PROBLEM="problem", RUNNING="running"
        ),
        BinarySensorEntityDescription=BinarySensorEntityDescription,
    )
    _stub(
        "homeassistant.components.button",
        ButtonEntityDescription=ButtonEntityDescription,
    )
    _stub(
        "homeassistant.components.climate",
        ClimateEntityDescription=ClimateEntityDescription,
        ClimateEntityFeature=ClimateEntityFeature,
    )
    _stub(
        "homeassistant.components.number",
        NumberEntityDescription=NumberEntityDescription,
        NumberMode=NumberMode,
    )
    _stub(
        "homeassistant.components.select",
        SelectEntityDescription=SelectEntityDescription,
    )
    _stub(
        "homeassistant.components.sensor",
        SensorEntityDescription=SensorEntityDescription,
        SensorDeviceClass=SensorDeviceClass,
        SensorStateClass=SensorStateClass,
    )
    _stub(
        "homeassistant.const",
        Platform=Platform,
        EntityCategory=EntityCategory,
        UnitOfTemperature=UnitOfTemperature,
        UnitOfVolumeFlowRate=UnitOfVolumeFlowRate,
    )
    _stub("pymodbus", is_package=True)
    _stub(
        "pymodbus.client",
        ModbusTcpClient=type("ModbusTcpClient", (), {"DATATYPE": _DataType}),
    )


def load_const() -> types.ModuleType:
    """Load const.py directly.

    Importing it as a package member would execute ``innova_hrds/__init__.py``,
    which needs far more of Home Assistant than is stubbed here.
    """
    # An empty package stand-in lets const.py's relative imports (e.g.
    # installer_params) resolve without running the real __init__.py.
    package = types.ModuleType("innova_hrds")
    package.__path__ = [str(COMP)]
    sys.modules.setdefault("innova_hrds", package)
    spec = importlib.util.spec_from_file_location(
        "innova_hrds.const", COMP / "const.py"
    )
    module = importlib.util.module_from_spec(spec)
    # const.py does sys.modules[__name__] at import time.
    sys.modules["innova_hrds.const"] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
FAILURES: list[str] = []

TYPED_DICT_PLATFORM = {
    "SENSOR_TYPES": "sensor",
    "BINARYSENSOR_TYPES": "binary_sensor",
    "BINARY_TYPES": "switch",
    "SELECT_TYPES": "select",
    "NUMBER_TYPES": "number",
    "BUTTON_TYPES": "button",
}


def check(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        FAILURES.append(message)


REFERENCE_PLATFORMS = {
    **TYPED_DICT_PLATFORM,
    "CLIMATE_TYPES": "climate",
    "OPERATION_TYPES": "switch",
}
# `| `platform.key` | ...` : the first cell of a row in an entity table.
ENTITY_ROW = re.compile(r"\|\s*`([a-z_]+\.[a-z0-9_]+)`\s*\|")


def reference_sections(text: str) -> dict[str, list[str]]:
    """Map each entity in the reference to the device group(s) it is listed under."""
    found: dict[str, list[str]] = {}
    device = group = None
    for line in text.splitlines():
        heading = re.match(r"(#{2,3}) (.+)", line)
        if heading:
            title = heading.group(2)
            if len(heading.group(1)) == 2:
                device = next(
                    (
                        d
                        for prefix, d in (
                            ("Main device", "main"),
                            ("Setup device", "setup"),
                            ("Installer device", "installer"),
                        )
                        if title.startswith(prefix)
                    ),
                    None,
                )
                group = device
            elif device == "main":
                group = {
                    "Operational": "main",
                    "Configuration": "config",
                    "Diagnostic": "diag",
                }.get(title)
            continue
        row = ENTITY_ROW.match(line)
        if row:
            found.setdefault(row.group(1), []).append(group or "outside a device")
    return found


def check_entity_reference(const) -> None:
    """doc/entity-reference.md lists every entity once, on its own device."""
    expected: dict[str, str] = {}
    for dict_name, platform in REFERENCE_PLATFORMS.items():
        for key in getattr(const, dict_name):
            if key in const.INSTALLER_KEYS:
                continue  # parameters are generated; MODBUS_REGISTERS.md section 16
            if key in const.INSTALLER_DEVICE_EXTRA_KEYS:
                group = "installer"
            elif key in const.SETUP_KEYS:
                group = "setup"
            elif key in const.CONFIG_KEYS:
                group = "config"
            elif key in const.DIAGNOSTIC_KEYS:
                group = "diag"
            else:
                group = "main"
            expected[f"{platform}.{key}"] = group
    path = ROOT / "doc/entity-reference.md"
    check(path.exists(), "doc/entity-reference.md exists")
    if not path.exists():
        return
    found = reference_sections(path.read_text(encoding="utf-8"))
    missing = sorted(set(expected) - set(found))
    check(not missing, f"every entity is in the entity reference (missing: {missing})")
    unknown = sorted(set(found) - set(expected))
    check(not unknown, f"the entity reference lists no unknown entity ({unknown})")
    twice = sorted(e for e, where in found.items() if len(where) > 1)
    check(not twice, f"each entity is listed once (listed twice: {twice})")
    misplaced = sorted(
        f"{e} is under '{found[e][0]}', not '{want}'"
        for e, want in expected.items()
        if e in found and found[e][0] != want
    )
    check(not misplaced, f"each entity sits on its own device and group ({misplaced})")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    restated = sorted({m for m in ENTITY_ROW.findall(readme)})
    check(
        not restated,
        f"the README links the entity reference, not copies it ({restated})",
    )


def png_size(path: pathlib.Path) -> tuple[int, int]:
    """Return (width, height) read from a PNG's IHDR chunk."""
    data = path.read_bytes()
    check(data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is a PNG")
    return struct.unpack(">II", data[16:24])


def build_blocks(addresses, foreign, max_gap, max_block):
    """Mirror of ``_build_blocks`` in __init__.py, for the block-span check."""
    addresses = sorted(set(addresses))
    blocks = []
    start = prev = addresses[0]
    for addr in addresses[1:]:
        fits = addr - prev <= max_gap and addr - start + 1 <= max_block
        spans_foreign = any(a in foreign for a in range(prev + 1, addr))
        if fits and not spans_foreign:
            prev = addr
        else:
            blocks.append((start, prev - start + 1))
            start = prev = addr
    blocks.append((start, prev - start + 1))
    return blocks


def main() -> int:
    install_stubs()
    const = load_const()

    print("== typed dicts populated ==")
    for name in [*TYPED_DICT_PLATFORM, "CLIMATE_TYPES"]:
        entries = getattr(const, name)
        check(len(entries) > 0, f"{name} has {len(entries)} entries")
    check("probe_source" in const.SELECT_TYPES, "probe_source classified as a select")
    check(
        const.SELECT_TYPES["probe_source"].default_select_option
        == "cnu2_temp_humidity",
        "probe_source default resolves via the DEFAULT field",
    )
    check("default" not in const.PROBE_SOURCE, "PROBE_SOURCE map has no sentinel key")

    print("== setup issue texts ==")
    check(
        len(const.SETUP_ISSUE_TEXTS) == 17
        and all(all(t) for t in const.SETUP_ISSUE_TEXTS.values()),
        "every setup issue slug has an English and a German text",
    )
    print("== switch hints ==")
    check(
        set(const.SWITCH_HINTS) <= set(const.BINARY_TYPES),
        "every switch hint belongs to a register-backed switch",
    )

    print("== headless / identity / probe sentinel ==")
    # PG01 is the fan arrangement, not "has recirculation"; reading it as the
    # latter made an `R` unit report "no recirculation".
    check(
        "has_recirculation" not in const.ENTITIES_DICT,
        "no entity claims PG01 means 'has recirculation'",
    )
    check("machine_type" in const.SENSOR_TYPES, "PG01 is a read-only enum sensor")
    for key, (decoded, raw) in const.HEADLESS_SETTINGS.items():
        props = const.ENTITIES_DICT[key]
        if const.is_entity_select(props):
            actual = const.get_entity_select(props).get(raw)
        else:
            actual = "on" if raw else "off"
        check(
            actual == decoded,
            f"HEADLESS_SETTINGS[{key}] raw {raw} decodes to '{decoded}'",
        )
        check(
            not const.is_entity_readonly(props),
            f"headless setting {key} is writable",
        )
    check(
        {"enable_onoff_display", "probe_source"} <= set(const.HEADLESS_SETTINGS),
        "headless mode asserts PH01 and HA00",
    )
    check(
        const.is_probe_sentinel(0x8004) and const.is_probe_sentinel(0x7FFA),
        "observed unwired-probe words (0x8004, 0x7FFA) are sentinels",
    )
    check(
        not const.is_probe_sentinel(0xFFF6) and not const.is_probe_sentinel(215),
        "a real reading (-1.0 degC, 21.5 degC) is not a sentinel",
    )
    for lang in ("en", "de"):
        tr = json.loads((COMP / f"translations/{lang}.json").read_text())
        for section in (tr["config"], tr["options"]):
            check(
                {"cannot_connect", "wrong_device"} <= set(section["error"]),
                f"{lang}.json has the identity-check form errors",
            )
        check(
            "has_display" in tr["config"]["step"]["user"]["data"],
            f"{lang}.json labels the has_display option",
        )

    print("== composite entities resolve availability correctly ==")
    # Regression guard: HubBackedEntity.available gates register-backed entities
    # on their key being in hub.data, which is populated only from
    # ENTITIES_DICT. climate/fan are composite and have no such key, so gating
    # them the same way made them permanently unavailable.
    common = (COMP / "entity_common.py").read_text()
    check(
        "if key not in ENTITIES_DICT:" in common,
        "available() special-cases keys that are not register-backed",
    )
    for dict_name in ("CLIMATE_TYPES",):
        for key in getattr(const, dict_name):
            check(
                key not in const.ENTITIES_DICT,
                f"{dict_name}['{key}'] is composite, so it must take that branch",
            )

    print("== installer menu stays out of the regular poll ==")
    hub_source = (COMP / "__init__.py").read_text()
    check(
        "frozenset(ENTITIES_DICT) - INSTALLER_KEYS" in hub_source,
        "the poll reads every key except the installer menu",
    )
    check(
        const.INSTALLER_LOGIC_KEYS <= const.INSTALLER_KEYS,
        "INSTALLER_LOGIC_KEYS are installer keys",
    )
    check(
        not const.DEFAULT_INSTALLER_DEVICE,
        "the installer device is off by default",
    )

    print("== every entity is classified ==")
    classified: set[str] = set()
    for name in TYPED_DICT_PLATFORM:
        classified |= set(getattr(const, name))
    orphans = sorted(set(const.ENTITIES_DICT) - classified)
    check(not orphans, f"no unclassified ENTITIES_DICT keys (orphans: {orphans})")

    print("== device classes ==")
    check(
        const.SENSOR_TYPES["room_humidity"].device_class == SensorDeviceClass.HUMIDITY,
        "room_humidity keeps device_class humidity",
    )
    for key in ("supply_fan_output", "compressor_output"):
        check(
            const.SENSOR_TYPES[key].device_class is None,
            f"{key} is not mislabelled as humidity",
        )
    check(
        const.SENSOR_TYPES["air_quality"].device_class is None,
        "air_quality does not pair ppm with AQI (AQI permits only a None unit)",
    )

    print("== climate features ==")
    features = const.CLIMATE_TYPES["hrds_climate"].supported_features
    check(
        bool(features & ClimateEntityFeature.TURN_ON)
        and bool(features & ClimateEntityFeature.TURN_OFF),
        "climate declares TURN_ON/TURN_OFF (the HA compat shim is gone in 2026.9)",
    )

    print("== number descriptions use native_* ==")
    number = const.NUMBER_TYPES["humidity_setpoint"]
    check(
        number.native_min_value is not None and number.native_max_value is not None,
        "native bounds are set",
    )
    check(number.mode == NumberMode.BOX, "mode is a NumberMode, not a bare string")

    print("== every declared platform has a module ==")
    source = (COMP / "__init__.py").read_text()
    listed = re.search(r"PLATFORMS = \[(.*?)\]", source, re.S).group(1)
    for platform in re.findall(r"Platform\.(\w+)", listed):
        check(
            (COMP / f"{platform.lower()}.py").exists(),
            f"{platform.lower()}.py exists for Platform.{platform}",
        )

    print("== translations cover every entity ==")
    for lang in ("en", "de"):
        entity = json.loads((COMP / f"translations/{lang}.json").read_text())["entity"]
        missing = [
            f"{platform}.{key}"
            for name, platform in TYPED_DICT_PLATFORM.items()
            for key in getattr(const, name)
            if key not in entity.get(platform, {})
        ]
        check(not missing, f"{lang}.json covers all entities (missing: {missing})")

    print("== register addresses match the reference doc ==")
    doc = (ROOT / "doc/references/MODBUS_REGISTERS.md").read_text()
    documented: dict[int, str] = {}
    for hex_addr, dec_addr, name in re.findall(
        r"`0x([0-9A-Fa-f]{4})`\s*\|\s*(\d+)\s*\|([^|]+)\|", doc
    ):
        if int(hex_addr, 16) != int(dec_addr):
            FAILURES.append(f"doc self-inconsistent: 0x{hex_addr} vs {dec_addr}")
        documented[int(dec_addr)] = name.strip()
    unlisted = {
        key: props["REG"]
        for key, props in const.ENTITIES_DICT.items()
        if props["REG"] not in documented
    }
    check(not unlisted, f"every REG is documented (unlisted: {unlisted})")

    print("== input blocks must not span holding addresses ==")
    inputs = [
        p["REG"]
        for p in const.ENTITIES_DICT.values()
        if p["RT"] == const.C_REG_TYPE_INPUT_REGISTERS
    ]
    holdings = {
        p["REG"]
        for p in const.ENTITIES_DICT.values()
        if p["RT"] == const.C_REG_TYPE_HOLDING_REGISTERS
    }
    blocks = build_blocks(inputs, holdings, const.C_MAX_GAP, const.C_MAX_BLOCK)
    bad = [b for b in blocks if any(a in holdings for a in range(b[0], b[0] + b[1]))]
    check(not bad, f"no input block spans a holding register (offenders: {bad})")
    print(f"   input blocks: {blocks}")

    print("== setup / config / operation grouping and gate ==")
    known = (
        set(const.ENTITIES_DICT)
        | set(const.COMPUTED_SENSORS)
        | set(const.COMPUTED_BINARY_SENSORS)
        | set(const.OPERATION_TYPES)
    )
    for label in ("SETUP_KEYS", "CONFIG_KEYS", "DIAGNOSTIC_KEYS"):
        stray = sorted(set(getattr(const, label)) - known)
        check(not stray, f"{label} only names existing entities (stray: {stray})")
    check(
        not (const.SETUP_KEYS & (const.CONFIG_KEYS | const.DIAGNOSTIC_KEYS)),
        "a key is either setup or config/diagnostic, never both",
    )
    check(
        const.C_OPERATION_ALLOWED in const.OPERATION_TYPES
        and const.C_OPERATION_ALLOWED in const.SETUP_KEYS,
        "the operation gate switch exists and lives on the setup device",
    )
    check(
        all(k in const.ENTITIES_DICT for k in const.OPERATIONAL_KEYS),
        "every gated key is a register-backed entity",
    )
    check(
        not (set(const.OPERATIONAL_KEYS) & const.SETUP_KEYS),
        "gated request entities stay on the main device",
    )
    for lang in ("en", "de"):
        tr = json.loads((COMP / f"translations/{lang}.json").read_text("utf-8"))
        ent = tr["entity"]
        check(
            "operation_allowed" in ent.get("switch", {}),
            f"{lang}.json names the operation_allowed switch",
        )
        states = ent.get("sensor", {}).get("setup_check", {}).get("state", {})
        check(
            set(states) == {"ok", "attention"},
            f"{lang}.json translates both setup_check states",
        )

    print("== entity reference matches the code ==")
    check_entity_reference(const)

    print("== installer device, season and heating guard ==")
    inst = const.INSTALLER_KEYS
    check(
        not (inst & (const.SETUP_KEYS | const.CONFIG_KEYS | const.DIAGNOSTIC_KEYS)),
        "installer parameters live only on the installer device",
    )
    regs = [const.ENTITIES_DICT[k]["REG"] for k in inst]
    others = {
        p["REG"]
        for k, p in const.ENTITIES_DICT.items()
        if k not in inst and p["RT"] == const.C_REG_TYPE_HOLDING_REGISTERS
    }
    check(len(regs) == len(set(regs)), "no installer register is listed twice")
    dup = sorted(set(regs) & others)
    check(not dup, f"installer rows do not repeat an existing entity ({dup})")
    # Passwords, PH15 restore-defaults and PH18 clear-history must never be
    # reachable; above 1900 readability is unverified (one bad address forces
    # the slow per-register fallback for its whole block).
    forbidden = {1601, 1626, 1787, 1790, 1796, 1802, 1875}
    check(not (set(regs) & forbidden), "no password / reset parameter is exposed")
    check(max(regs) <= 1900, "no installer register above 1900 is polled")
    season = const.ENTITIES_DICT[const.C_SEASON]
    check(
        season["REG"] == 1825 and set(season["VALUES"]) == {3, 4},
        "season select writes only HB04 = 3/4 (anything else raises AL25)",
    )
    check(
        const.is_entity_readonly(const.ENTITIES_DICT[const.C_WATER_VALVE_PUMP]),
        "water valve / pump output is read-only (the unit drives it)",
    )
    hub_src = (COMP / "__init__.py").read_text(encoding="utf-8")
    check(
        "self._check_request_allowed(entity_key, raw)" in hub_src,
        "every write passes the winter-heating / brine guard",
    )

    print("== brine temperature guard ==")
    guard = const.C_BRINE_GUARD
    check(
        guard in const.BINARYSENSOR_TYPES and guard not in const.ENTITIES_DICT,
        "the brine guard is a computed binary sensor (no register)",
    )
    check(
        const.BINARYSENSOR_TYPES[guard].device_class == "problem",
        "the brine guard is a problem indicator (on = blocking)",
    )
    # Its availability must not hinge on hub.data/poll health alone.
    check(
        "C_BRINE_GUARD" in (COMP / "binary_sensor.py").read_text(encoding="utf-8"),
        "binary_sensor.py special-cases the brine guard",
    )
    check(
        "self.update_brine_guard()" in hub_src and "brine_guard_ok is True" in hub_src,
        "requests re-judge the guard, and winter brine DEU needs it passing",
    )
    for lang in ("en", "de"):
        tr = json.loads((COMP / f"translations/{lang}.json").read_text("utf-8"))
        for section, step in ((tr["config"], "user"), (tr["options"], "init")):
            check(
                {"brine_temperature_entity", "brine_min_temperature"}
                <= set(section["step"][step]["data"]),
                f"{lang}.json labels the brine guard options ({step})",
            )

    print("== manifest and brand images ==")
    manifest = json.loads((COMP / "manifest.json").read_text())
    pinned = [r for r in manifest["requirements"] if "==" in r]
    check(not pinned, f"no exact == requirement pin (hassfest rejects: {pinned})")
    brand = COMP / "brand"
    for name, side in (("icon", 256), ("icon@2x", 512)):
        for prefix in ("", "dark_"):
            width, height = png_size(brand / f"{prefix}{name}.png")
            check(
                (width, height) == (side, side),
                f"{prefix}{name}.png is {side}x{side} (got {width}x{height})",
            )
    for name, short in (("logo", 256), ("logo@2x", 512)):
        for prefix in ("", "dark_"):
            width, height = png_size(brand / f"{prefix}{name}.png")
            check(
                min(width, height) == short,
                f"{prefix}{name}.png shortest side is {short} (got {width}x{height})",
            )

    print()
    print("RESULT:", "ALL PASS" if not FAILURES else f"{len(FAILURES)} FAILURE(S)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
