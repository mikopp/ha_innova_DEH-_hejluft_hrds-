---
status: accepted
date: 2026-10-19
decision-makers: mikopp
topics: [config, modbus-writes]
paths:
  - "custom_components/innova_hrds/identity.py"
  - "custom_components/innova_hrds/config_flow.py"
---

# ADR-0009: Verify the device is an HRDS+ before writing anything

## Decision

- `async_setup_entry` MUST call `identity.verify_device` before the first
  read cycle (whose headless sync may write), and the config and options
  flows MUST call it before saving a host, port or unit id.
- It MUST require FC 43/14 vendor `EVCO` (`EXPECTED_VENDOR`) and a product
  code starting `EPB9` (`EXPECTED_PRODUCT_PREFIX`), and the four status
  registers holding documented enum values. When the gateway does not
  forward FC 43, the register fingerprint alone decides.
- A wrong device MUST raise `ConfigEntryError` (flow error `wrong_device`);
  no answer MUST raise `ConfigEntryNotReady` (flow error `cannot_connect`).
- The identity feeds the device registry (`model_id`, `sw_version`).
- MUST NOT loosen the product prefix without a dump from another variant.

## Context

The integration writes configuration registers (ADR-0010) as soon as it
connects. A wrong IP or a wrong unit id behind a shared RS-485 gateway would
write them into another device. The reference unit reports `EVCO` /
`EPB9ORSINDEU` / `V01.00.09.02`; other variants are unconfirmed
(`plans/todo.md`).

## Consequences

- Good: no write ever reaches a foreign device.
- Bad: an HRDS+ variant with another product code is refused until the
  prefix is widened.

## Confirmation

- `tests/ha/test_config_flow.py::test_user_flow_wrong_vendor`
- `tests/ha/test_config_flow.py::test_user_flow_wrong_fingerprint_without_fc43`
- `tests/ha/test_config_flow.py::test_user_flow_without_fc43_uses_fingerprint`
- `tests/ha/test_config_flow.py::test_setup_fails_on_wrong_device`
- `tests/e2e/test_install_and_flow.py::test_flow_wrong_device`

## More information

PR #15, first bring-up on a real HRDS+ 30 R.
