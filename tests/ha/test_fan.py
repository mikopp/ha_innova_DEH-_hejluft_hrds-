"""Fan speeds: commanded (PM20) vs actual (639) under each firmware hypothesis.

The real mapping from PM20 to fan output is not confirmed yet (plans/todo.md),
so the simulator offers three models. Whichever applies, the integration must
report the actual output as state, the commanded value as attribute / number,
and derive airflow from the actual output.
"""

from __future__ import annotations

import pytest
from homeassistant.const import STATE_UNKNOWN

from tests.sim import registers as R

from .conftest import CLIMATE, FAN, add_entry, allow_operation, set_hvac_mode

# Factory band during dehumidify: PF28 = 50 %, PF10 = 85 %.
EXPECTED_ACTUAL = {
    "rescale": {0: 50.0, 30: 60.5, 55: 69.25, 85: 79.75, 100: 85.0},
    "clamp": {0: 50.0, 30: 50.0, 55: 55.0, 85: 85.0, 100: 85.0},
    "direct": {0: 0.0, 30: 30.0, 55: 55.0, 85: 85.0, 100: 100.0},
}


def _fan_mode(actual: float) -> str:
    if actual < 5:
        return "off"
    if actual < 42.5:
        return "low"
    if actual < 70:
        return "medium"
    return "high"


@pytest.mark.parametrize("model", list(EXPECTED_ACTUAL))
async def test_fan_percentage_during_dehumidify(setup, clock, model):
    s = setup
    s.device.set_fan_model(model)
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")

    for commanded, actual in EXPECTED_ACTUAL[model].items():
        await s.service("fan", "set_percentage", FAN, percentage=commanded)
        await clock.settle()
        assert s.device.holding[R.FAN_MANUAL] == commanded * 100

        fan = s.state("fan", FAN)
        assert fan.attributes["commanded_percent"] == pytest.approx(commanded)
        assert fan.attributes["percentage"] == round(actual)
        assert float(s.state("sensor", "supply_fan_output").state) == pytest.approx(
            actual
        )
        assert float(s.state("number", "fan_manual_speed").state) == pytest.approx(
            commanded
        )
        airflow = float(s.state("sensor", "supply_fan_airflow").state)
        assert airflow == pytest.approx(min(300.0, actual / 100 * 300.0))
        assert s.state("climate", CLIMATE).attributes["fan_mode"] == _fan_mode(actual)


@pytest.mark.parametrize(
    ("fan_mode", "commanded"), [("low", 30), ("medium", 55), ("high", 85)]
)
async def test_climate_fan_modes_write_pm20(setup, clock, fan_mode, commanded):
    s = setup
    await allow_operation(s)
    await s.service("climate", "set_fan_mode", CLIMATE, fan_mode=fan_mode)
    await clock.settle()
    assert s.device.holding[R.FAN_MANUAL] == commanded * 100


async def test_no_optimistic_update_before_poll(setup, clock):
    s = setup
    s.device.set_fan_model("direct")
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    await s.service("fan", "set_percentage", FAN, percentage=30)
    # Before the debounced refresh the state still shows the old actual value.
    assert s.state("fan", FAN).attributes["percentage"] == 0
    await clock.settle()
    assert s.state("fan", FAN).attributes["percentage"] == 30


async def test_per_mode_minimum_moves_output(setup, clock):
    s = setup
    s.device.set_fan_model("clamp")
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    await s.service("fan", "set_percentage", FAN, percentage=20)
    await clock.settle()
    assert float(s.state("sensor", "supply_fan_output").state) == 50.0
    await s.service("number", "set_value", "fan_min_speed_dehumidify", value=20)
    await clock.settle()
    assert float(s.state("sensor", "supply_fan_output").state) == 20.0


async def test_airflow_zero_when_fan_off(setup, clock):
    s = setup
    assert s.state("sensor", "supply_fan_status").state == "off"
    assert float(s.state("sensor", "supply_fan_airflow").state) == 0.0
    assert s.state("fan", FAN).state == "off"


async def test_recirculation_is_damper_open_and_fan_running(setup, clock):
    s = setup
    assert s.state("binary_sensor", "recirculation_active").state == "off"
    await allow_operation(s)
    # The damper opens with the request; the fan waits out the pre-start.
    s.device.sequence_delay = 3600
    await set_hvac_mode(s, clock, "dry")
    assert s.state("sensor", "recirculation_damper").state == "on"
    assert s.state("sensor", "supply_fan_status").state == "wait_on"
    assert s.state("binary_sensor", "recirculation_active").state == "off"

    s.device.sequence_delay = 0
    await clock.poll()
    assert s.state("sensor", "supply_fan_status").state == "on"
    assert s.state("binary_sensor", "recirculation_active").state == "on"
    # 1112 stays 0 while the unit recirculates (UNIT_BEHAVIOUR.md T16, T18).
    assert s.state("binary_sensor", "fan_integration_request").state == "off"

    await set_hvac_mode(s, clock, "fan_only")
    assert s.state("binary_sensor", "recirculation_active").state == "off"


async def test_fan_speed_unknown_without_a_tachometer_input(setup, clock):
    s = setup
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert float(s.state("sensor", "supply_fan_output").state) > 0
    assert s.device.input[R.FAN_RPM] == 0
    assert s.state("sensor", "supply_fan_rpm").state == STATE_UNKNOWN


async def test_fan_speed_shown_with_a_tachometer_input(hass, sim, clock):
    sim.device.holding[R.TACHOMETER_ALLOCATIONS[-1]] = 45  # HB07: DI3 expansion
    s = await add_entry(hass, sim)
    await allow_operation(s)
    await set_hvac_mode(s, clock, "dry")
    assert float(s.state("sensor", "supply_fan_rpm").state) > 0
