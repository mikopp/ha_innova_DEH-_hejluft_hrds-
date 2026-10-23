"""Serve an :class:`HrdsDevice` over Modbus TCP with pymodbus 3.13.

pymodbus 3.13 routes every request through ``SimDevice(action=...)``; the old
datastore classes are only a compatibility shim whose ``setValues`` is never
called. The action callback here answers reads from the device model and hands
writes to it, and injects transport faults.

The FC 43 identity lives in pymodbus' process-global control block, so only one
identity can be served per process; the server sets it when it starts.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Optional

from pymodbus.constants import ExcCodes
from pymodbus.pdu.device import ModbusControlBlock
from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from .device import DeviceFailure, HrdsDevice, IllegalAddress

_LOGGER = logging.getLogger(__name__)

_INPUT_FC = {4}
_ADDRESS_SPACE = 2048  # covers 0 - 2047; validity is decided by the model
_IDENTITY_KEYS = {0: "VendorName", 1: "ProductCode", 2: "MajorMinorRevision"}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class HrdsSimServer:
    """Modbus TCP front end for one simulated unit, with transport faults.

    Faults (attributes, change any time):

    * ``illegal_addresses`` - reads touching these answer exception 02, so the
      integration's per-register fallback has to kick in;
    * ``reject_writes`` - writes to these answer exception 04 (device failure);
    * ``delay`` - seconds to stall every request (past the client's 3 s timeout
      the request fails);
    * ``max_count`` - reads of more registers than this are never answered,
      like an RS-485 gateway (or unit) overloaded by a large block read; each
      one is counted in ``oversized_reads``;
    * ``fc43`` - False to answer FC 43 without identification objects;
    * ``wrong_unit`` - answer only this unit id (simulate a wrong slave id).
    """

    def __init__(
        self,
        device: HrdsDevice,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
    ) -> None:
        self.device = device
        self.host = host
        self.port = port or free_port()
        self.illegal_addresses: set[int] = set()
        self.reject_writes: set[int] = set()
        self.delay = 0.0
        self.max_count: Optional[int] = None
        self.oversized_reads = 0
        self.fc43 = True
        self.identity_override: Optional[dict[int, str]] = None
        self.request_count = 0
        # Every read request as (kind, address, count), for tests that check
        # which registers the integration asks for.
        self.read_log: list[tuple[str, int, int]] = []
        self._server: Optional[ModbusTcpServer] = None
        self._delays: set[asyncio.Future] = set()

    # ---- lifecycle -----------------------------------------------------------
    @property
    def online(self) -> bool:
        return self._server is not None

    async def start(self) -> None:
        if self._server is not None:
            return
        self.apply_identity()
        blocks = [
            SimData(0, count=_ADDRESS_SPACE, values=0, datatype=DataType.REGISTERS)
        ]
        bits = [SimData(0, values=False, datatype=DataType.BITS)]
        sim = SimDevice(
            id=self.device.unit_id,
            simdata=(bits, bits, blocks, list(blocks)),
            action=self._action,
        )
        self._server = ModbusTcpServer(sim, address=(self.host, self.port))
        await self._server.serve_forever(background=True)
        _LOGGER.info("HRDS+ simulator listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        # Release requests stalled by ``delay`` so no handler outlives us.
        for waiter in list(self._delays):
            waiter.cancel()
        await asyncio.sleep(0)
        await server.shutdown()

    def reset_faults(self) -> None:
        self.illegal_addresses.clear()
        self.reject_writes.clear()
        self.delay = 0.0
        self.max_count = None
        self.fc43 = True
        self.identity_override = None
        self.apply_identity()

    def apply_identity(self) -> None:
        """Publish the FC 43 objects (process-global in pymodbus)."""
        ident = ModbusControlBlock().Identity
        source = self.identity_override or self.device.identity
        for key in _IDENTITY_KEYS:
            ident[key] = source.get(key, "") if self.fc43 else ""

    # ---- request handling ----------------------------------------------------
    async def _action(
        self, function_code, start_address, address, count, registers, values
    ):
        self.request_count += 1
        if values is None:
            kind = "input" if function_code in _INPUT_FC else "holding"
            self.read_log.append((kind, address, count))
        oversized = (
            values is None and self.max_count is not None and count > self.max_count
        )
        if oversized:
            self.oversized_reads += 1
        if self.delay or oversized:
            # An oversized read is never answered (the stall outlasts any
            # client retry; stop() releases it).
            await self._stall(self.delay if not oversized else 120)
            if self._server is None or oversized:
                return ExcCodes.DEVICE_BUSY
        span = range(address, address + count)
        if values is None:
            if any(a in self.illegal_addresses for a in span):
                return ExcCodes.ILLEGAL_ADDRESS
            kind = "input" if function_code in _INPUT_FC else "holding"
            try:
                data = self.device.read(kind, address, count)
            except IllegalAddress:
                return ExcCodes.ILLEGAL_ADDRESS
            registers[address - start_address : address - start_address + count] = data
            return None
        if any(a in self.reject_writes for a in span):
            return ExcCodes.DEVICE_FAILURE
        try:
            for offset, value in enumerate(values):
                values[offset] = self.device.write(address + offset, int(value))
        except IllegalAddress:
            return ExcCodes.ILLEGAL_ADDRESS
        except DeviceFailure:
            return ExcCodes.DEVICE_FAILURE
        return None

    async def _stall(self, seconds: float) -> None:
        waiter = asyncio.get_running_loop().create_future()
        self._delays.add(waiter)
        try:
            await asyncio.wait_for(waiter, seconds)
        except (TimeoutError, asyncio.CancelledError):
            pass
        finally:
            self._delays.discard(waiter)

    # ---- context manager -----------------------------------------------------
    async def __aenter__(self) -> "HrdsSimServer":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()
