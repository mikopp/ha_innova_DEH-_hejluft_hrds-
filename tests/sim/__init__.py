"""Fake HRDS+ Modbus device for the integration tests.

The simulator is deliberately independent of ``custom_components/innova_hrds``:
its register addresses and behaviour come from
``doc/references/MODBUS_REGISTERS.md`` and the real-device dumps in
``tests/devices/``. Sharing ``const.py`` would make a wrong address in the
integration invisible to the tests, because the fake device would be wrong in
exactly the same way.

* :mod:`tests.sim.seeds` loads a real-device dump (plus optional overlays).
* :mod:`tests.sim.device` is the pure-Python device model.
* :mod:`tests.sim.server` serves that model over Modbus TCP (pymodbus).
* :mod:`tests.sim.control` is the HTTP control API used by the Docker tests.
* ``python -m tests.sim`` runs a simulator process.
"""

from .device import HrdsDevice
from .seeds import DEFAULT_SEED, list_seeds, load_seed
from .server import HrdsSimServer

__all__ = ["DEFAULT_SEED", "HrdsDevice", "HrdsSimServer", "list_seeds", "load_seed"]
