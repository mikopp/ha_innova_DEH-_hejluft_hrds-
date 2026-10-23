"""Register addresses the simulator models (direct PDU addresses).

Taken from ``doc/references/MODBUS_REGISTERS.md``, not from the integration's
``const.py`` (see the package docstring for why).
"""

# --- input registers (FC 04) -------------------------------------------------
REMOTE_CONTACT = 257  # packed; bit 0 = remote on/off contact closed
ROOM_TEMP = 499  # AI_TreturnRoom, x0.1 degC, INT16
OUTDOOR_TEMP = 500
WATER_TEMP = 501
EXHAUST_TEMP = 502
SUPPLY_TEMP = 503
ROOM_HUMIDITY = 505  # AI_HretRoom, %RH
AIR_QUALITY = 506
FAN_OUTPUT = 639  # outAO_SupplyFan, x0.01 %
COMPRESSOR_OUTPUT = 641  # x0.01 %
ALARMS_1 = 768  # bit n = AL(n+1)
ALARMS_2 = 769  # bit n = AL(n+17)
ALARMS_3 = 770  # bit n = AL(n+33)
ANY_ALARM = 1103
UNIT_STATUS = 1104
MODE_STATUS = 1110
ACTUAL_SETPOINT = 1111
FAN_INTEGRATION_REQUEST = 1112  # INT fan request, x0.01 %; 0 through DEU (T16, T18)
FAN_MANUAL_REQUEST = 1114  # mirror of PM20, x0.01 %
FAN_RPM = 1117  # 0 unless an input is allocated to the tachometer
FAN_STATUS = 1119
DEHUM_REQUEST = 1121
COMPRESSOR_STATUS = 1122
CONDENSER_VALVE = 1124
WATER_VALVE_PUMP = 1126
DAMPER = 1134
SEASON_READBACK = 1583  # 0 summer, 1 winter, 2 auto

# --- holding registers (FC 03/06/16) -----------------------------------------
BMS_ON = 1105
INT_REQUEST = 1139  # integration / active cooling
DEU_REQUEST = 1140  # dehumidify
SUMMER_SETPOINT = 1584  # x0.1 degC
WINTER_SETPOINT = 1585
HUMIDITY_SETPOINT = 1586
FAN_HOURS = 1604  # PM01, write 0 resets AL22
FAN_MANUAL = 1614  # PM20, x0.01 %
PC07_MAX_WATER = 1633  # x0.1 degC
PF26_FAN_POST_RUN = 1637  # x0.01 %, the fan's run-on speed
PU02_WINTER_DEHUM = 1689  # 0 = no dehumidifying in winter (factory)
PU07_DEHUM_DIFF = 1694  # %RH; auto DEU on above PU01 + PU07, off below PU01
PF07_FAN_MIN_VMC = 1644  # x0.01 %
PF12_TEMP_DEAD_BAND = 1649  # x0.1 degC; auto INT around SEtC / SEtH
PF09_FAN_MAX_INT = 1646
PF10_FAN_MAX_DEU = 1647
PS01_DAMPER_PRESTART = 1698  # s
PH01_ONOFF_DISPLAY = 1777
PH02_ONOFF_BMS = 1778
PH09_WINTER_SETPOINT_MIN = 1785  # x0.1 degC; SEtH clamp
PH10_WINTER_SETPOINT_MAX = 1786
PG02_INTEGRATION = 1798
HA00_PROBE_SOURCE = 1803
HA02_AI2 = 1805
HA03_AI3 = 1806
HB04_SEASON = 1825
PF27_FAN_MIN_INT = 1852
PF28_FAN_MIN_DEU = 1853
PH27_INT_BMS = 1869
PH28_DEU_BMS = 1870
PU13_MIN_ROOM_TEMP = 1889  # x0.1 degC
PH29_HUM_MIN = 1892
PH30_HUM_MAX = 1893

# Alarm reset registers 0x030B-0x031A: writing 1 to (774 + n) resets ALn.
ALARM_RESET_BASE = 774
ALARM_RESET_RANGE = range(775, 795)

# Writes that only take effect while their "by BMS" enable is set (handbook /
# MODBUS_REGISTERS.md section 3).
ENABLE_FOR = {
    BMS_ON: PH02_ONOFF_BMS,
    DEU_REQUEST: PH28_DEU_BMS,
    INT_REQUEST: PH27_INT_BMS,
}


# Unwired analog input (MODBUS_REGISTERS.md section 14.7).
PROBE_SENTINEL = 0x8004

# Input allocations that can carry the fan tachometer (input function 45 / 46
# on a digital input; MODBUS_REGISTERS.md section 16, UNIT_BEHAVIOUR.md 9.1):
# HA01, HA04-HA18 (1804, 1807-1821), HB01, HB02, HB05-HB07 (1822, 1823,
# 1826-1828). AI2/AI3 are not among them: there 45/46 are the room probes.
TACHOMETER_ALLOCATIONS = (1804, *range(1807, 1824), *range(1826, 1829))
TACHOMETER_CODES = (45, 46)

ROOM_TEMP_PROBE_CODES = (45,)
ROOM_HUMIDITY_PROBE_CODES = (53, 54)
# HA00 values whose display supplies the room humidity (CNU / EPJ / CNU2, T + H).
DISPLAY_HUMIDITY_SOURCES = (2, 4, 6)
# HA00 values whose display supplies the room temperature (every display).
DISPLAY_TEMP_SOURCES = (1, 2, 3, 4, 5, 6)

SEASON_SUMMER = 4  # HB04 values
SEASON_WINTER = 3


def alarm_bit(code: str) -> tuple[int, int]:
    """(register, bit) of alarm ``ALnn``."""
    n = int(code.upper().removeprefix("AL"))
    if 1 <= n <= 16:
        return ALARMS_1, n - 1
    if 17 <= n <= 32:
        return ALARMS_2, n - 17
    if 33 <= n <= 48:
        return ALARMS_3, n - 33
    raise ValueError(f"unknown alarm {code!r}")
