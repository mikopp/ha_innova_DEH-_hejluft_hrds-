"""Wiring / consistency checks that do not need Home Assistant installed.

Home Assistant is a heavy dependency and this repo has no test harness, so this
script stubs just enough of the HA API to import ``const.py``, then asserts the
things that have actually broken before:

* every ``ENTITIES_DICT`` entry is classified into a typed dict - an
  unclassified entry silently produces no entity at all
* every ``Platform`` in ``PLATFORMS`` has a matching module - ``select`` was
  declared for a while with no ``select.py``, so that entity was never created
* every entity key has an ``en`` and ``de`` translation
* every ``REG`` appears in ``references/MODBUS_REGISTERS.md`` with a
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
import sys
import types
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components/innova_hrds"


# --------------------------------------------------------------------------
# Minimal Home Assistant stubs
# --------------------------------------------------------------------------
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
class FanEntityDescription(EntityDescription):
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


class SensorStateClass(enum.StrEnum):
    MEASUREMENT = "measurement"


class Platform(enum.StrEnum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    SWITCH = "switch"
    NUMBER = "number"
    SELECT = "select"
    CLIMATE = "climate"
    FAN = "fan"


class UnitOfTemperature(enum.StrEnum):
    CELSIUS = "°C"


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
        BinarySensorEntityDescription=BinarySensorEntityDescription,
    )
    _stub(
        "homeassistant.components.climate",
        ClimateEntityDescription=ClimateEntityDescription,
        ClimateEntityFeature=ClimateEntityFeature,
    )
    _stub(
        "homeassistant.components.fan",
        FanEntityDescription=FanEntityDescription,
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
        UnitOfTemperature=UnitOfTemperature,
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
    spec = importlib.util.spec_from_file_location("hrds_const", COMP / "const.py")
    module = importlib.util.module_from_spec(spec)
    # const.py does sys.modules[__name__] at import time.
    sys.modules["hrds_const"] = module
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
}


def check(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        FAILURES.append(message)


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
    for name in [*TYPED_DICT_PLATFORM, "CLIMATE_TYPES", "FAN_TYPES"]:
        entries = getattr(const, name)
        check(len(entries) > 0, f"{name} has {len(entries)} entries")
    check("probe_source" in const.SELECT_TYPES, "probe_source classified as a select")
    check(
        const.SELECT_TYPES["probe_source"].default_select_option
        == "cnu2_temp_humidity",
        "probe_source default resolves via the DEFAULT field",
    )
    check("default" not in const.PROBE_SOURCE, "PROBE_SOURCE map has no sentinel key")

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
    for dict_name in ("CLIMATE_TYPES", "FAN_TYPES"):
        for key in getattr(const, dict_name):
            check(
                key not in const.ENTITIES_DICT,
                f"{dict_name}['{key}'] is composite, so it must take that branch",
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
    doc = (ROOT / "references/MODBUS_REGISTERS.md").read_text()
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

    print()
    print("RESULT:", "ALL PASS" if not FAILURES else f"{len(FAILURES)} FAILURE(S)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
