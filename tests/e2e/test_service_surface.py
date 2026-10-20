"""Needs a real HA because: service calls arrive as REST/websocket requests
and their errors are serialised into codes and messages (``http-surface``).
What the services *do* to the unit is tested in-process (tests/ha); here only
the surface a client sees: one refusal, one working cycle, one failed write.
"""

from __future__ import annotations

import pytest

from .ha_client import ServiceError

pytestmark = pytest.mark.needs_real_ha("http-surface")

CLIMATE = "hrds_climate"
DEU_REQUEST = 1140


def test_gate_refusal_is_a_service_validation_error(hl):
    with pytest.raises(ServiceError) as err:
        hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    assert err.value.code == "service_validation_error"
    assert "Operational requests are not allowed" in err.value.message
    assert all(value == 0 for _address, value in hl.sim.writes())


def test_dry_cycle_through_the_service_api(hl):
    hl.allow_operation()
    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
    hl.assert_state(CLIMATE, "dry", {"hvac_action": "drying"})
    hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    hl.assert_state(CLIMATE, "off")


def test_rejected_write_is_a_home_assistant_error(hl):
    # The hub logs this failure as an ERROR; test_zz_log_hygiene allows it.
    hl.allow_operation()
    hl.sim.fault(reject_writes=[DEU_REQUEST])
    try:
        with pytest.raises(ServiceError) as err:
            hl.service("climate", "set_hvac_mode", CLIMATE, hvac_mode="dry")
        assert err.value.code == "home_assistant_error"
    finally:
        hl.sim.fault(reject_writes=[])
