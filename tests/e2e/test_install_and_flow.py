"""Needs a real HA because: the integration is installed and loaded by Home
Assistant itself (manifest requirement resolved, files loaded from
``custom_components/``) and set up through the config/options flow as
REST/websocket JSON (form schema and selector serialisation, error keys).

What the flow *does* with its answers is tested in-process
(tests/ha/test_config_flow.py); only what travels over HTTP is tested here.
"""

from __future__ import annotations

import pytest

from .conftest import DOMAIN, user_input


def _live(entry, key: str) -> bool:
    """The entity exists and is provided by the running integration.

    A disabled-by-default or no-longer-created entity can stay in the registry
    (as ``unavailable``), so the registry alone cannot tell.
    """
    entry.entity_ids.clear()
    try:
        state = entry.ha.get_state(entry.eid(key))
    except KeyError:
        return False
    return state is not None and state["state"] != "unavailable"


def _submit(ha, host: str, port: int, **overrides):
    flow = ha.flow_start(DOMAIN)
    return ha.flow_configure(flow["flow_id"], user_input(host, port, **overrides))


@pytest.mark.needs_real_ha("install-path")
def test_entry_is_installed_loaded_and_polling(headless):
    entry = next(
        e
        for e in headless.ha.config_entries(DOMAIN)
        if e["entry_id"] == headless.entry_id
    )
    assert entry["state"] == "loaded"
    assert headless.has("hrds_climate")
    headless.assert_state("unit_status", lambda s: s["state"] in ("off_by_bms", "on"))


@pytest.mark.needs_real_ha("http-surface")
def test_devices_in_the_real_registry(headless):
    devices = [
        d
        for d in headless.ha.device_registry()
        if headless.entry_id in d["config_entries"]
    ]
    main = [d for d in devices if d["via_device_id"] is None]
    children = [d for d in devices if d["via_device_id"] is not None]
    assert len(main) == 1
    assert main[0]["model_id"] == "EPB9ORSINDEU"
    assert main[0]["sw_version"] == "V01.00.09.02"
    # The installer device is opt-in (options), so a new entry has none.
    assert {d["name"] for d in children} == {"HRDS headless setup"}
    assert all(d["via_device_id"] == main[0]["id"] for d in children)


@pytest.mark.needs_real_ha("http-surface")
def test_flow_cannot_connect(ha):
    result = _submit(ha, "127.0.0.3", 5099)  # nothing listens there
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.needs_real_ha("http-surface")
def test_flow_wrong_device(ha, sims):
    spare = sims["spare"]
    spare.call("/reset")
    spare.fault(identity={"0": "ACME", "1": "HEATPUMP-9", "2": "1.0"})
    try:
        result = _submit(ha, spare.address, spare.port)
        assert result["errors"] == {"base": "wrong_device"}
        assert spare.writes() == [], "nothing may be written to a foreign device"
    finally:
        spare.call("/reset")


@pytest.mark.needs_real_ha("http-surface")
def test_flow_already_configured(ha, headless):
    result = _submit(ha, "127.0.0.1", headless.sim.port)
    assert result["errors"] == {"host": "already_configured"}


@pytest.mark.needs_real_ha("http-surface")
def test_options_form_serialises_the_brine_selector(hl):
    flow = hl.ha.options_flow_start(hl.entry_id)
    try:
        fields = {f["name"]: f for f in flow["data_schema"]}
        selector = fields["brine_temperature_entity"]["selector"]
        assert selector["entity"]["domain"] == ["sensor"]
        assert selector["entity"]["device_class"] == ["temperature"]
        assert not _live(hl, "brine_temperature_guard")  # hidden without a sensor
    finally:
        hl.ha.options_flow_abort(flow["flow_id"])

    hl.options(
        water_circuit="brine",
        brine_temperature_entity="sensor.brine_supply",
        brine_min_temperature=12.0,
    )
    try:
        assert _live(hl, "brine_temperature_guard")
    finally:
        hl.options()  # back to the plain setup: clears the sensor
    assert not _live(hl, "brine_temperature_guard")
