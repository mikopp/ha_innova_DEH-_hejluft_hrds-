# References — HRDS+ / Innova DEH+

Manufacturer documentation for the **hej.luft HRDS+** air-dehumidification
module for residential ventilation systems (OEM: **Innova DEH+**), plus the
repository's own distilled references.

## Which file answers what

Each topic has exactly one home. Other files link to it instead of repeating
it.

| Topic | File |
|-------|------|
| **How the unit behaves**: variants, states, start/stop sequences, summer/winter, display/probe configurations, fan, compressor, water circuit, alarm effects, display and Modbus actions, what was tested on real hardware | [`UNIT_BEHAVIOUR.md`](UNIT_BEHAVIOUR.md) |
| **Which registers exist**: addresses, names, encodings, ranges, value meanings, write recipes | [`MODBUS_REGISTERS.md`](MODBUS_REGISTERS.md) |
| Technical data (airflow, capacity, power) and the fan-speed → airflow estimate | this file, below |
| What the Home Assistant integration does on top of the unit | [`../CLAUDE.md`](../CLAUDE.md) (agents), [`../README.md`](../README.md) (users) |
| Open hardware questions and test plans | [`../plans/todo.md`](../plans/todo.md) |

## Source documents

| File | What it is | Cited as |
|------|------------|----------|
| [HRDS+_Technisches_Handbuch_DE.pdf](HRDS+_Technisches_Handbuch_DE.pdf) | Technical handbook — installation, operation, control logic (§6), alarms, technical data (German, 87 pp). | `HB §n` |
| [HRDS+_Technisches_Handbuch_DE.txt](HRDS+_Technisches_Handbuch_DE.txt) | Full text of the handbook, for searching. Tables are flattened; check the PDF for column alignment. | `HB §n` |
| [HRDS+_Modbus_RTU_RS485_DE.pdf](HRDS+_Modbus_RTU_RS485_DE.pdf) | Modbus RTU/RS-485 connection and register manual (German). Source of every register address. | `MB p.n` |
| [HRDS+_Benutzerhandbuch_DE.pdf](HRDS+_Benutzerhandbuch_DE.pdf) | End-user handbook (German, 12 pp); a subset of the technical handbook. | `HB` |
| [Innova_DEH+_H_Installation_Manual_EN.txt](Innova_DEH+_H_Installation_Manual_EN.txt) | Innova DEH+ H installation manual (English), the OEM original. Describes an **older controller** (microswitches, three fixed fan speeds), not the EVCO "K" board of the HRDS+. | `IM` |

The vendor's and other users' statements from the energiesparhaus.at HRDS+
forum thread are quoted with their post numbers in
[`UNIT_BEHAVIOUR.md` §13](UNIT_BEHAVIOUR.md#13-evidence-log-what-was-seen-on-real-hardware).

## Technical data (airflow, capacity, power)

From the technical handbook §10, p.77 ("Leistungsdaten Luftaufbereitung" /
"Elektrische Daten"). The two columns are the **30** and **50** variants.

| Spec | HRDS+ 30 | HRDS+ 50 |
|------|---------:|---------:|
| **Nominal total airflow (supply + recirc)** | **300 m³/h** | **500 m³/h** |
| External share (supply from the MVHR) | 0–300 m³/h | 0–500 m³/h |
| **Recirculation share (room air via own fan)** | **130–300 m³/h** | **190–500 m³/h** |
| Register-pack pressure drop @ nominal | 31 Pa | 38 Pa |
| Usable dehumidification capacity ¹ | 56 L/24h | 89 L/24h |
| Total cooling capacity ¹ | 2.59 kW | 3.95 kW |
| Compressor frequency range | 23–63 Hz | 23–78 Hz |
| **Max. electrical power (operating)** | **820 W** | **1130 W** |
| — compressor nominal | 690 W | 950 W |
| — **recirc fan nominal** | **120 W** | **170 W** |
| Sound pressure @ 3 m | 39.5 dB(A) | 40.8 dB(A) |
| Weight (with recirc / without) | 46 / 43 kg | 57 / 54 kg |

¹ At nominal airflow and the reference conditions footnoted in the handbook.

The handbook table prints the pressure drop as kPa; its curve (§10.3.1, p.80)
shows about 31 Pa at 300 m³/h and 38 Pa at 500 m³/h, so the unit is Pa.

The 130–300 / 190–500 m³/h recirculation band is the **tested operating
range** from the performance spec, not a firmware floor: the fan minimum during
dehumidification and integration is `PF28` / `PF27`, factory 50 %, settable
down to 0 % (HB §5.3, §6.2). The total flow (supply + recirc) should not exceed
the nominal 300 / 500 m³/h; above it efficiency drops, noise rises and the
supply ducts must be sized for it (HB §3.7.1, p.24).

### Dehumidification capacity vs. airflow

From the per-flow performance tables (HB p.78 / p.79, reference inlet
conditions):

| Airflow | HRDS+ 30 dehum. | HRDS+ 50 dehum. |
|--------:|----------------:|----------------:|
| 150 m³/h | 31.2 L/d | — |
| 200 m³/h | 41.1 L/d | 42.6 L/d |
| 250 m³/h | 50.7 L/d | — |
| 300 m³/h | 54.4 L/d | 62.4 L/d |
| 400 m³/h | — | 81.1 L/d |
| 500 m³/h | — | 83.2 L/d |

## Translating fan speed (% / RPM) to airflow (m³/h)

The unit has **no airflow register**; it cannot measure its own m³/h. It
reports the fan's analog output `outAO_SupplyFan` (639, %) and its speed
`actRPMsupplyFan` (1117, rpm) (MB p.8, p.15).

The handbook's performance curves (§10.3, p.80–81) are pressure-vs-flow system
curves, not an RPM-vs-flow table, so there is no published conversion. An
estimate with the **fan affinity law** (for a centrifugal EC fan on a fixed
duct, flow is proportional to speed, `Q ∝ N`) [our derivation, not from the
handbook]:

```
m³/h  ≈  (RPM / RPM_max) × Q_max  ≈  (output% / 100) × Q_max
```

* `Q_max` = the variant's recirculation maximum, 300 (HRDS+ 30) / 500 (HRDS+ 50).
* `RPM_max` = the speed at 100 % output; not published, calibrate once.
* When the fan is off (`SupplyFan_Status` reads OFF), its share is 0 m³/h;
  only the MVHR's passive flow passes, which the unit cannot see.

Accuracy: the affinity law only holds at constant duct resistance. A loaded
filter or long, narrow ducts move less air at the same speed (see the
available-pressure curves, p.81). For better accuracy, fit a line through two
known balanced flows from the MVHR commissioning report. Treat the result as
indicative, not metered.
