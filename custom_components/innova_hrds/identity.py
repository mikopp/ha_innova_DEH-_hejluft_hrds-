"""Check that a Modbus endpoint really is an HRDS+ before we poll or write to it.

The integration writes configuration registers (PH01/PH02/PH27/PH28/HA00), so
pointing it at the wrong Modbus device - a heat pump, a meter, another slave id
on a shared gateway - would write into unrelated registers. Two independent
checks guard against that:

* FC 43/14 "Read Device Identification": the HRDS+ controller answers with
  vendor ``EVCO``, a product code starting ``EPB9`` and a firmware revision.
* A register fingerprint: the four status registers must hold values from the
  documented enums. A device that answers but is not an HRDS+ is very unlikely
  to satisfy all four.

If the gateway does not forward FC 43 the fingerprint alone decides.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import ModbusTcpClient

from .const import (
    C_COMPRESSOR_STATUS,
    C_MODE_STATUS,
    C_SUPPLY_FAN_STATUS,
    C_UNIT_STATUS,
    COMPRESSOR_STATUS,
    EXPECTED_PRODUCT_PREFIX,
    EXPECTED_VENDOR,
    FAN_STATUS,
    MODE_STATUS,
    UNIT_STATUS,
    get_entity_props,
    get_entity_reg,
)

_LOGGER = logging.getLogger(__name__)

# (entity key, documented values) - read via FC 04.
_FINGERPRINT = (
    (C_UNIT_STATUS, UNIT_STATUS),
    (C_MODE_STATUS, MODE_STATUS),
    (C_SUPPLY_FAN_STATUS, FAN_STATUS),
    (C_COMPRESSOR_STATUS, COMPRESSOR_STATUS),
)


class CannotConnect(Exception):
    """The gateway or the unit did not answer."""


class WrongDevice(Exception):
    """Something answered, but it is not an HRDS+."""


@dataclass(frozen=True)
class DeviceIdentity:
    """What the device told us about itself (all None if FC 43 is unsupported)."""

    vendor: Optional[str] = None
    product_code: Optional[str] = None
    revision: Optional[str] = None


def _read_fc43(client: ModbusTcpClient, unit: int) -> DeviceIdentity:
    """Return the FC 43/14 identification, or an empty identity if unsupported."""
    try:
        resp = client.read_device_information(read_code=1, device_id=unit)
    except Exception as exc:  # noqa: BLE001 - gateways reject this in many ways
        _LOGGER.debug("FC43 device identification not available: %r", exc)
        return DeviceIdentity()
    if resp is None or resp.isError():
        return DeviceIdentity()
    info = {
        int(k): (v.decode("latin-1", "replace") if isinstance(v, bytes) else str(v))
        for k, v in (getattr(resp, "information", None) or {}).items()
    }
    return DeviceIdentity(
        vendor=info.get(0), product_code=info.get(1), revision=info.get(2)
    )


def _fingerprint_matches(client: ModbusTcpClient, unit: int) -> bool:
    """True if all status registers decode to documented enum values."""
    for key, valid in _FINGERPRINT:
        reg = get_entity_reg(get_entity_props(key))[0]
        resp = client.read_input_registers(address=reg, count=1, device_id=unit)
        if resp is None or resp.isError() or not getattr(resp, "registers", None):
            return False
        if resp.registers[0] not in valid:
            return False
    return True


def verify_device(host: str, port: int, unit: int) -> DeviceIdentity:
    """Connect and confirm the endpoint is an HRDS+ (blocking: run in an executor).

    Raises ``CannotConnect`` if nothing usable answers and ``WrongDevice`` if
    something answers but fails the identity checks.
    """
    client = ModbusTcpClient(host=host, port=port, timeout=3, retries=1)
    try:
        if not client.connect():
            raise CannotConnect(f"cannot open {host}:{port}")
        status_reg = get_entity_reg(get_entity_props(C_UNIT_STATUS))[0]
        try:
            probe = client.read_input_registers(
                address=status_reg, count=1, device_id=unit
            )
        except Exception as exc:  # noqa: BLE001
            raise CannotConnect(f"no Modbus answer from unit id {unit}") from exc
        if probe is None or probe.isError():
            raise CannotConnect(f"no Modbus answer from unit id {unit}")

        identity = _read_fc43(client, unit)
        if identity.vendor is not None:
            vendor_ok = identity.vendor.strip().upper() == EXPECTED_VENDOR
            product_ok = (
                (identity.product_code or "")
                .upper()
                .startswith(EXPECTED_PRODUCT_PREFIX)
            )
            if not (vendor_ok and product_ok):
                raise WrongDevice(
                    f"identifies as {identity.vendor!r} {identity.product_code!r}, "
                    f"expected {EXPECTED_VENDOR!r} {EXPECTED_PRODUCT_PREFIX}*"
                )
        else:
            _LOGGER.warning(
                "%s:%s does not provide FC43 device identification; "
                "falling back to the register fingerprint only",
                host,
                port,
            )

        if not _fingerprint_matches(client, unit):
            raise WrongDevice("status registers do not look like an HRDS+")
        return identity
    finally:
        client.close()
