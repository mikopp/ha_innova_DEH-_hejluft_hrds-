# Security policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please do **not** open a public issue. Report it privately through
GitHub: **Security → Report a vulnerability** on this repository
(private vulnerability reporting). You will get an answer as soon as
possible; please allow time for a fix before disclosing it.

This integration talks Modbus TCP to the HRDS+ on the local network.
Modbus has no authentication, so anyone who can reach the unit's Modbus
port can control it regardless of this integration; keep that port on a
trusted network segment.
