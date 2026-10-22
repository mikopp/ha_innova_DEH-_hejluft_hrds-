# Innova DEH+ / hej.luft HRDS+ — Home-Assistant-Integration

[![Release](https://img.shields.io/github/v/release/mikopp/homeassistant-innova-hrds)](https://github.com/mikopp/homeassistant-innova-hrds/releases)
[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)
[![HACS](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/hacs.yaml/badge.svg)](https://github.com/mikopp/homeassistant-innova-hrds/actions/workflows/hacs.yaml)

[![Dieses Repository in HACS öffnen.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mikopp&repository=homeassistant-innova-hrds&category=integration)

**Deutsch** · [English](README.md) (vollständige Dokumentation)

Diese Seite ist eine **Kurzfassung auf Deutsch**: Einleitung, Geräte,
Schnellstart und Funktionsumfang. Alles Weitere steht im
[englischen README](README.md); das Inhaltsverzeichnis unten verweist auf jeden
Abschnitt dort, damit Sie alles finden.

Home-Assistant-Integration (per **HACS** installierbar) für die
Entfeuchter **hej.luft HRDS+ 30 / 50** (auch HRDS 30 / HRDS 50 geschrieben)
und **Innova DEH+ 30 / 50** (auch DEH 30 / DEH 50): Taupunktentfeuchtung mit
Lüftung und Flächenkühlung. Die Integration steuert und überwacht das Gerät
**lokal über Modbus TCP, ganz ohne Cloud**.

## Kompatible Geräte

Das Gerät wird von **[INNOVA S.r.l.](https://www.innova.it/)** (Storo, Italien)
hergestellt. hej.luft verkauft es in Österreich unter eigenem Namen als
OEM-Produkt. Die
[CE-Konformitätserklärung auf der hej.luft-Seite](https://www.hejluft.at/_files/ugd/714411_e735ab85400c485fa7c042fac92d3230.pdf)
nennt Innova als Hersteller der Entfeuchtungsgeräte HRDS und HRDS+.

* **[hej.luft HRDS+ 30 / HRDS+ 50](https://www.hejluft.at/hrds)** (auch HRDS 30 / 50
  geschrieben), mit den Typenschild-Codes aus dem
  [Technischen Handbuch](https://www.hejluft.at/_files/ugd/714411_f1ffc5d222f4476da2e37f29c64a7f93.pdf),
  zum Beispiel *HRDS+ 30 H R K DC*.
* **[Innova DEH+ 30 H / 50 H](https://www.innova.it/en/products/vmc/dehumidifiers/deh-ad-incasso-orizzontale/)**:
  Innovas eigener Name für dasselbe Gerät, mit denselben Größen und demselben
  Nenn-Luftdurchsatz (300 / 500 m³/h). hej.luft baut oder verändert es nicht:
  das HRDS+ 30 des Maintainers wurde direkt aus Italien geliefert und ist
  physisch dasselbe Gerät wie das DEH+ 30 H; die Integration wurde damit
  entwickelt. Die 50er-Größen sind nicht getestet (siehe Beta-Hinweis). Die in
  `doc/references/` abgelegte DEH+-Installationsanleitung beschreibt die ältere
  Steuerung mit Mikroschaltern, nicht die EVCO-„K“-Platine des HRDS+; Register
  und Verhalten stammen aus den HRDS+-Handbüchern.

> *Wird Ihr Gerät mit der Innova-Platine unter einem anderen Namen verkauft,
> eröffnen Sie ein Issue und verlinken Sie die Produktseite.*

## Release 0.9.4: Beta, noch nicht 1.0

Die Integration ist veröffentlicht und nutzbar, aber eine **Beta**.

* **Entwickelt und getestet** wurde sie nur mit **einem HRDS+ 30 mit Umluft
  (`R`-Variante)**, ohne Display und ohne externe Fühler, hinter einem
  Modbus-RTU-zu-TCP-Gateway, im Solekreis einer Erdwärmepumpe. Welche Geräte und
  Installationen bekanntermaßen funktionieren und was jeweils beobachtet wurde:
  [Getestete Geräte und Installationen](doc/tested-setups.md) (EN).
* **Auf echter Hardware nicht getestet:** das HRDS+ 50, Geräte ohne Umluft,
  Geräte mit Display oder Fühlern (automatische Sollwertregelung), Winterbetrieb
  und Freikühlung. Auch wie die manuelle Lüfterstufe zur tatsächlichen
  Lüfterleistung passt, ist noch nicht geprüft. Offene Punkte:
  [`plans/todo.md`](plans/todo.md).
* **Der Klima-Modus *Auto* ist nicht an echter Hardware getestet.** Er erscheint
  nur mit Display oder Raumfühler; die CI prüft ihn gegen ein simuliertes
  Display-Gerät.

Berichte von anderen Geräten sind sehr willkommen, siehe
[Reporting issues](README.md#reporting-issues) (EN). Der Weg zu 1.0:
[Road to 1.0](README.md#road-to-10) (EN). Details: der
[englische Abschnitt](README.md#release-094--beta-not-10-yet).

## Schnellstart

Die Einzelheiten stehen im englischen README; die Links führen dorthin.

1. **[Installieren](README.md#1-install)** (EN): die Integration mit HACS
   installieren und Home Assistant neu starten.
2. **[Hinzufügen](README.md#2-add-the-integration)** (EN) unter
   *Einstellungen → Geräte & Dienste*, mit der Adresse Ihres Modbus-TCP-Gateways.
3. **[Einrichtung prüfen](README.md#3-check-the-setup)** (EN): das Gerät
   **HRDS+ setup** öffnen und sicherstellen, dass **Setup check** den Wert `ok`
   zeigt.
4. **[Festlegen, was Home Assistant steuern darf](README.md#4-choose-what-home-assistant-may-control)** (EN):
   die **Modbus-Freigaben** für die gewünschten Funktionen einschalten (Ein/Aus,
   Entfeuchten, Integration) und danach **Allow operational requests**. Beides
   ist nach einer Neuinstallation **aus**, und die Integration schaltet sie nie
   von selbst ein. Ohne sie beobachtet die Integration nur: Messwerte und
   Einstellungen funktionieren.
5. **[Wie das Gerät arbeitet](README.md#how-the-unit-works)** (EN): die
   Betriebsarten, einschließlich des passiven Kaltwasserbetriebs, und wie man
   sie bedient.

## Was die Integration kann

Sie spricht über Modbus TCP mit der Steuerplatine des Geräts und stellt bereit:

* **Klima-Entität** mit Raumtemperatur und -feuchte, der aktuellen Aktion
  (aus / Leerlauf / Lüfter / Entfeuchten / Kühlen / Heizen) und einem
  einstellbaren Modus: **Aus**, **Standby** (nichts angefordert),
  **Entfeuchten**, **Kühlen** (Sommer), **Heizen** (Winter, nur wenn in den
  Optionen erlaubt, nie bei Sole) und, nur mit Display oder Raumfühler,
  **Auto**. Beim `R`-Gerät auch die Lüfterstufe.
* **Sensoren, Binärsensoren, Schalter, Zahlen und Auswahlfelder**: Messwerte,
  Betriebszustand, Alarme, Anforderungen (Entfeuchten, Integration), Sollwerte
  und Lüfterbänder, Saison.
* **Lüfter** (nur `R`-Variante): der Zuluft-/Umluftlüfter als Prozentwert.
* **Wasserkreis-Diagnose**: Ventil/Pumpe, Kondensatorventil, Wasseralarme und
  eine Zusammenfassung *Water circuit check* (nur lesend, das Gerät steuert
  seinen Wasserkreis selbst).
* **Setup-Gerät** mit einer Einrichtungsprüfung und den Freigaben, und auf
  Wunsch ein **Installateur-Gerät** mit dem gesamten Installateurmenü
  (rund 240 Parameter, standardmäßig aus).

Jede Entität steht, nach Gerät gegliedert und mit Begründung, in der
**[Entitätsreferenz](doc/entity-reference.md)** (Englisch). Wie sich das Gerät
selbst verhält und was auf echter Hardware getestet wurde, steht in
[`doc/references/UNIT_BEHAVIOUR.md`](doc/references/UNIT_BEHAVIOUR.md) (Englisch).

## Inhaltsverzeichnis des englischen README

Die Abschnitte sind auf Englisch (EN); die deutsche Zeile nennt, was dort
steht.

* [Install and set up](README.md#install-and-set-up) (EN): Installation und Einrichtung
  * [Before you start](README.md#before-you-start) (EN): Was Sie brauchen (Gerät, Gateway, Adresse)
  * [1. Install](README.md#1-install) (EN): Installation mit HACS
    * [HACS (custom repository)](README.md#hacs-custom-repository) (EN): HACS als benutzerdefiniertes Repository
    * [Manual](README.md#manual) (EN): Manuelle Installation
  * [2. Add the integration](README.md#2-add-the-integration) (EN): Integration hinzufügen (Modbus-TCP-Adresse)
  * [3. Check the setup](README.md#3-check-the-setup) (EN): Einrichtung prüfen (Setup-Check)
    * [First-use checklist](README.md#first-use-checklist) (EN): Checkliste für die erste Benutzung
  * [4. Choose what Home Assistant may control](README.md#4-choose-what-home-assistant-may-control) (EN): Festlegen, was Home Assistant steuern darf
    * [Which enable gives which function](README.md#which-enable-gives-which-function) (EN): Welche Freigabe welche Funktion bringt
    * [Allow operational requests](README.md#allow-operational-requests) (EN): Betriebsanforderungen erlauben
  * [5. First run](README.md#5-first-run) (EN): Erster Betrieb
  * [Airflow calibration (Options)](README.md#airflow-calibration-options) (EN): Luftmengen-Kalibrierung (Optionen)
* [How the unit works](README.md#how-the-unit-works) (EN): Wie das Gerät arbeitet
  * [What is inside](README.md#what-is-inside) (EN): Aufbau des Geräts
  * [Two requests](README.md#two-requests) (EN): Die zwei Anforderungen (DEU und INT)
  * [Operating modes in summer](README.md#operating-modes-in-summer) (EN): Betriebsarten im Sommer
  * [Operating modes in winter](README.md#operating-modes-in-winter) (EN): Betriebsarten im Winter
  * [How to use it](README.md#how-to-use-it) (EN): Bedienung
* [Using the integration](README.md#using-the-integration) (EN): Die Integration nutzen
  * [Season and winter heating](README.md#season-and-winter-heating) (EN): Saison und Winterbetrieb (Heizen)
  * [The unit heats on its own](README.md#the-unit-heats-on-its-own) (EN): Das Gerät heizt von selbst
  * [Water circuit and brine](README.md#water-circuit-and-brine) (EN): Wasserkreis und Sole
    * [Brine temperature guard](README.md#brine-temperature-guard) (EN): Solewächter (Temperaturschutz)
  * [Setting target humidity and target temperature](README.md#setting-target-humidity-and-target-temperature) (EN): Soll-Feuchte und Soll-Temperatur einstellen
  * [Fan mode and recirculation](README.md#fan-mode-and-recirculation) (EN): Lüfterstufe und Umluft
  * [Drying with the fan on, but active cooling off](README.md#drying-with-the-fan-on-but-active-cooling-off) (EN): Entfeuchten mit Lüfter, ohne aktive Kühlung
  * [Airflow sensors](README.md#airflow-sensors) (EN): Luftmengen-Sensoren
  * [Commanded vs actual fan speed](README.md#commanded-vs-actual-fan-speed) (EN): Vorgegebene und tatsächliche Lüfterdrehzahl
* [Entity reference](doc/entity-reference.md) (EN): Alle Entitäten, nach Gerät gegliedert (eigene Datei)
* [Probe requirements](README.md#probe-requirements) (EN): Anforderungen an Temperatur- und Feuchtefühler
* [Requirements](README.md#requirements) (EN): Mindestversionen (Home Assistant, pymodbus)
  * [Availability](README.md#availability) (EN): Verhalten bei Ausfall: Entitäten werden „nicht verfügbar“
* [Disclaimer](README.md#disclaimer) (EN): Haftungsausschluss
* [Reporting issues](README.md#reporting-issues) (EN): Fehler und Testberichte melden
* [Road to 1.0](README.md#road-to-10) (EN): Weg zu Version 1.0
* [Design decisions](README.md#design-decisions) (EN): Architekturentscheidungen (ADRs)
* [Credits](README.md#credits) (EN): Quellen und Danksagung

Weitere Dokumente (Englisch):
[Modbus-Register](doc/references/MODBUS_REGISTERS.md),
[Verhalten des Geräts](doc/references/UNIT_BEHAVIOUR.md),
[Entitätsreferenz](doc/entity-reference.md),
[getestete Geräte und Installationen](doc/tested-setups.md),
[Architekturentscheidungen](doc/adr/README.md),
[Änderungsprotokoll](CHANGELOG.md).
