"""Config flow through the real UI API, against simulated units."""

from __future__ import annotations

from .conftest import DOMAIN, create_entry, user_input


def _submit(ha, host: str, port: int, **overrides):
    flow = ha.flow_start(DOMAIN)
    return ha.flow_configure(flow["flow_id"], user_input(host, port, **overrides))


def test_cannot_connect(ha):
    result = _submit(ha, "127.0.0.1", 5099)  # nothing listens there
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


def test_wrong_vendor(ha, sims):
    spare = sims["spare"]
    spare.call("/reset")
    spare.fault(identity={"0": "ACME", "1": "HEATPUMP-9", "2": "1.0"})
    try:
        result = _submit(ha, spare.address, spare.port)
        assert result["errors"] == {"base": "wrong_device"}
        assert spare.writes() == [], "nothing may be written to a foreign device"
    finally:
        spare.call("/reset")


def test_wrong_fingerprint_without_fc43(ha, sims):
    spare = sims["spare"]
    spare.call("/reset")
    spare.fault(fc43=False)
    spare.call("/force", {"input": {"1104": 9}})
    try:
        result = _submit(ha, spare.address, spare.port)
        assert result["errors"] == {"base": "wrong_device"}
    finally:
        spare.call("/reset")


def test_entries_created_with_device_identity(ha, headless, display):
    devices = {d["id"]: d for d in ha.device_registry()}
    main = [
        d
        for d in devices.values()
        if headless.entry_id in d["config_entries"] and d["via_device_id"] is None
    ]
    assert len(main) == 1
    assert main[0]["model_id"] == "EPB9ORSINDEU"
    assert main[0]["sw_version"] == "V01.00.09.02"
    assert {e["entry_id"] for e in ha.config_entries(DOMAIN)} >= {
        headless.entry_id,
        display.entry_id,
    }


def test_already_configured(ha, headless):
    result = _submit(ha, "127.0.0.1", headless.sim.port)
    assert result["errors"] == {"host": "already_configured"}


def test_fc43_unsupported_fingerprint_decides(ha, sims):
    spare = sims["spare"]
    spare.call("/reset")
    spare.fault(fc43=False)
    entry = create_entry(ha, spare, spare.address, name="HRDS spare")
    try:
        assert entry.state("unit_status")["state"] == "off_by_bms"
    finally:
        ha.delete_entry(entry.entry_id)
        spare.call("/reset")
