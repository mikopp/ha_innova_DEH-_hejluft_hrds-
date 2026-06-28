"""Constants and the central register table for the Innova HRDS+ integration.

All Modbus registers are declared once in ``ENTITIES_DICT``. ``init()`` (called
at import time) classifies every entry into the typed dicts consumed by the
platform files. See ``references/MODBUS_REGISTERS.md`` for the source data.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorEntityDescription,
)
from homeassistant.components.climate import (
    ClimateEntityDescription,
    ClimateEntityFeature,
)
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    Platform,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from pymodbus.client import ModbusTcpClient

thismodule = sys.modules[__name__]
_LOGGER = logging.getLogger(__name__)

DOMAIN = "innova_hrds"
DEFAULT_NAME = "HRDS+"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PORT = 502
DEFAULT_HOSTID = 1
CONF_HOSTID = "hostid"
CONF_MODEL = "model"
DEFAULT_MODEL = "30"
MODELS = ["30", "50"]
MODEL_SPECS: Dict[str, Dict[str, float]] = {
    "30": {"max": 300.0},
    "50": {"max": 500.0},
}
CONF_AIRFLOW_MAX = "airflow_max_m3h"
CONF_FAN_MIN_OUTPUT = "fan_min_output_pct"
DEFAULT_FAN_MIN_OUTPUT = 50.0
ATTR_MANUFACTURER = "Innova / hej.luft"

# ------------------------------------------------------------------
# Register-type / data-type constants
# ------------------------------------------------------------------
# The HRDS+ exposes *only* analog registers: read-only "input registers"
# (function code 4) and read-write "holding registers" (function code 3).
# There are no coils or discrete inputs (0/1 flags are analog registers).
C_REG_TYPE_INPUT_REGISTERS = 4  # read-only  (FC 04)
C_REG_TYPE_HOLDING_REGISTERS = 3  # read-write (FC 03 / 06 / 16)

C_DT_INT16 = ModbusTcpClient.DATATYPE.INT16
C_DT_UINT16 = ModbusTcpClient.DATATYPE.UINT16

# Maximum registers per Modbus request and the largest gap we will bridge when
# grouping scattered addresses into a single block read.
C_MAX_BLOCK = 120
C_MAX_GAP = 8

# ------------------------------------------------------------------
# Enumerations used by status registers (mapped to translation slugs)
# ------------------------------------------------------------------
UNIT_STATUS = {
    0: "off_by_display",
    1: "off_by_di",
    2: "off_by_bms",
    3: "off_by_scheduler",
    4: "off_by_rtc",
    5: "on",
}
MODE_STATUS = {
    0: "summer_manual",
    1: "winter_manual",
    2: "summer_auto",
    3: "winter_auto",
    4: "summer_di",
    5: "winter_di",
}
FAN_STATUS = {
    0: "disabled",
    1: "off",
    2: "wait_on",
    3: "on",
    4: "wait_off",
    5: "alarm",
}
COMPRESSOR_STATUS = {
    0: "disabled",
    1: "alarm",
    2: "manual",
    3: "wait_on",
    4: "on",
    5: "wait_off",
    6: "off",
}
OPERATING_MODE = {0: "summer", 1: "winter", 2: "auto"}
RECIRCULATION_DAMPER = {0: "off", 1: "on", 2: "disabled"}

# HA00 (reg 1803) — source for room temperature and humidity probes.
# 0 = no display sensors; external probes on AI2/AI3 are used if wired.
# 5/6 = CNU2 display (the wired remote with built-in T/H sensors).
# 1-4 = older CNU / Epj display variants (rare).
# Default from factory: 6 (CNU2 with both T and H sensors).
PROBE_SOURCE = {
    0: "none_or_external",
    1: "cnu_temp",
    2: "cnu_temp_humidity",
    3: "epj_temp",
    4: "epj_temp_humidity",
    5: "cnu2_temp",
    6: "cnu2_temp_humidity",
    "default": 6,
}

# ------------------------------------------------------------------
# Entity-key constants (== Home Assistant object_id / translation_key)
# ------------------------------------------------------------------
# Read-only sensors
C_ROOM_TEMPERATURE = "room_temperature"
C_OUTDOOR_TEMPERATURE = "outdoor_temperature"
C_WATER_TEMPERATURE = "water_temperature"
C_SUPPLY_TEMPERATURE = "supply_temperature"
C_ROOM_HUMIDITY = "room_humidity"
C_AIR_QUALITY = "air_quality"
C_ACTUAL_SETPOINT = "actual_setpoint"
C_SUPPLY_FAN_OUTPUT = "supply_fan_output"
C_COMPRESSOR_OUTPUT = "compressor_output"
C_SUPPLY_FAN_RPM = "supply_fan_rpm"
# Read-only enum sensors
C_UNIT_STATUS = "unit_status"
C_MODE_STATUS = "mode_status"
C_SUPPLY_FAN_STATUS = "supply_fan_status"
C_COMPRESSOR_STATUS = "compressor_status"
C_OPERATING_MODE = "operating_mode"
# Read-only binary sensors
C_DEHUM_REQUEST = "dehumidify_request"
C_RECIRCULATION_ACTIVE = "recirculation_active"
C_ALARM_ACTIVE = "alarm_active"
# Read-only binary sensors derived from holding registers (RW=0)
C_HAS_RECIRCULATION = "has_recirculation"
C_ACTIVE_COOLING_AVAILABLE = "active_cooling_available"
# Read-only enum sensor from digital output register
C_RECIRCULATION_DAMPER = "recirculation_damper"
# Read-write numbers
C_HUMIDITY_SETPOINT = "humidity_setpoint"
C_SUMMER_SETPOINT = "summer_setpoint"
C_WINTER_SETPOINT = "winter_setpoint"
C_FAN_MIN_DEHUM = "fan_min_speed_dehumidify"
C_FAN_MAX_DEHUM = "fan_max_speed_dehumidify"
C_FAN_MIN_COOLING = "fan_min_speed_cooling"
C_FAN_MAX_COOLING = "fan_max_speed_cooling"
C_FAN_MANUAL = "fan_manual_speed"
# Read-write switches
C_UNIT_ON_OFF = "unit_on_off"
C_DEHUMIDIFY = "dehumidify"
C_ACTIVE_COOLING = "active_cooling"
C_ENABLE_ONOFF_BMS = "enable_onoff_bms"
C_ENABLE_DEHUM_BMS = "enable_dehumidify_bms"
C_ENABLE_COOLING_BMS = "enable_cooling_bms"
# Read-write selects
C_PROBE_SOURCE = "probe_source"
# Derived binary sensors (bit-extracted from packed alarm registers)
C_TEMP_PROBE_OK = "temp_probe_ok"
C_HUMIDITY_PROBE_OK = "humidity_probe_ok"
# Individual alarm sensors (bit-extracted; ON = alarm active)
C_ALARM_COMPRESSOR_LP = "alarm_compressor_lowpressure"
C_ALARM_COMPRESSOR_HP = "alarm_compressor_highpressure"
C_ALARM_ANTIFREEZE = "alarm_water_antifreeze"
C_ALARM_FILTER = "alarm_dirty_filter"
# Computed (non-register-backed) airflow sensors
C_MAX_TOTAL_AIRFLOW = "max_total_airflow"
C_SUPPLY_FAN_MAX_AIRFLOW = "supply_fan_max_airflow"
C_SUPPLY_FAN_AIRFLOW = "supply_fan_airflow"

# Keys the (composite) climate entity reads/writes.
CLIMATE_CURRENT_TEMP = C_ROOM_TEMPERATURE
CLIMATE_CURRENT_HUMIDITY = C_ROOM_HUMIDITY
CLIMATE_TARGET_HUMIDITY = C_HUMIDITY_SETPOINT
CLIMATE_TARGET_TEMP = C_SUMMER_SETPOINT

# ------------------------------------------------------------------
# ENTITIES_DICT — the single source of truth.
#
# Fields:
#   RT*    register type (input or holding)
#   REG*   Modbus address (decimal, direct PDU address — no -1 offset)
#   DT     data type (INT16 / UINT16); defaults to UINT16
#   NAME   fallback display name (translations override this)
#   FAKTOR multiplier applied on read (raw * FAKTOR); reciprocal on write
#   UNIT   unit string (drives device/state class via _unit_mapping)
#   MIN/MAX/STEP   bounds for numbers
#   VALUES enum map {raw: slug} for selects/enum sensors
#   SWITCH {"off": 0, "on": 1} marks a 0/1 register as a switch/binary sensor
#   PF     platform override (e.g. Platform.NUMBER to keep a temp off climate)
#   (* = required)
# ------------------------------------------------------------------
ENTITIES_DICT: Dict[str, Dict[str, Any]] = {
    # --- Read-only sensors (input registers, FC 04) ---
    C_ROOM_TEMPERATURE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 499,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "°C",
        "NAME": "Room temperature",
    },
    C_OUTDOOR_TEMPERATURE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 500,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "°C",
        "NAME": "Outdoor temperature",
    },
    C_WATER_TEMPERATURE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 501,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "°C",
        "NAME": "Water temperature",
    },
    C_SUPPLY_TEMPERATURE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 503,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "°C",
        "NAME": "Supply air temperature",
    },
    C_ROOM_HUMIDITY: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 505,
        "DT": C_DT_INT16,
        "UNIT": "%",
        "NAME": "Room humidity",
    },
    C_AIR_QUALITY: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 506,
        "DT": C_DT_INT16,
        "UNIT": "ppm",
        "NAME": "Air quality",
    },
    C_ACTUAL_SETPOINT: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1111,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "°C",
        "NAME": "Active setpoint",
    },
    C_SUPPLY_FAN_OUTPUT: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 639,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "NAME": "Supply fan output",
    },
    C_COMPRESSOR_OUTPUT: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 641,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "NAME": "Compressor output",
    },
    C_SUPPLY_FAN_RPM: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1117,
        "DT": C_DT_UINT16,
        "UNIT": "rpm",
        "NAME": "Supply fan speed",
    },
    # --- Read-only enum sensors (input registers, FC 04) ---
    C_UNIT_STATUS: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1104,
        "DT": C_DT_UINT16,
        "VALUES": UNIT_STATUS,
        "NAME": "Unit status",
    },
    C_MODE_STATUS: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1110,
        "DT": C_DT_UINT16,
        "VALUES": MODE_STATUS,
        "NAME": "Mode status",
    },
    C_SUPPLY_FAN_STATUS: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1119,
        "DT": C_DT_UINT16,
        "VALUES": FAN_STATUS,
        "NAME": "Supply fan status",
    },
    C_COMPRESSOR_STATUS: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1122,
        "DT": C_DT_UINT16,
        "VALUES": COMPRESSOR_STATUS,
        "NAME": "Compressor status",
    },
    C_OPERATING_MODE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1583,
        "DT": C_DT_UINT16,
        "VALUES": OPERATING_MODE,
        "NAME": "Operating mode (season)",
    },
    # --- Read-only binary sensors (0/1 input registers) ---
    C_DEHUM_REQUEST: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1121,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Dehumidify requested",
    },
    C_RECIRCULATION_ACTIVE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1112,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Recirculation active",
    },
    C_RECIRCULATION_DAMPER: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1134,
        "DT": C_DT_UINT16,
        "VALUES": RECIRCULATION_DAMPER,
        "NAME": "Recirculation damper",
    },
    C_ALARM_ACTIVE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1103,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Alarm active",
    },
    # --- Read-write numbers (holding registers, FC 03) ---
    C_HUMIDITY_SETPOINT: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1586,
        "DT": C_DT_UINT16,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Humidity setpoint",
    },
    C_SUMMER_SETPOINT: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1584,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "°C",
        "MIN": 15.0,
        "MAX": 35.0,
        "STEP": 0.5,
        "PF": Platform.NUMBER,
        "NAME": "Summer setpoint",
    },
    C_WINTER_SETPOINT: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1585,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "°C",
        "MIN": 15.0,
        "MAX": 35.0,
        "STEP": 0.5,
        "PF": Platform.NUMBER,
        "NAME": "Winter setpoint",
    },
    C_FAN_MIN_DEHUM: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1853,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Fan min speed (dehumidify)",
    },
    C_FAN_MAX_DEHUM: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1647,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Fan max speed (dehumidify)",
    },
    C_FAN_MIN_COOLING: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1852,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Fan min speed (cooling)",
    },
    C_FAN_MAX_COOLING: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1646,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Fan max speed (cooling)",
    },
    C_FAN_MANUAL: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1614,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Manual fan speed",
    },
    # --- Read-write switches (0/1 holding registers) ---
    C_UNIT_ON_OFF: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1105,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Unit on/off (BMS)",
    },
    C_DEHUMIDIFY: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1140,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Dehumidify (BMS)",
    },
    C_ACTIVE_COOLING: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1139,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Active cooling (BMS)",
    },
    C_ENABLE_ONOFF_BMS: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1778,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Enable on/off via Modbus",
    },
    C_ENABLE_DEHUM_BMS: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1870,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Enable dehumidify via Modbus",
    },
    C_ENABLE_COOLING_BMS: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1869,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Enable cooling via Modbus",
    },
    # --- Hardware-variant read-only sensors (holding registers, RW=0) ---
    # PG01_MachineType (1797): 0=dehumidifier only, 1=dehumidifier+VMC (has recirc fan).
    # PG02_EnableIntegration (1798): 0=cooling disabled, 1=cooling enabled on this unit.
    # RW=0 forces classification as binary sensor even though RT is HOLDING.
    C_HAS_RECIRCULATION: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1797,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "RW": 0,
        "NAME": "Has recirculation fan",
    },
    C_ACTIVE_COOLING_AVAILABLE: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1798,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "RW": 0,
        "NAME": "Active cooling available",
    },
    # --- T/H probe source (HA00, holding register R/W) ---
    # Controls which sensor supplies room temperature and humidity readings.
    # Set to 0 ("none_or_external") when no display is connected; external
    # NTC/0-10V probes on AI2/AI3 are then used if wired.
    C_PROBE_SOURCE: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1803,
        "DT": C_DT_UINT16,
        "VALUES": PROBE_SOURCE,
        "NAME": "T/H probe source (HA00)",
    },
    # --- Probe-OK binary sensors derived from packed alarm registers ---
    # PackedAlarm_2 (reg 769): bit 11 = AL28 (room temperature probe fault).
    # PackedAlarm_3 (reg 770): bit  1 = AL34 (room humidity probe fault).
    # BITMASK: which bit to check; BITMASK_INVERT: alarm SET → probe NOT OK.
    C_TEMP_PROBE_OK: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 769,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 11,
        "BITMASK_INVERT": True,
        "NAME": "Room temperature probe OK",
    },
    C_HUMIDITY_PROBE_OK: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 770,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 1,
        "BITMASK_INVERT": True,
        "NAME": "Room humidity probe OK",
    },
    # --- Individual alarm sensors (PackedAlarm bit extraction; ON = alarm active) ---
    # PackedAlarm_1 (reg 768): bit N = AL(N+1).
    # AL11 (bit 10): compressor low-pressure / frost-thermostat — stops compressor.
    #   This is the effective minimum-airflow protection: insufficient flow causes
    #   evaporator icing which triggers low refrigerant pressure.
    C_ALARM_COMPRESSOR_LP: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 768,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 10,
        "NAME": "Alarm: compressor low-pressure / frost",
    },
    # AL12 (bit 11): compressor high-pressure switch — stops compressor.
    C_ALARM_COMPRESSOR_HP: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 768,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 11,
        "NAME": "Alarm: compressor high-pressure",
    },
    # AL16 (bit 15): water-circuit antifreeze — stops fan.
    C_ALARM_ANTIFREEZE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 768,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 15,
        "NAME": "Alarm: water antifreeze",
    },
    # PackedAlarm_2 (reg 769): bit N = AL(N+17).
    # AL22 (bit 5): dirty filters — display-only, manual reset.
    C_ALARM_FILTER: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 769,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 5,
        "NAME": "Alarm: dirty filter",
    },
}

# Registers written (in order) when the integration is set up, to make sure
# Modbus control is actually permitted by the unit.
BMS_ENABLE_KEYS = (C_ENABLE_ONOFF_BMS, C_ENABLE_DEHUM_BMS, C_ENABLE_COOLING_BMS)

# Computed sensors: not backed by Modbus registers; values are written by the
# hub after each decode cycle using model calibration parameters.
COMPUTED_SENSORS: Dict[str, Dict[str, str]] = {
    C_MAX_TOTAL_AIRFLOW: {"NAME": "Max total airflow", "UNIT": "m³/h"},
    C_SUPPLY_FAN_MAX_AIRFLOW: {"NAME": "Supply fan max airflow", "UNIT": "m³/h"},
    C_SUPPLY_FAN_AIRFLOW: {"NAME": "Supply fan airflow", "UNIT": "m³/h"},
}


# ------------------------------------------------------------------
# Entity description dataclasses
# ------------------------------------------------------------------
@dataclass
class MySensorEntityDescription(SensorEntityDescription):
    """Describes a read-only Modbus sensor."""


@dataclass
class MyBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a read-only 0/1 Modbus register."""


@dataclass
class MyBinaryEntityDescription(BinarySensorEntityDescription):
    """Describes a read-write 0/1 Modbus register (rendered as a switch)."""


@dataclass
class MySelectEntityDescription(SelectEntityDescription):
    """Describes a writable enum register."""

    default_select_option: str | None = None


@dataclass
class MyNumberEntityDescription(NumberEntityDescription):
    """Describes a writable numeric register."""

    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    unit_of_measurement: str | None = None
    mode: str = "box"


@dataclass
class MyClimateEntityDescription(ClimateEntityDescription):
    """Describes the composite climate entity."""

    temperature_unit: str = UnitOfTemperature.CELSIUS
    supported_features: ClimateEntityFeature = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_HUMIDITY
        | ClimateEntityFeature.FAN_MODE
    )


# Typed dicts populated by init().
SENSOR_TYPES: dict[str, MySensorEntityDescription] = {}
BINARYSENSOR_TYPES: dict[str, MyBinarySensorEntityDescription] = {}
BINARY_TYPES: dict[str, MyBinaryEntityDescription] = {}
SELECT_TYPES: dict[str, MySelectEntityDescription] = {}
NUMBER_TYPES: dict[str, MyNumberEntityDescription] = {}
CLIMATE_TYPES: dict[str, MyClimateEntityDescription] = {}


# ------------------------------------------------------------------
# Property accessors / classifiers
# ------------------------------------------------------------------
TEMP_UNITS = {"°C", "K"}


def get_entity_props(entity: str) -> dict:
    return ENTITIES_DICT[entity]


def get_entity_type(props: Dict[str, Any]) -> int | None:
    return props.get("RT")


def get_entity_name(props: Dict[str, Any], default: str | None = None) -> str | None:
    return props.get("NAME", default)


def get_entity_unit(props: Dict[str, Any], default: str | None = None) -> str | None:
    return props.get("UNIT", default)


def get_entity_platform(props: Dict[str, Any], default: Any = None) -> Any:
    return props.get("PF", default)


def get_entity_factor(props: Dict[str, Any]) -> float:
    return props.get("FAKTOR", 1.0)


def get_entity_min(props: Dict[str, Any]) -> float:
    return props.get("MIN", 0)


def get_entity_max(props: Dict[str, Any]) -> float:
    return props.get("MAX", 100.0)


def get_entity_step(props: Dict[str, Any]) -> float:
    return props.get("STEP", 1.0)


def get_entity_switch(props: Dict[str, Any]) -> dict[str, int] | None:
    return props.get("SWITCH")


def get_entity_select(props: Dict[str, Any]) -> dict[Any, Any] | None:
    return props.get("VALUES")


def get_entity_reg(
    props: Dict[str, Any],
) -> tuple[int | None, ModbusTcpClient.DATATYPE | None]:
    return props.get("REG"), props.get("DT", C_DT_UINT16)


def is_entity_readonly(props: Dict[str, Any]) -> bool:
    return get_entity_type(props) == C_REG_TYPE_INPUT_REGISTERS or props.get("RW") == 0


def is_entity_readwrite(props: Dict[str, Any]) -> bool:
    return not is_entity_readonly(props)


def is_entity_switch(props: Dict[str, Any]) -> bool:
    return get_entity_switch(props) is not None


def is_entity_select(props: Dict[str, Any]) -> bool:
    return get_entity_select(props) not in (None, {})


def get_entity_bitmask(props: Dict[str, Any]) -> int | None:
    return props.get("BITMASK")


def is_entity_climate(props: Dict[str, Any]) -> bool:
    return get_entity_unit(props) in TEMP_UNITS and get_entity_platform(props) in (
        None,
        Platform.CLIMATE,
    )


def get_entity_select_values_and_default(
    props: dict[str, Any],
) -> tuple[list[str], str | None]:
    values = get_entity_select(props)
    default_index = values.get("default")
    select_map = {k: v for k, v in values.items() if k != "default"}
    return list(select_map.values()), select_map.get(default_index)


def _unit_mapping(
    unit: Optional[str],
) -> tuple[Optional[str], Optional[SensorDeviceClass], Optional[SensorStateClass]]:
    """Map our UNIT strings to HA native unit + device/state class."""
    if unit is None:
        return None, None, None
    u = unit.strip()
    if u == "°C":
        return (
            UnitOfTemperature.CELSIUS,
            SensorDeviceClass.TEMPERATURE,
            SensorStateClass.MEASUREMENT,
        )
    if u == "%":
        return "%", SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT
    if u == "ppm":
        return (
            "ppm",
            SensorDeviceClass.AQI,
            SensorStateClass.MEASUREMENT,
        )
    if u == "rpm":
        return "rpm", None, SensorStateClass.MEASUREMENT
    if u == UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR:
        return (
            UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
            SensorDeviceClass.VOLUME_FLOW_RATE,
            SensorStateClass.MEASUREMENT,
        )
    return u, None, SensorStateClass.MEASUREMENT


def _classify(props: Dict[str, Any]) -> type | None:
    """Return the entity-description class an entry maps to."""
    if get_entity_reg(props)[0] is None:
        return None
    if is_entity_readonly(props):
        if is_entity_switch(props):
            return MyBinarySensorEntityDescription
        return MySensorEntityDescription  # plain or enum sensor
    # read-write
    if is_entity_switch(props):
        return MyBinaryEntityDescription
    if is_entity_select(props):
        return MySelectEntityDescription
    if is_entity_climate(props):
        return MyClimateEntityDescription
    return MyNumberEntityDescription


_initialized = False


def init() -> None:
    """Classify every ENTITIES_DICT entry into the typed dicts (idempotent)."""
    global _initialized
    if _initialized:
        return

    # The climate entity is composite (not backed by one register) and is
    # always created manually.
    CLIMATE_TYPES["hrds_climate"] = MyClimateEntityDescription(
        key="hrds_climate",
        name="Climate",
        translation_key="hrds_climate",
    )

    for key, props in ENTITIES_DICT.items():
        name = get_entity_name(props, key)
        cls = _classify(props)

        if cls is MySensorEntityDescription:
            if is_entity_select(props):
                SENSOR_TYPES[key] = MySensorEntityDescription(
                    key=key,
                    name=name,
                    translation_key=key,
                    device_class=SensorDeviceClass.ENUM,
                    options=[
                        v for k, v in get_entity_select(props).items() if k != "default"
                    ],
                )
            else:
                unit, device_class, state_class = _unit_mapping(get_entity_unit(props))
                SENSOR_TYPES[key] = MySensorEntityDescription(
                    key=key,
                    name=name,
                    translation_key=key,
                    native_unit_of_measurement=unit,
                    device_class=device_class,
                    state_class=state_class,
                )
        elif cls is MyBinarySensorEntityDescription:
            BINARYSENSOR_TYPES[key] = MyBinarySensorEntityDescription(
                key=key,
                name=name,
                translation_key=key,
            )
        elif cls is MyBinaryEntityDescription:
            BINARY_TYPES[key] = MyBinaryEntityDescription(
                key=key,
                name=name,
                translation_key=key,
            )
        elif cls is MySelectEntityDescription:
            values, default = get_entity_select_values_and_default(props)
            SELECT_TYPES[key] = MySelectEntityDescription(
                key=key,
                name=name,
                translation_key=key,
                options=values,
                default_select_option=default,
            )
        elif cls is MyNumberEntityDescription:
            NUMBER_TYPES[key] = MyNumberEntityDescription(
                key=key,
                name=name,
                translation_key=key,
                min_value=get_entity_min(props),
                max_value=get_entity_max(props),
                step=get_entity_step(props),
                unit_of_measurement=get_entity_unit(props),
            )
        else:
            _LOGGER.warning("Unclassified entity %s: %s", key, props)

    for key, props in COMPUTED_SENSORS.items():
        unit, device_class, state_class = _unit_mapping(props.get("UNIT"))
        SENSOR_TYPES[key] = MySensorEntityDescription(
            key=key,
            name=props["NAME"],
            translation_key=key,
            native_unit_of_measurement=unit,
            device_class=device_class,
            state_class=state_class,
        )

    _initialized = True


init()
