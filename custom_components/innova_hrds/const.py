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
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.climate import (
    ClimateEntityDescription,
    ClimateEntityFeature,
)
from homeassistant.components.fan import FanEntityDescription
from homeassistant.components.number import NumberEntityDescription, NumberMode
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    Platform,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from pymodbus.client import ModbusTcpClient

from .installer_params import INSTALLER_PARAMS, installer_key

thismodule = sys.modules[__name__]
_LOGGER = logging.getLogger(__name__)

DOMAIN = "innova_hrds"
DEFAULT_NAME = "HRDS+"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PORT = 502
DEFAULT_HOSTID = 1
CONF_HOSTID = "hostid"
CONF_MODEL = "model"
CONF_HAS_DISPLAY = "has_display"
# Opt-in: allow an integration (INT) request while the unit is in winter
# season, which makes it heat with water from the heating circuit.
CONF_ALLOW_WINTER_HEATING = "allow_winter_heating"
DEFAULT_ALLOW_WINTER_HEATING = False
# What the unit's water register is plumbed to. A brine (ground-source)
# circuit cannot heat and must not dehumidify in winter (coil freezing).
CONF_WATER_CIRCUIT = "water_circuit"
WATER_CIRCUIT_HEATING_COOLING = "heating_cooling"
WATER_CIRCUIT_BRINE = "brine"
WATER_CIRCUITS = [WATER_CIRCUIT_HEATING_COOLING, WATER_CIRCUIT_BRINE]
DEFAULT_WATER_CIRCUIT = WATER_CIRCUIT_HEATING_COOLING
# Optional guard: a Home Assistant temperature sensor on the brine supply (e.g.
# from the heat pump). When set, no DEU/INT request starts unless it reports at
# least the minimum and was reported within BRINE_GUARD_MAX_AGE. On a brine
# circuit it is also what permits dehumidifying in winter; without it, winter
# dehumidifying on brine is always refused.
CONF_BRINE_TEMPERATURE_ENTITY = "brine_temperature_entity"
CONF_BRINE_MIN_TEMPERATURE = "brine_min_temperature"
DEFAULT_BRINE_MIN_TEMPERATURE = 10.0
BRINE_GUARD_MAX_AGE_HOURS = 24
# The unit is driven over Modbus; a wired CNU2 display is the exception.
DEFAULT_HAS_DISPLAY = False
# Opt-in: the installer device (installer_params.py). Its registers are never
# part of the regular poll, only read on its refresh button.
CONF_INSTALLER_DEVICE = "installer_device"
DEFAULT_INSTALLER_DEVICE = False
DEFAULT_MODEL = "30"
MODELS = ["30", "50"]
MODEL_SPECS: Dict[str, Dict[str, float]] = {
    "30": {"max": 300.0},
    "50": {"max": 500.0},
}
# Max airflow is a *model* property with no register (see CLAUDE.md, Device
# variants), so it stays a config option. The fan *minimum*, by contrast, is
# per-mode and register-backed (PF27/PF28/PF07) - the device owns it, and it is
# exposed as writable numbers rather than shadowed by a config option.
CONF_AIRFLOW_MAX = "airflow_max_m3h"
ATTR_MANUFACTURER = "Innova / hej.luft"

# FC 43/14 (Read Device Identification) as reported by a real HRDS+ 30:
# vendor "EVCO", product code "EPB9ORSINDEU", revision "V01.00.09.02". The
# controller is an EVCO board, so the vendor is a hard requirement. The product
# code is matched on its family prefix only; it was seen on a single unit.
EXPECTED_VENDOR = "EVCO"
EXPECTED_PRODUCT_PREFIX = "EPB9"

# An unwired or failed analog input reads as a value in this raw (unsigned)
# window instead of a temperature: 0x8004 was observed on every missing probe
# and 0x7FFA next to them. Decoded as INT16 these are about -3276 degC, which
# is never a real reading, so they mean "no value".
PROBE_SENTINEL_LOW = 0x7FF0
PROBE_SENTINEL_HIGH = 0x800F

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
# grouping scattered addresses into a single block read. Modbus allows 125, but
# a real HRDS+ behind an RS-485 gateway did not answer a 120-register read at
# all, while 10-register reads covered the whole map (tests/devices dump). The
# hub halves this further if a block goes unanswered but a single register
# does (``_shrink_blocks``).
C_MAX_BLOCK = 10
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
# PG01 - fan arrangement, NOT whether a recirculation fan exists. Handbook:
# "0: dehumidifier with supply fan only, 1: with supply and exhaust fan". An `R`
# unit reads 0 (its single fan is the recirculation fan).
MACHINE_TYPE = {0: "supply_fan_only", 1: "supply_and_exhaust_fan"}
# HB03 - remote ON/OFF digital input (the OFF/OFF terminals): 2 = normally open
# (factory), 1 = normally closed, 0 = not used.
REMOTE_ONOFF_INPUT = {0: "unused", 1: "normally_closed", 2: "normally_open"}
# HB04 - summer/winter digital input; only 3 and 4 are valid (others raise AL25).
# Without a display the Modbus manual uses it as THE season switch: 4 makes
# the open DI4 contact read as summer, 3 (normally closed) as winter. If a
# contact is actually wired to DI4, closing it inverts the meaning.
SEASON = {4: "summer", 3: "winter"}
# PC11 - who owns the summer/winter change.
SEASON_OWNER = {0: "display", 1: "digital_input"}
# PH05
TEMPERATURE_UNIT = {0: "celsius", 1: "fahrenheit"}
RECIRCULATION_DAMPER = {0: "off", 1: "on", 2: "disabled"}
# Relay outputs reported as 0 = off, 1 = on, 2 = not configured.
OUTPUT_STATUS = {0: "off", 1: "on", 2: "disabled"}
# PU02 - dehumidification during the winter season.
WINTER_DEHUM = {0: "disabled", 1: "with_water", 2: "without_water"}

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
}

# HA02 (reg 1805) / HA03 (reg 1806) — what is wired to analog inputs AI2 / AI3
# (handbook 6.7). Only the room-probe codes are documented; any other code of
# the 0-60 range decodes to None and the setup check flags it.
ROOM_TEMP_PROBE_INPUT = {0: "unused", 45: "room_temperature_ntc"}
ROOM_HUMIDITY_PROBE_INPUT = {
    0: "unused",
    53: "room_humidity_4_20ma",
    54: "room_humidity_0_10v",
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
C_EXHAUST_TEMPERATURE = "exhaust_temperature"
C_EVAPORATOR_TEMPERATURE = "evaporator_temperature"
C_FAN_MANUAL_REQUEST = "fan_manual_request"
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
# Read-only sensors derived from holding registers (RW=0)
C_MACHINE_TYPE = "machine_type"
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
C_FAN_MIN_VMC = "fan_min_speed_vmc"
C_FAN_MAX_COOLING = "fan_max_speed_cooling"
C_FAN_MANUAL = "fan_manual_speed"
C_DEHUM_DIFFERENTIAL = "dehumidify_differential"
C_MIN_ROOM_TEMP_DEHUM = "min_room_temp_dehumidify"
C_MIN_ROOM_TEMP_DIFF = "min_room_temp_diff_dehumidify"
C_FAN_MIN_RUNTIME = "fan_min_runtime"
C_FAN_POST_RUN_TIME = "fan_post_run_time"
C_HUMIDITY_SETPOINT_MIN = "humidity_setpoint_min"
C_HUMIDITY_SETPOINT_MAX = "humidity_setpoint_max"
# Read-write switches
C_UNIT_ON_OFF = "unit_on_off"
C_DEHUMIDIFY = "dehumidify"
C_ACTIVE_COOLING = "active_cooling"
C_TIME_PROGRAMS = "enable_time_programs"
C_AI2_ALLOCATION = "ai2_allocation"
C_AI3_ALLOCATION = "ai3_allocation"
C_REMOTE_ONOFF_INPUT = "remote_onoff_input"
C_SEASON = "season"
C_ONOFF_BY_DI_REQUEST = "enable_onoff_by_di_request"
C_WATER_VALVE_PUMP = "water_valve_pump"
C_WATER_CONDENSER_VALVE = "water_condenser_valve"
C_ALARM_HIGH_WATER_TEMP = "alarm_high_water_temperature"
C_ALARM_LOW_WATER_TEMP = "alarm_low_water_temperature"
# Computed: water-circuit health (pump/valve, water temperature limits).
C_WATER_CHECK = "water_check"
C_BRINE_GUARD = "brine_temperature_guard"
C_SEASON_OWNER = "season_owner"
C_TEMPERATURE_UNIT = "temperature_unit"
C_FAN_OUTPUT_ALLOCATION = "fan_output_allocation"
C_DAMPER_RELAY_ALLOCATION = "damper_relay_allocation"
C_DAMPER_PRESTART = "damper_prestart_time"
C_REMOTE_CONTACT_CLOSED = "remote_contact_closed"
# Computed: summary of what still needs the user's attention.
C_SETUP_CHECK = "setup_check"
# Composite switch (no register): gate for operational requests.
C_OPERATION_ALLOWED = "operation_allowed"
C_ENABLE_ONOFF_DISPLAY = "enable_onoff_display"
C_ENABLE_ONOFF_BMS = "enable_onoff_bms"
C_ENABLE_DEHUM_BMS = "enable_dehumidify_bms"
C_ENABLE_INT_BMS = "enable_integration_bms"
C_FORCE_DEHUM_IN_COOLING = "force_dehumidify_in_cooling"
C_ENABLE_FREE_COOLING = "enable_free_cooling"
# Read-write selects
C_PROBE_SOURCE = "probe_source"
C_WINTER_DEHUM = "winter_dehumidify"
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
# PH29/PH30 - the unit clamps PU01 to this band, so the climate entity should
# advertise it rather than a hardcoded guess.
CLIMATE_MIN_HUMIDITY = C_HUMIDITY_SETPOINT_MIN
CLIMATE_MAX_HUMIDITY = C_HUMIDITY_SETPOINT_MAX

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
#   DC     explicit sensor device class (overrides the UNIT-derived default)
#   DEFAULT  default raw value for a select
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
        "DC": SensorDeviceClass.HUMIDITY,
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
        "MIN": 5.0,
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
    # PF07 - the third per-mode minimum, for VMC (ventilation-only) operation.
    # Completes the set alongside PF28 (dehumidify) and PF27 (integration).
    C_FAN_MIN_VMC: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1644,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Fan min speed (VMC)",
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
        # The INT request: dehumidify + cool in summer, HEAT in winter.
        "NAME": "Integration request (BMS)",
    },
    # PH01: let a wired display switch the unit on/off. With no display the unit
    # stays OFF-by-display forever while this is 1, and an OFF from any source
    # beats a Modbus ON.
    C_ENABLE_ONOFF_DISPLAY: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1777,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Enable on/off via display (PH01)",
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
        "NAME": "Enable dehumidify (DEU) via Modbus (PH28)",
    },
    C_ENABLE_INT_BMS: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1869,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Enable integration (INT) via Modbus (PH27)",
    },
    # --- Hardware-variant read-only sensors (holding registers, RW=0) ---
    # PG01_MachineType (1797): fan arrangement (supply only / supply + exhaust).
    # It does NOT say whether a recirculation fan is fitted: use the damper
    # output (1134, `disabled` = no damper wired) for that.
    # PG02_EnableIntegration (1798): 0=cooling disabled, 1=cooling enabled on this unit.
    # RW=0 forces read-only classification even though RT is HOLDING.
    C_MACHINE_TYPE: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1797,
        "DT": C_DT_UINT16,
        "VALUES": MACHINE_TYPE,
        "RW": 0,
        "NAME": "Machine type (PG01)",
    },
    C_ACTIVE_COOLING_AVAILABLE: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1798,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "RW": 0,
        "NAME": "Unit has integration function (PG02)",
    },
    # --- Installer configuration, exposed so the user can see how the unit is set
    # up and change what matters without a service tool. Read-only entries are
    # RW=0 holding registers. Addresses of the HA/HB/HC/HD groups follow the
    # handbook's parameter order, which matches every address the Modbus PDF
    # gives (PH05=1781, HA00=1803, HB04=1825, HD01=1838).
    C_TIME_PROGRAMS: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1779,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Enable time programs (PH03)",
    },
    C_REMOTE_ONOFF_INPUT: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1824,
        "DT": C_DT_UINT16,
        "VALUES": REMOTE_ONOFF_INPUT,
        "RW": 0,
        "NAME": "Remote on/off input (HB03)",
    },
    # The season switch over Modbus (HB04, see SEASON). Read-back is 1583.
    C_SEASON: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1825,
        "DT": C_DT_UINT16,
        "VALUES": SEASON,
        "NAME": "Season",
    },
    # PC12: a DI dehumidify/integration request starts the unit even with the
    # remote OFF contact open.
    C_ONOFF_BY_DI_REQUEST: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1894,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Unit on by DI request (PC12)",
    },
    # Relay K5: external water valve (V3V) and, switched with it, the pump
    # output (PM). The unit drives these itself; read-only on purpose.
    C_WATER_VALVE_PUMP: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1126,
        "DT": C_DT_UINT16,
        "VALUES": OUTPUT_STATUS,
        "NAME": "Water valve / pump output",
    },
    # Relay K4: internal water condenser valve (closed = all heat to water).
    C_WATER_CONDENSER_VALVE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1124,
        "DT": C_DT_UINT16,
        "VALUES": OUTPUT_STATUS,
        "NAME": "Water condenser valve",
    },
    C_SEASON_OWNER: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1878,
        "DT": C_DT_UINT16,
        "VALUES": SEASON_OWNER,
        "RW": 0,
        "NAME": "Season change owner (PC11)",
    },
    C_TEMPERATURE_UNIT: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1781,
        "DT": C_DT_UINT16,
        "VALUES": TEMPERATURE_UNIT,
        "RW": 0,
        "NAME": "Temperature unit (PH05)",
    },
    # Raw allocation codes: HC04 1 = 0-10 V supply fan; HD01 10 = recirculation
    # damper NO, 9 = NC. Shown raw so unfamiliar codes are not hidden.
    C_FAN_OUTPUT_ALLOCATION: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1832,
        "DT": C_DT_UINT16,
        "RW": 0,
        "NAME": "Supply fan output allocation (HC04)",
    },
    C_DAMPER_RELAY_ALLOCATION: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1838,
        "DT": C_DT_UINT16,
        "RW": 0,
        "NAME": "Recirculation damper relay allocation (HD01)",
    },
    C_DAMPER_PRESTART: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1698,
        "DT": C_DT_UINT16,
        "UNIT": "s",
        "RW": 0,
        "NAME": "Damper pre-start time (PS01)",
    },
    # Packed_logicDI1 bits 0-1 = remote ON/OFF contact. The field read 1 on a
    # unit with the factory wire bridge fitted, so 1 is taken to mean closed.
    # The 0/2 meanings are not documented: unverified.
    C_REMOTE_CONTACT_CLOSED: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 257,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 0,
        "NAME": "Remote on/off contact closed",
    },
    # --- T/H probes: source (HA00) and the external probe inputs (HA02/HA03) ---
    # HA00 picks where room temperature and humidity come from. Without a
    # display it must be 0 ("none_or_external"); the unit then only has a room
    # reading if a probe is wired to AI2 (temperature, terminal M2) or AI3
    # (humidity, M3) and HA02/HA03 say so. A probe code with nothing wired
    # raises AL28/AL34, so a sensor-less unit needs "unused" on both. The names
    # share a "T/H probe" prefix so the three sit together on the setup device.
    C_PROBE_SOURCE: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1803,
        "DT": C_DT_UINT16,
        "VALUES": PROBE_SOURCE,
        "DEFAULT": 6,
        "NAME": "T/H probe source (HA00)",
    },
    C_AI2_ALLOCATION: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1805,
        "DT": C_DT_UINT16,
        "VALUES": ROOM_TEMP_PROBE_INPUT,
        "NAME": "T/H probe temperature input (AI2, HA02)",
    },
    C_AI3_ALLOCATION: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1806,
        "DT": C_DT_UINT16,
        "VALUES": ROOM_HUMIDITY_PROBE_INPUT,
        "NAME": "T/H probe humidity input (AI3, HA03)",
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
    # AL03 (bit 2): water above PC07 in summer - blocks cooling/dehumidify.
    C_ALARM_HIGH_WATER_TEMP: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 768,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 2,
        "NAME": "Alarm: high water temperature",
    },
    # AL04 (bit 3): water below PC08 in winter - blocks heating.
    C_ALARM_LOW_WATER_TEMP: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 768,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "BITMASK": 3,
        "NAME": "Alarm: low water temperature",
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
    # --- Additional sensors (input registers, FC 04) ---
    C_EXHAUST_TEMPERATURE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 502,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "\u00b0C",
        "NAME": "Exhaust air temperature",
    },
    C_EVAPORATOR_TEMPERATURE: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 511,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "\u00b0C",
        "NAME": "Evaporator temperature",
    },
    # Mirrors the *display's* manual fan request, not ours. Diagnostic only:
    # the faithful read-back of our own write is holding register 1614.
    C_FAN_MANUAL_REQUEST: {
        "RT": C_REG_TYPE_INPUT_REGISTERS,
        "REG": 1114,
        "DT": C_DT_UINT16,
        "FAKTOR": 0.01,
        "UNIT": "%",
        "NAME": "Manual fan request (display)",
    },
    # --- Additional numbers (holding registers, FC 03) ---
    C_DEHUM_DIFFERENTIAL: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1694,
        "DT": C_DT_UINT16,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Dehumidify differential (PU07)",
    },
    # PU13: the unit refuses to dehumidify below this room temperature. On a
    # unit with no room probe this interlock can block a Modbus request.
    C_MIN_ROOM_TEMP_DEHUM: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1889,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "\u00b0C",
        "MIN": 0.0,
        "MAX": 30.0,
        "STEP": 0.1,
        "PF": Platform.NUMBER,
        "NAME": "Min room temp for dehumidify (PU13)",
    },
    C_MIN_ROOM_TEMP_DIFF: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1890,
        "DT": C_DT_INT16,
        "FAKTOR": 0.1,
        "UNIT": "\u00b0C",
        "MIN": 0.1,
        "MAX": 20.0,
        "STEP": 0.1,
        "PF": Platform.NUMBER,
        "NAME": "Min room temp differential (PU14)",
    },
    # PF01/PF03 are the device's own anti-short-cycle timers, so an external
    # controller usually does not need a minimum-runtime timer of its own.
    C_FAN_MIN_RUNTIME: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1638,
        "DT": C_DT_UINT16,
        "UNIT": "s",
        "MIN": 0,
        "MAX": 999,
        "STEP": 1,
        "NAME": "Fan minimum runtime (PF01)",
    },
    C_FAN_POST_RUN_TIME: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1640,
        "DT": C_DT_UINT16,
        "UNIT": "s",
        "MIN": 0,
        "MAX": 999,
        "STEP": 1,
        "NAME": "Fan post-run time (PF03)",
    },
    C_HUMIDITY_SETPOINT_MIN: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1892,
        "DT": C_DT_UINT16,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Humidity setpoint min (PH29)",
    },
    C_HUMIDITY_SETPOINT_MAX: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1893,
        "DT": C_DT_UINT16,
        "UNIT": "%",
        "MIN": 0,
        "MAX": 100,
        "STEP": 1,
        "NAME": "Humidity setpoint max (PH30)",
    },
    # --- Additional switches ---
    C_FORCE_DEHUM_IN_COOLING: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1692,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Force dehumidify when cooling (PU05)",
    },
    # When off, outdoor temperature (reg 500) is decoration, not a control input.
    C_ENABLE_FREE_COOLING: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1799,
        "DT": C_DT_UINT16,
        "SWITCH": {"off": 0, "on": 1},
        "NAME": "Enable free cooling/heating (PG03)",
    },
    # --- Additional selects ---
    C_WINTER_DEHUM: {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": 1689,
        "DT": C_DT_UINT16,
        "VALUES": WINTER_DEHUM,
        "DEFAULT": 0,
        "NAME": "Winter dehumidification (PU02)",
    },
}

# Installer-menu parameters (installer_params.py) on their own child device.
INSTALLER_KEYS: frozenset[str] = frozenset(
    installer_key(row[0]) for row in INSTALLER_PARAMS
)
# Installer values the hub's own checks use (water check); read once at setup
# even without the installer device.
INSTALLER_LOGIC_KEYS: frozenset[str] = frozenset(
    {installer_key("PC07"), installer_key("PU08")}
)
# Button on the installer device: the only regular way its registers are read.
C_INSTALLER_REFRESH = "refresh_installer"
# Timestamp sensor on the installer device: when its registers were last read.
C_INSTALLER_LAST_READ = "installer_last_read"
# Installer-device entities that are not installer parameters.
INSTALLER_DEVICE_EXTRA_KEYS = frozenset({C_INSTALLER_REFRESH, C_INSTALLER_LAST_READ})
for _code, _reg, _kind, _factor, _min, _max, _unit, _en, _de, _on in INSTALLER_PARAMS:
    _props: Dict[str, Any] = {
        "RT": C_REG_TYPE_HOLDING_REGISTERS,
        "REG": _reg,
        # Offsets and temperature limits can be negative.
        "DT": C_DT_INT16 if _min < 0 or _unit == "°C" else C_DT_UINT16,
        "NAME": _en,
        "NAME_DE": _de,
        "ENABLED": _on,
        "INSTALLER": _code,
    }
    if _kind == "s":
        _props["SWITCH"] = {"off": 0, "on": 1}
    else:
        _props.update(
            {
                "FAKTOR": _factor,
                "MIN": _min,
                "MAX": _max,
                "STEP": _factor if _factor < 1 else 1,
                "PF": Platform.NUMBER,
            }
        )
        if _unit:
            _props["UNIT"] = _unit
    if _kind == "r":
        _props["RW"] = 0
    ENTITIES_DICT[installer_key(_code)] = _props

# Guidance shown as the `hint` attribute of a setup switch: when to leave it on
# or turn it off. Home Assistant has no tooltip for entities; the attribute is
# what the more-info dialog shows. {key: (English, German)}
SWITCH_HINTS: Dict[str, tuple[str, str]] = {
    C_ENABLE_FREE_COOLING: (
        "Turn this OFF unless an outdoor temperature probe is wired. It lets the "
        "unit act on the outdoor temperature (bypass relay); with no probe there is "
        "no valid reading, so the unit may behave unpredictably. Also leave it off "
        "if a central ventilation system already handles free cooling. The Setup "
        "check lists it under 'to_fix' while it is on without a probe.",
        "AUS schalten, solange kein Außentemperaturfühler angeschlossen ist. Die "
        "Funktion lässt das Gerät auf die Außentemperatur reagieren (Bypass-Relais); "
        "ohne Fühler gibt es keinen gültigen Messwert, das Gerät kann sich dann "
        "unvorhersehbar verhalten. Ebenfalls aus lassen, wenn eine zentrale "
        "Lüftungsanlage das Free-Cooling übernimmt. Die Einrichtungsprüfung listet "
        "sie unter 'to_fix', solange sie ohne Fühler an ist.",
    ),
    C_ENABLE_ONOFF_DISPLAY: (
        "Leave OFF without a CNU2 display: the unit would otherwise stay off "
        "waiting for it. The integration keeps it off unless the display option is "
        "ticked.",
        "Ohne CNU2-Display AUS lassen: sonst bleibt das Gerät aus und wartet auf "
        "das Display. Die Integration hält es aus, solange die Display-Option nicht "
        "aktiv ist.",
    ),
    C_ENABLE_ONOFF_BMS: (
        "Leave ON. The unit ignores on/off from Home Assistant without it; the "
        "integration sets it again on every poll.",
        "AN lassen. Ohne diese Freigabe ignoriert das Gerät Ein/Aus aus Home "
        "Assistant; die Integration setzt sie bei jeder Abfrage erneut.",
    ),
    C_ENABLE_DEHUM_BMS: (
        "Leave ON. The unit ignores the dehumidify (DEU) request without it; the "
        "integration sets it again on every poll.",
        "AN lassen. Ohne diese Freigabe ignoriert das Gerät die Entfeuchtungs-"
        "anforderung (DEU); die Integration setzt sie bei jeder Abfrage erneut.",
    ),
    C_ENABLE_INT_BMS: (
        "Leave ON. The unit ignores the integration (INT) request without it; the "
        "integration sets it again on every poll.",
        "AN lassen. Ohne diese Freigabe ignoriert das Gerät die Integrations-"
        "anforderung (INT); die Integration setzt sie bei jeder Abfrage erneut.",
    ),
}

# What to do about each setup issue slug (Setup check `issues`), shown as the
# `to_fix` attribute: {slug: (English, German)}.
SETUP_ISSUE_TEXTS: Dict[str, tuple[str, str]] = {
    "modbus_enables_pending": (
        "Modbus enables not set yet (PH02/PH27/PH28): written on the next poll",
        "Modbus-Freigaben noch nicht gesetzt (PH02/PH27/PH28): werden bei der nächsten Abfrage geschrieben",
    ),
    "headless_settings_pending": (
        "Settings for running without a display not set yet (PH01, HA00): written on the next poll",
        "Einstellungen für Betrieb ohne Display noch nicht gesetzt (PH01, HA00): werden bei der nächsten Abfrage geschrieben",
    ),
    "unit_off_by_digital_input": (
        "Unit held off by the remote on/off contact: close it or set HB03",
        "Gerät durch den Fern-Ein/Aus-Kontakt ausgeschaltet: Kontakt schließen oder HB03 anpassen",
    ),
    "unit_waiting_for_first_on": (
        "The unit still shows 'off by display' although no display is used: it "
        "keeps that stored OFF until the first Modbus ON. Turn on 'Allow "
        "operational requests', then switch on 'Unit on/off (Modbus)' once on the "
        "main device",
        "Das Gerät zeigt noch 'Aus durch Display', obwohl kein Display genutzt "
        "wird: es behält dieses gespeicherte AUS bis zum ersten Modbus-EIN. "
        "'Betriebsanforderungen erlauben' einschalten, dann auf dem Hauptgerät "
        "einmal 'Gerät ein/aus (Modbus)' einschalten",
    ),
    "unit_off_by_scheduler": (
        "Unit held off by a time program: turn off 'Time programs enabled' (PH03)",
        "Gerät durch ein Zeitprogramm ausgeschaltet: 'Zeitprogramme' (PH03) ausschalten",
    ),
    "unit_off_by_clock": (
        "Unit held off by the internal clock: turn off 'Time programs enabled' (PH03)",
        "Gerät durch die interne Uhr ausgeschaltet: 'Zeitprogramme' (PH03) ausschalten",
    ),
    "unit_off_by_display": (
        "Unit switched off by the display: switch it on at the display",
        "Gerät am Display ausgeschaltet: am Display einschalten",
    ),
    "room_temperature_probe_missing": (
        "Room temperature probe expected but not wired: set 'T/H probe temperature input' (HA02) to Unused, or wire the probe",
        "Raumtemperaturfühler erwartet, aber nicht angeschlossen: HA02 auf 'Nicht verwendet' setzen oder Fühler anschließen",
    ),
    "room_humidity_probe_missing": (
        "Room humidity probe expected but not wired: set 'T/H probe humidity input' (HA03) to Unused, or wire the probe",
        "Raumfeuchtefühler erwartet, aber nicht angeschlossen: HA03 auf 'Nicht verwendet' setzen oder Fühler anschließen",
    ),
    "probe_input_unrecognised": (
        "A probe input (HA02/HA03) holds an unknown code: pick an option or check the wiring",
        "Ein Fühlereingang (HA02/HA03) hat einen unbekannten Code: Option wählen oder Verdrahtung prüfen",
    ),
    "time_programs_enabled": (
        "Time programs may switch the unit off: turn off 'Time programs enabled' (PH03) for Modbus-only control",
        "Zeitprogramme können das Gerät ausschalten: für reine Modbus-Steuerung 'Zeitprogramme' (PH03) ausschalten",
    ),
    "free_cooling_without_outdoor_probe": (
        "Free cooling is on but no outdoor probe is wired: turn off 'Enable free cooling/heating' (PG03)",
        "Free-Cooling ist an, aber kein Außenfühler angeschlossen: 'Free-Cooling/Heating freigeben' (PG03) ausschalten",
    ),
    "temperature_unit_fahrenheit": (
        "The unit is set to Fahrenheit: set 'Temperature unit' (PH05) to Celsius",
        "Das Gerät steht auf Fahrenheit: 'Temperatureinheit' (PH05) auf Celsius stellen",
    ),
    "water_pump_output_not_configured": (
        "Relay K5 (water valve / pump) is not configured: check HD05 and the wiring",
        "Relais K5 (Wasserventil/Pumpe) ist nicht konfiguriert: HD05 und Verdrahtung prüfen",
    ),
    "winter_dehumidify_on_brine": (
        "Brine circuit without a temperature guard allows winter dehumidifying (coil can freeze): set 'Winter dehumidification' (PU02) to Disabled or configure a brine guard",
        "Solekreis ohne Temperaturwächter erlaubt Winter-Entfeuchtung (Register kann einfrieren): 'Winter-Entfeuchtung' (PU02) deaktivieren oder Soleüberwachung einrichten",
    ),
}

# Registers written (in order) when the integration is set up, to make sure
# Modbus control is actually permitted by the unit.
BMS_ENABLE_KEYS = (C_ENABLE_ONOFF_BMS, C_ENABLE_DEHUM_BMS, C_ENABLE_INT_BMS)

# Settings that must hold when no CNU2 display is fitted: {key: (decoded, raw)}.
# Without them the unit sits OFF-by-display and expects room T/H from a display
# that is not there (handbook section 5.1). Asserted like the BMS enables.
HEADLESS_SETTINGS: Dict[str, tuple[str, int]] = {
    C_ENABLE_ONOFF_DISPLAY: ("off", 0),
    C_PROBE_SOURCE: ("none_or_external", 0),
}

# ------------------------------------------------------------------
# Device-page grouping
#
# SETUP_KEYS live on a child device ("<name> setup"): everything the user must
# look at or decide once, right after the integration connects - the gate for
# operational requests, the setup check, the settings the integration asserts
# or that make the unit stop (display, probes, Modbus enables, time programs,
# remote contact), and the read-only facts that describe how the unit is wired.
# CONFIG_KEYS are parameters tuned after setup (Configuration section of the main
# device). DIAGNOSTIC_KEYS are read-only extras (Diagnostic section). Everything
# else - climate, fan, the request switches, live readings, alarms - is the
# operational surface of the main device.
# ------------------------------------------------------------------
SETUP_KEYS = frozenset(
    {
        C_OPERATION_ALLOWED,
        C_SETUP_CHECK,
        C_UNIT_STATUS,
        C_ENABLE_ONOFF_DISPLAY,
        C_PROBE_SOURCE,
        C_ENABLE_ONOFF_BMS,
        C_ENABLE_DEHUM_BMS,
        C_ENABLE_INT_BMS,
        C_AI2_ALLOCATION,
        C_AI3_ALLOCATION,
        C_TIME_PROGRAMS,
        C_ENABLE_FREE_COOLING,
        C_REMOTE_ONOFF_INPUT,
        C_REMOTE_CONTACT_CLOSED,
        C_ONOFF_BY_DI_REQUEST,
        C_SEASON_OWNER,
        C_TEMPERATURE_UNIT,
        C_MACHINE_TYPE,
        C_ACTIVE_COOLING_AVAILABLE,
        C_FAN_OUTPUT_ALLOCATION,
        C_DAMPER_RELAY_ALLOCATION,
        C_DAMPER_PRESTART,
        C_TEMP_PROBE_OK,
        C_HUMIDITY_PROBE_OK,
    }
)
CONFIG_KEYS = frozenset(
    {
        C_HUMIDITY_SETPOINT,
        C_SUMMER_SETPOINT,
        C_WINTER_SETPOINT,
        C_FAN_MIN_DEHUM,
        C_FAN_MAX_DEHUM,
        C_FAN_MIN_COOLING,
        C_FAN_MIN_VMC,
        C_FAN_MAX_COOLING,
        C_DEHUM_DIFFERENTIAL,
        C_MIN_ROOM_TEMP_DEHUM,
        C_MIN_ROOM_TEMP_DIFF,
        C_FAN_MIN_RUNTIME,
        C_FAN_POST_RUN_TIME,
        C_HUMIDITY_SETPOINT_MIN,
        C_HUMIDITY_SETPOINT_MAX,
        C_FORCE_DEHUM_IN_COOLING,
        C_WINTER_DEHUM,
    }
)
DIAGNOSTIC_KEYS = frozenset(
    {
        C_FAN_MANUAL_REQUEST,
        C_MAX_TOTAL_AIRFLOW,
        C_SUPPLY_FAN_MAX_AIRFLOW,
        C_WATER_VALVE_PUMP,
        C_WATER_CONDENSER_VALVE,
        C_WATER_CHECK,
    }
)
# Suffixes of the child devices' identifiers (parent identifier + suffix).
SETUP_DEVICE_SUFFIX = "-setup"
INSTALLER_DEVICE_SUFFIX = "-installer"

# Shown on the main device only when a room probe can make them act: without
# one the unit ignores its setpoints, and Home Assistant must do the control.
TEMPERATURE_TARGET_KEYS = frozenset({C_SUMMER_SETPOINT, C_WINTER_SETPOINT})
HUMIDITY_TARGET_KEYS = frozenset({C_HUMIDITY_SETPOINT, C_DEHUM_DIFFERENTIAL})
# HA02 / HA03 options that put a room probe on AI2 / AI3.
ROOM_TEMP_PROBE_CODES = frozenset(v for k, v in ROOM_TEMP_PROBE_INPUT.items() if k)
ROOM_HUMIDITY_PROBE_CODES = frozenset(
    v for k, v in ROOM_HUMIDITY_PROBE_INPUT.items() if k
)


def entity_category_for(key: str) -> EntityCategory | None:
    """Entity category of a key; setup items stay uncategorised on their device."""
    if key in SETUP_KEYS:
        return None
    if key == C_INSTALLER_REFRESH:
        return EntityCategory.CONFIG
    if key == C_INSTALLER_LAST_READ:
        return EntityCategory.DIAGNOSTIC
    if key in INSTALLER_KEYS:
        # Writable parameters under Configuration, fixed facts under Diagnostic.
        props = ENTITIES_DICT[key]
        return (
            EntityCategory.DIAGNOSTIC if props.get("RW") == 0 else EntityCategory.CONFIG
        )
    if key in CONFIG_KEYS:
        return EntityCategory.CONFIG
    if key in DIAGNOSTIC_KEYS:
        return EntityCategory.DIAGNOSTIC
    return None


# Computed sensors: not backed by Modbus registers; values are written by the
# hub after each decode cycle using model calibration parameters.
COMPUTED_SENSORS: Dict[str, Dict[str, Any]] = {
    C_MAX_TOTAL_AIRFLOW: {"NAME": "Max total airflow", "UNIT": "m³/h"},
    C_SUPPLY_FAN_MAX_AIRFLOW: {"NAME": "Supply fan max airflow", "UNIT": "m³/h"},
    C_SUPPLY_FAN_AIRFLOW: {"NAME": "Supply fan airflow", "UNIT": "m³/h"},
    # OPTIONS makes it an enum sensor; the list of open issues is an attribute.
    C_SETUP_CHECK: {"NAME": "Setup check", "OPTIONS": ["ok", "attention"]},
    C_WATER_CHECK: {"NAME": "Water circuit check", "OPTIONS": ["ok", "attention"]},
    C_INSTALLER_LAST_READ: {
        "NAME": "Installer parameters last read",
        "DC": SensorDeviceClass.TIMESTAMP,
    },
}
# Computed binary sensors, written by the hub like COMPUTED_SENSORS. The brine
# guard is a problem indicator: on = the guard blocks requests. It is only
# created when a brine temperature entity is configured.
COMPUTED_BINARY_SENSORS: Dict[str, Dict[str, Any]] = {
    C_BRINE_GUARD: {
        "NAME": "Brine temperature guard",
        "DC": BinarySensorDeviceClass.PROBLEM,
    },
}

# Requests that make the unit do something. They are refused until the user
# turns on "Allow operational requests"; switching things OFF and all
# configuration writes always go through. A fan setpoint of 0 is not a request.
OPERATIONAL_KEYS = (C_UNIT_ON_OFF, C_DEHUMIDIFY, C_ACTIVE_COOLING, C_FAN_MANUAL)


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
    """Describes a writable numeric register.

    Bounds/unit live in the base class' ``native_*`` fields, which
    ``NumberEntity`` reads directly - no per-entity copying needed.
    """


@dataclass
class MyButtonEntityDescription(ButtonEntityDescription):
    """Describes an action button (not backed by a register)."""


@dataclass
class MyFanEntityDescription(FanEntityDescription):
    """Describes the composite supply-fan entity."""


@dataclass
class MyClimateEntityDescription(ClimateEntityDescription):
    """Describes the composite climate entity."""

    temperature_unit: str = UnitOfTemperature.CELSIUS
    supported_features: ClimateEntityFeature = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_HUMIDITY
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )


# Typed dicts populated by init().
SENSOR_TYPES: dict[str, MySensorEntityDescription] = {}
BINARYSENSOR_TYPES: dict[str, MyBinarySensorEntityDescription] = {}
BINARY_TYPES: dict[str, MyBinaryEntityDescription] = {}
SELECT_TYPES: dict[str, MySelectEntityDescription] = {}
NUMBER_TYPES: dict[str, MyNumberEntityDescription] = {}
CLIMATE_TYPES: dict[str, MyClimateEntityDescription] = {}
FAN_TYPES: dict[str, MyFanEntityDescription] = {}
BUTTON_TYPES: dict[str, MyButtonEntityDescription] = {}
# Composite switches that are not backed by a register.
OPERATION_TYPES: dict[str, MyBinaryEntityDescription] = {}


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


def is_probe_sentinel(raw_word: int) -> bool:
    """True if an unsigned register word is the "no probe / failed" marker."""
    return PROBE_SENTINEL_LOW <= raw_word <= PROBE_SENTINEL_HIGH


def is_entity_climate(props: Dict[str, Any]) -> bool:
    return get_entity_unit(props) in TEMP_UNITS and get_entity_platform(props) in (
        None,
        Platform.CLIMATE,
    )


def get_entity_select_values_and_default(
    props: dict[str, Any],
) -> tuple[list[str], str | None]:
    values = get_entity_select(props) or {}
    return list(values.values()), values.get(props.get("DEFAULT"))


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
        # No device class by default: fan/compressor outputs are percentages,
        # not humidity. Entities that really are humidity set "DC" explicitly.
        return "%", None, SensorStateClass.MEASUREMENT
    if u == "ppm":
        # SensorDeviceClass.AQI only permits a None unit, so pairing it with
        # ppm is rejected by HA. Leave the device class unset.
        return "ppm", None, SensorStateClass.MEASUREMENT
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
    # Also composite: backed by the manual-speed register plus status readings.
    FAN_TYPES["hrds_supply_fan"] = MyFanEntityDescription(
        key="hrds_supply_fan",
        name="Supply fan",
        translation_key="hrds_supply_fan",
    )

    BUTTON_TYPES[C_INSTALLER_REFRESH] = MyButtonEntityDescription(
        key=C_INSTALLER_REFRESH,
        name="Refresh installer parameters",
        translation_key=C_INSTALLER_REFRESH,
        entity_category=entity_category_for(C_INSTALLER_REFRESH),
    )

    OPERATION_TYPES[C_OPERATION_ALLOWED] = MyBinaryEntityDescription(
        key=C_OPERATION_ALLOWED,
        name="Allow operational requests",
        translation_key=C_OPERATION_ALLOWED,
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
                    entity_category=entity_category_for(key),
                    entity_registry_enabled_default=props.get("ENABLED", True),
                    device_class=SensorDeviceClass.ENUM,
                    options=[
                        v for k, v in get_entity_select(props).items() if k != "default"
                    ],
                )
            else:
                unit, device_class, state_class = _unit_mapping(get_entity_unit(props))
                device_class = props.get("DC", device_class)
                SENSOR_TYPES[key] = MySensorEntityDescription(
                    key=key,
                    name=name,
                    translation_key=key,
                    entity_category=entity_category_for(key),
                    entity_registry_enabled_default=props.get("ENABLED", True),
                    native_unit_of_measurement=unit,
                    device_class=device_class,
                    state_class=state_class,
                )
        elif cls is MyBinarySensorEntityDescription:
            BINARYSENSOR_TYPES[key] = MyBinarySensorEntityDescription(
                key=key,
                name=name,
                translation_key=key,
                entity_category=entity_category_for(key),
                entity_registry_enabled_default=props.get("ENABLED", True),
            )
        elif cls is MyBinaryEntityDescription:
            BINARY_TYPES[key] = MyBinaryEntityDescription(
                key=key,
                name=name,
                translation_key=key,
                entity_category=entity_category_for(key),
                entity_registry_enabled_default=props.get("ENABLED", True),
            )
        elif cls is MySelectEntityDescription:
            values, default = get_entity_select_values_and_default(props)
            SELECT_TYPES[key] = MySelectEntityDescription(
                key=key,
                name=name,
                translation_key=key,
                entity_category=entity_category_for(key),
                entity_registry_enabled_default=props.get("ENABLED", True),
                options=values,
                default_select_option=default,
            )
        elif cls is MyNumberEntityDescription:
            NUMBER_TYPES[key] = MyNumberEntityDescription(
                key=key,
                name=name,
                translation_key=key,
                entity_category=entity_category_for(key),
                entity_registry_enabled_default=props.get("ENABLED", True),
                native_min_value=get_entity_min(props),
                native_max_value=get_entity_max(props),
                native_step=get_entity_step(props),
                native_unit_of_measurement=get_entity_unit(props),
                mode=NumberMode.BOX,
            )
        else:
            _LOGGER.warning("Unclassified entity %s: %s", key, props)

    for key, props in COMPUTED_SENSORS.items():
        if props.get("OPTIONS"):
            SENSOR_TYPES[key] = MySensorEntityDescription(
                key=key,
                name=props["NAME"],
                translation_key=key,
                entity_category=entity_category_for(key),
                entity_registry_enabled_default=props.get("ENABLED", True),
                device_class=SensorDeviceClass.ENUM,
                options=list(props["OPTIONS"]),
            )
            continue
        unit, device_class, state_class = _unit_mapping(props.get("UNIT"))
        device_class = props.get("DC", device_class)
        SENSOR_TYPES[key] = MySensorEntityDescription(
            key=key,
            name=props["NAME"],
            translation_key=key,
            entity_category=entity_category_for(key),
            native_unit_of_measurement=unit,
            device_class=device_class,
            state_class=state_class,
        )

    for key, props in COMPUTED_BINARY_SENSORS.items():
        BINARYSENSOR_TYPES[key] = MyBinarySensorEntityDescription(
            key=key,
            name=props["NAME"],
            translation_key=key,
            entity_category=entity_category_for(key),
            device_class=props.get("DC"),
        )

    _initialized = True


init()
