"""Fan speeds in real Home Assistant: commanded vs actual per firmware model."""

from __future__ import annotations

import pytest

CLIMATE = "hrds_climate"
FAN = "hrds_supply_fan"
PM20 = 1614

# Actual output during dehumidify with the factory 50-85 % band.
CASES = {
    "rescale": [(30, 60.5), (85, 79.75)],
    "clamp": [(30, 50.0), (60, 60.0), (100, 85.0)],
    "direct": [(30, 30.0), (85, 85.0)],
}


@pytest.mark.parametrize("model", list(CASES))
def test_commanded_vs_actual(hl, model):
    hl.sim.fault(fan_model=model)
    hl.allow_operation()
    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    hl.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})
    for commanded, actual in CASES[model]:
        hl.service("fan", "set_percentage", FAN, percentage=commanded)
        assert hl.sim.holding(PM20) == commanded * 100
        hl.assert_state("supply_fan_output", lambda s, a=actual: float(s["state"]) == a)
        fan = hl.assert_state(FAN, "on", {"commanded_percent": float(commanded)})
        assert fan["attributes"]["percentage"] == round(actual)
        assert float(hl.state("fan_manual_speed")["state"]) == commanded
        airflow = float(hl.state("supply_fan_airflow")["state"])
        assert airflow == pytest.approx(min(300.0, actual * 3))


@pytest.mark.parametrize(("mode", "pct"), [("low", 30), ("medium", 55), ("high", 85)])
def test_climate_fan_modes(hl, mode, pct):
    hl.allow_operation()
    hl.service("climate", "set_fan_mode", CLIMATE, fan_mode=mode)
    hl.sim.wait_for(lambda s: s["holding"][str(PM20)] == pct * 100, timeout=10)


def test_fan_off_means_no_airflow(hl):
    hl.assert_state(FAN, "off")
    hl.assert_state("supply_fan_airflow", lambda s: float(s["state"]) == 0.0)
