"""Run tests/wiring_check.py as part of the pytest suite.

It runs in a subprocess: the script replaces ``homeassistant`` in
``sys.modules`` with stubs, which would break the real-HA tests in this process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_wiring_check():
    script = Path(__file__).with_name("wiring_check.py")
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
