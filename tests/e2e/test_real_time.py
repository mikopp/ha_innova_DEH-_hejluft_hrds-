"""Needs a real HA because: the poll runs on Home Assistant's real scheduler
and executor, with no time manipulation (in-process tests fire timers by hand).
"""

from __future__ import annotations

import pytest

from .conftest import SCAN_INTERVAL

WATER_TEMPERATURE = 501


@pytest.mark.needs_real_ha("real-time")
def test_entity_follows_the_unit_in_real_time(hl):
    hl.sim.call("/set", {"input": {str(WATER_TEMPERATURE): 214}})
    hl.assert_state("water_temperature", "21.4", timeout=2 * SCAN_INTERVAL + 5)
