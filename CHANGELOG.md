# Changelog

## 0.1.0 — Initial scaffold

* Initial Home Assistant custom integration for the Innova DEH+ / hej.luft HRDS+
  dehumidifier over Modbus TCP.
* Composite **climate** entity (room temperature & humidity, HVAC action, HVAC
  mode → off / dehumidify / active cooling, target humidity & temperature).
* Sensors, binary sensors, switches and numbers generated from a single
  `ENTITIES_DICT` register table.
* Chunked block reads to cover the wide/sparse Modbus address space, and
  automatic enabling of "by BMS" control registers.
* Manufacturer PDFs and a distilled register reference added under
  `references/`.
* CI: Ruff lint/format, hassfest, and HACS validation workflows.

> Register addresses and scaling are taken from the manufacturer documentation
> and have not yet been verified against physical hardware.
