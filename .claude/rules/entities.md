---
paths:
  - "custom_components/innova_hrds/const.py"
  - "custom_components/innova_hrds/installer_params.py"
  - "custom_components/innova_hrds/translations/*.json"
---

# Adding or changing an entity

Decision behind this: ADR-0002. Steps:

1. Add or edit the entry in `ENTITIES_DICT` (`const.py`).
2. Fields: `RT` (register type), `REG` (decimal PDU address), `DT`
   (`C_DT_INT16` / `C_DT_UINT16`), `NAME`; optional `UNIT`, `FAKTOR`, `MIN`,
   `MAX`, `STEP`, `VALUES` (enum/select), `DEFAULT` (select raw default),
   `DC` (device class overriding the `UNIT` default), `SWITCH` (0/1 flag),
   `BITMASK` / `BITMASK_INVERT`, `PF` (platform override), `RW: 0` (holding
   register shown read-only).
3. Scaling: temperatures and setpoints ×0.1, fan / percent ×0.01, humidity ×1.
4. Add `en` and `de` translations under the platform key (and `state` slugs
   for enums).
5. Put the key in at most one of `SETUP_KEYS`, `CONFIG_KEYS`,
   `DIAGNOSTIC_KEYS` (ADR-0016); a fan-only key also in `FAN_KEYS`. The
   choice decides the device and section in the entity reference.
6. Document the register in `doc/references/MODBUS_REGISTERS.md`.
7. List the entity in `doc/entity-reference.md`, in the device section and group
   from step 5 (ADR-0030); installer parameters are the exception. Say why a
   new device or group exists.
8. Run `python3 tests/wiring_check.py`; if entities change, update the
   snapshots (`tests/CLAUDE.md`).

Renaming a key: ADR-0026. Installer parameters are rows in
`installer_params.py`, not `ENTITIES_DICT` entries (ADR-0017).

## Classification (`_classify`)

| Register type | Shape | Entity |
|---|---|---|
| input (R/O) | plain numeric | sensor |
| input (R/O) | `VALUES` | enum sensor |
| input (R/O) | `SWITCH` | binary_sensor |
| holding (R/W) | `SWITCH` | switch |
| holding (R/W) | `VALUES` | select |
| holding (R/W) | temperature unit, no `PF` | climate (avoid: set `PF=Platform.NUMBER`) |
| holding (R/W) | otherwise | number |

## Bits of packed registers

`BITMASK: N` extracts bit N (0-based); combine with
`SWITCH: {"off": 0, "on": 1}`. Without `BITMASK_INVERT` a set bit is `on`
(alarms); with it a set bit is `off` ("probe OK" sensors).

* `PackedAlarm_1` (768): bit N = AL(N+1), e.g. AL11 = bit 10, AL16 = bit 15.
* `PackedAlarm_2` (769): bit N = AL(N+17), e.g. AL22 = bit 5, AL28 = bit 11.
* `PackedAlarm_3` (770): bit 0 = AL33, bit 1 = AL34, bit 2 = AL35, bit 6 = AL39.

## Computed values

Not register-backed: `COMPUTED_SENSORS` / `COMPUTED_BINARY_SENSORS` (key,
`NAME`, `UNIT` or `OPTIONS`/`DC`); the hub writes them in
`_compute_derived()`. Pattern: the airflow sensors.
