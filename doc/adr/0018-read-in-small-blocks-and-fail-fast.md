---
status: accepted
date: 2026-10-20
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/__init__.py"
  - "tests/diagnose_hrds.py"
  - "tests/sim/server.py"
---

# ADR-0018: Read in small blocks; fail the poll on a missing reply

## Decision

- The hub MUST read in blocks of at most `C_MAX_BLOCK` (10) registers,
  merging gaps up to `C_MAX_GAP` (8) (`_build_blocks`). A block MUST NOT
  span an address of the other function code, nor of a key not being read
  (installer menu, ADR-0017).
- A block the unit rejects (Modbus exception) MUST be retried register by
  register, so one bad address cannot blank every entity.
- A block with no reply, or a reply with the wrong register count, MUST fail
  the cycle and close the connection (`_read`): pymodbus hands a late answer
  to the next request, which then decodes another block's registers.
- If a block gets no reply while a single register at its start answers
  within `C_PROBE_MAX_SECONDS` (1.5 s), the hub MUST halve its cap for its
  lifetime (`_shrink_blocks`). A slow answer proves nothing (pymodbus' retry
  can pick up a late answer); a dead link fails the poll fast.
- MUST NOT raise `C_MAX_BLOCK` without a hardware read that proves the
  larger size works.
- `build_blocks` in `tests/diagnose_hrds.py` MUST stay in sync with
  `_build_blocks`.

## Context

The address space (0x0100–0x077A) is wide and sparse. A 120-register read
was never answered through the real RS-485→TCP gateway, while 10-register
reads covered the whole map (`UNIT_BEHAVIOUR.md` T9; 0.9.0 did not load).
A slow gateway once made a running unit read `off_by_display` because
replies were decoded against the wrong blocks.

## Consequences

- Good: works through the weakest gateway seen; never shows another
  register's value.
- Bad: about 34 requests per poll; the real limit is unknown
  (`plans/todo.md`).

## Confirmation

- `tests/ha/test_failures.py::test_gateway_that_drops_large_reads`
- `tests/ha/test_failures.py::test_dead_link_is_not_mistaken_for_a_size_limit`
- `tests/ha/test_failures.py::test_one_bad_address_does_not_blank_the_block`
- `tests/ha/test_failures.py::test_unanswered_requests_time_out`
- `tests/wiring_check.py` "input blocks must not span holding addresses"

## More information

`77f2aec` (no FC spanning, per-register fallback), PR #16 (late replies),
PR #28 (cap 10, adaptive halving).
