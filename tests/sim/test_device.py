"""Unit tests of the device model alone (no Modbus, no Home Assistant)."""

from __future__ import annotations

import pytest

from tests.sim import registers as R
from tests.sim.device import DeviceFailure, HrdsDevice, IllegalAddress
from tests.sim.seeds import list_seeds, load_seed


def _enable_and_wake(dev: HrdsDevice) -> None:
    """What the integration does on its first poll without a display."""
    for addr, value in (
        (R.PH02_ONOFF_BMS, 1),
        (R.PH27_INT_BMS, 1),
        (R.PH28_DEU_BMS, 1),
        (R.PH01_ONOFF_DISPLAY, 0),
        (R.HA00_PROBE_SOURCE, 0),
    ):
        dev.write(addr, value)


@pytest.mark.parametrize("seed", list_seeds())
def test_every_seed_loads_with_identity(seed):
    s = load_seed(seed)
    assert s.identity.get(0) and s.identity.get(1)
    assert R.UNIT_STATUS in s.input and R.HB04_SEASON in s.holding


def test_factory_state_is_off_by_display():
    dev = HrdsDevice()
    assert dev.read("input", R.UNIT_STATUS, 1) == [0]
    assert dev.read("input", R.ROOM_TEMP, 1) == [R.PROBE_SENTINEL]


def test_unknown_address_is_illegal():
    dev = HrdsDevice()
    with pytest.raises(IllegalAddress):
        dev.read("input", 2000, 1)
    with pytest.raises(IllegalAddress):
        dev.write(2000, 1)


def test_on_off_ignored_without_bms_enable():
    dev = HrdsDevice()
    dev.write(R.BMS_ON, 1)
    assert dev.holding[R.BMS_ON] == 0
    assert dev.write_log[-1].accepted is False


def test_enables_turn_unit_on():
    dev = HrdsDevice()
    _enable_and_wake(dev)
    assert dev.read("input", R.UNIT_STATUS, 1) == [2]  # off_by_bms
    dev.write(R.BMS_ON, 1)
    assert dev.read("input", R.UNIT_STATUS, 1) == [5]


def test_dehumidify_sequence_and_off_wins():
    dev = HrdsDevice()
    _enable_and_wake(dev)
    dev.write(R.DEU_REQUEST, 1)
    dev.write(R.BMS_ON, 1)
    i = dev.input
    assert i[R.DEHUM_REQUEST] == 1
    assert i[R.DAMPER] == 1  # R variant
    assert i[R.WATER_VALVE_PUMP] == 1
    assert i[R.FAN_STATUS] == 3
    assert i[R.COMPRESSOR_STATUS] == 4
    dev.write(R.BMS_ON, 0)
    assert i[R.COMPRESSOR_STATUS] == 6 and i[R.FAN_STATUS] == 1


def test_winter_integration_heats_without_compressor():
    dev = HrdsDevice()
    _enable_and_wake(dev)
    dev.write(R.HB04_SEASON, R.SEASON_WINTER)
    dev.write(R.INT_REQUEST, 1)
    dev.write(R.BMS_ON, 1)
    assert dev.input[R.SEASON_READBACK] == 1
    assert dev.input[R.COMPRESSOR_STATUS] == 6
    assert dev.input[R.WATER_VALVE_PUMP] == 1


def test_invalid_season_raises_al25_and_stops():
    dev = HrdsDevice()
    _enable_and_wake(dev)
    dev.write(R.DEU_REQUEST, 1)
    dev.write(R.BMS_ON, 1)
    dev.write(R.HB04_SEASON, 7)
    reg, bit = R.alarm_bit("AL25")
    assert dev.input[reg] & (1 << bit)
    assert dev.input[R.COMPRESSOR_STATUS] == 6
    dev.write(R.HB04_SEASON, R.SEASON_SUMMER)
    assert not dev.input[reg] & (1 << bit)


def test_humidity_setpoint_clamped():
    dev = HrdsDevice()
    assert dev.write(R.HUMIDITY_SETPOINT, 90) == dev.holding[R.PH30_HUM_MAX]
    assert dev.write(R.HUMIDITY_SETPOINT, 10) == dev.holding[R.PH29_HUM_MIN]


def _dehumidify(dev: HrdsDevice) -> None:
    _enable_and_wake(dev)
    dev.write(R.DEU_REQUEST, 1)
    dev.write(R.BMS_ON, 1)


def test_fan_starts_at_the_band_minimum_and_follows_a_raised_one():
    """T22, T24-T26: the unit's manual request is clamped into the band."""
    dev = HrdsDevice()
    assert dev.holding[R.FAN_MANUAL] == 0
    _dehumidify(dev)
    assert dev.input[R.FAN_OUTPUT] == dev.holding[R.FAN_MANUAL] == 5000
    dev.write(R.PF28_FAN_MIN_DEU, 4500)
    assert dev.input[R.FAN_OUTPUT] == 5000
    dev.write(R.PF28_FAN_MIN_DEU, 5500)
    assert dev.input[R.FAN_OUTPUT] == dev.input[R.FAN_MANUAL_REQUEST] == 5500
    dev.write(R.PF28_FAN_MIN_DEU, 5000)
    assert dev.input[R.FAN_OUTPUT] == 5500
    dev.write(R.DEU_REQUEST, 0)
    assert dev.input[R.FAN_OUTPUT] == dev.holding[R.FAN_MANUAL] == 0


def test_pm20_write_is_not_kept_and_outside_the_band_refused():
    """T23, T27, T28."""
    dev = HrdsDevice()
    _dehumidify(dev)
    assert dev.write(R.FAN_MANUAL, 6000) == 5000
    assert not dev.write_log[-1].accepted
    with pytest.raises(DeviceFailure):
        dev.write(R.FAN_MANUAL, 4000)
    assert dev.input[R.FAN_OUTPUT] == 5000


def test_compressor_alarm_and_reset_register():
    dev = HrdsDevice()
    _enable_and_wake(dev)
    dev.write(R.DEU_REQUEST, 1)
    dev.write(R.BMS_ON, 1)
    dev.raise_alarm("AL11")
    assert dev.input[R.COMPRESSOR_STATUS] == 1
    assert dev.input[R.ANY_ALARM] == 1
    dev.write(R.ALARM_RESET_BASE + 11, 1)
    assert dev.input[R.COMPRESSOR_STATUS] == 4


def test_probe_alarm_when_allocated_probe_missing():
    dev = HrdsDevice(overlays=("display_with_probes",))
    dev.write(R.PH02_ONOFF_BMS, 1)
    dev.write(R.BMS_ON, 1)
    assert dev.input[R.UNIT_STATUS] == 5
    reg, bit = R.alarm_bit("AL28")
    assert not dev.input[reg] & (1 << bit)
    dev.unplug_probe(R.ROOM_TEMP)
    assert dev.input[reg] & (1 << bit)


def test_display_humidity_raises_auto_dehumidify():
    dev = HrdsDevice(overlays=("display_cnu2",))
    dev.write(R.PH02_ONOFF_BMS, 1)
    dev.write(R.BMS_ON, 1)
    assert dev.input[R.UNIT_STATUS] == 5
    assert dev.input[R.DEHUM_REQUEST] == 0  # 55 %RH, PU01 60 + PU07 3
    dev.set_room_humidity(70)
    assert dev.input[R.DEHUM_REQUEST] == 1
    assert dev.input[R.COMPRESSOR_STATUS] == 4
    dev.set_room_humidity(61)  # inside the hysteresis: keeps running
    assert dev.input[R.DEHUM_REQUEST] == 1
    dev.set_room_humidity(58)
    assert dev.input[R.DEHUM_REQUEST] == 0
    dev.set_room_humidity(70)
    dev.write(R.BMS_ON, 0)  # only switching the unit off stops it
    assert dev.input[R.DEHUM_REQUEST] == 0


def test_display_temperature_heats_by_itself_in_winter():
    """Handbook 6.1.2: INT below SEtH - PF12, off above SEtH + PF12."""
    dev = HrdsDevice(overlays=("display_cnu2",))
    dev.write(R.PH02_ONOFF_BMS, 1)
    dev.write(R.HB04_SEASON, R.SEASON_WINTER)
    dev.write(R.BMS_ON, 1)
    assert dev.input[R.WATER_VALVE_PUMP] == 0  # 22.5 degC, SEtH 14
    dev.set_input(R.ROOM_TEMP, 134)  # below 14.0 - 0.5
    assert dev.input[R.WATER_VALVE_PUMP] == 1
    assert dev.input[R.COMPRESSOR_STATUS] == 6  # heats with water only
    assert dev.input[R.DEHUM_REQUEST] == 0
    dev.set_input(R.ROOM_TEMP, 144)  # inside the dead band: keeps heating
    assert dev.input[R.WATER_VALVE_PUMP] == 1
    dev.set_input(R.ROOM_TEMP, 146)
    assert dev.input[R.WATER_VALVE_PUMP] == 0
    # PH10 caps SEtH: a higher setpoint does not raise the threshold.
    dev.set_holding(R.WINTER_SETPOINT, 200)
    assert dev.input[R.WATER_VALVE_PUMP] == 0
    dev.set_holding(R.PG02_INTEGRATION, 0)  # no INT function: never heats
    dev.set_input(R.ROOM_TEMP, 100)
    assert dev.input[R.WATER_VALVE_PUMP] == 0


def test_headless_unit_never_requests_by_itself():
    dev = HrdsDevice()
    _enable_and_wake(dev)
    dev.set_room_humidity(90)  # not a source: no display, nothing on AI3
    assert dev.input[R.DEHUM_REQUEST] == 0


def test_power_cycle_keeps_every_setting():
    dev = HrdsDevice()
    _enable_and_wake(dev)
    before = dict(dev.holding)
    dev.power_cycle()
    assert dev.holding == before


def test_display_switched_off_beats_modbus_on():
    dev = HrdsDevice(overlays=("display_with_probes",))
    dev.write(R.PH02_ONOFF_BMS, 1)
    dev.write(R.BMS_ON, 1)
    dev.set_display_on(False)
    assert dev.input[R.UNIT_STATUS] == 0


def test_non_r_variant_has_no_damper():
    dev = HrdsDevice(overlays=("non_r",))
    _enable_and_wake(dev)
    dev.write(R.DEU_REQUEST, 1)
    dev.write(R.BMS_ON, 1)
    assert dev.input[R.DAMPER] == 2
    assert dev.input[R.COMPRESSOR_STATUS] == 4
