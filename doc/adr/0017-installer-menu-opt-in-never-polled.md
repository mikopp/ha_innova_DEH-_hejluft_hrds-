---
status: accepted
date: 2026-10-20
decision-makers: mikopp
paths:
  - "custom_components/innova_hrds/installer_params.py"
  - "custom_components/innova_hrds/button.py"
  - "custom_components/innova_hrds/__init__.py"
  - "custom_components/innova_hrds/const.py"
---

# ADR-0017: The installer menu is opt-in, never polled, and never dangerous

## Decision

- The installer device MUST be opt-in: option `installer_device`, default
  off, offered only in the options flow. Turning it off MUST remove the
  device and its entities.
- Installer registers (`INSTALLER_KEYS`) MUST NOT be part of the regular
  poll (`_poll_keys`), and no poll block may span one. They are read at
  setup, on `button.refresh_installer`, and one register after its write;
  `sensor.installer_last_read` shows when. With the option off only
  `INSTALLER_LOGIC_KEYS` (PC07, PC08, PU08, PF12, PH09, PH10) are read, once
  at setup.
- MUST NOT expose passwords (PSd*), PH15 (restore factory defaults) or PH18
  (clear alarm history). Link settings, I/O allocation, PE05 and test mode
  MUST be read-only. MUST NOT add registers above 1900.
- Rows live in `installer_params.py` (code, register, kind n/s/r, scale,
  range, unit, en/de name, enabled by default); translations are generated
  from them and `MODBUS_REGISTERS.md` §16 lists them.

## Context

0.9.0 never loaded on a real unit: ~240 installer registers made the poll
read 120-register blocks the gateway never answered (PR #28). Changing link
settings cuts the connection; the excluded parameters are destructive.
Registers above 1900 are unverified, and one bad address forces a block onto
the per-register fallback.

## Consequences

- Good: the poll stays small; nothing destructive is one click away.
- Bad: installer values are as old as their last read.

## Confirmation

- `tests/ha/test_installer.py::test_off_by_default_and_not_offered_at_first_install`
- `tests/ha/test_installer.py::test_regular_poll_never_reads_installer_registers`
- `tests/ha/test_installer.py::test_write_reads_back_only_that_register`

```sh
! grep -E '\("(PSd[0-9]*|PH15|PH18)",' custom_components/innova_hrds/installer_params.py
! grep -E '\("(PE05|PT[0-9]+)", [0-9]+, "[ns]"' custom_components/innova_hrds/installer_params.py
python3 -c "import re,sys; t=open('custom_components/innova_hrds/installer_params.py').read(); sys.exit(any(int(r)>1900 for r in re.findall(r'\(\"\w+\", (\d+), \"[nsr]\"', t)))"
```

## More information

PR #15 (installer device), PR #28 (opt-in, never polled), PR #37 (PF12,
PH09, PH10 as logic keys).
