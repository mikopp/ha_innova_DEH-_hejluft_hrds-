# Repository settings

GitHub settings that are not files. Check the live state with
`gh api repos/mikopp/homeassistant-innova-hrds/rulesets` before relying on
this page; it can go stale.

## About panel (discoverability)

* Description: `Home Assistant (HACS) integration for the hej.luft HRDS+ and Innova
  DEH+ dehumidifiers: local control and monitoring over Modbus TCP, no cloud`
* Topics (20 is the GitHub maximum): `dehumidifier`, `dehumidifiers`,
  `hacs-integration`, `hacs`, `hejluft`, `home-assistant`, `homeassistant`,
  `homeassistant-custom-component`, `custom-component`, `hrds`, `hvac`, `innova`,
  `innova-deh`, `modbus`, `modbus-tcp`, `taupunktentfeuchtung`, `entfeuchter`,
  `radiant-cooling`, `vmc`, `hej-luft`.
* Optional: a social preview image (Settings -> General).

## Ruleset on the default branch (Settings -> Rules -> Rulesets)

* Enforcement active; target the default branch.
* Require a pull request (0 approvals; the owner merges their own), squash
  merge only.
* Require the checks `ruff`, `hassfest`, `hacs`, `pytest`, `e2e (pinned)`.
* Block force pushes and deletion.
* Bypass: the Repository admin role only, in mode **pull request** (never
  "always", so no direct pushes).
* Do **not** add "Restrict updates": a merge is an update, so it forces a
  bypass on every merge.

## Ruleset on tags

* Target `refs/tags/v*`; "Restrict creations/updates/deletions" (publishing a
  release creates its tag). Bypass: Repository admin role only.
* Do not turn on "Immutable releases": `package` uploads the zip after the
  release is published.

## Who can merge or release

* Only people with write access can merge, so keep the owner the sole
  collaborator with write.
* Never add an app to any bypass list.
* Dependabot has no merge path (no auto-merge workflow, read-only token).
* A ruleset cannot stop the Claude app from merging a green PR without a
  bypass list; limit its installation to this repo.

## Actions (Settings -> Actions -> General)

* Workflow permissions "read"; approve fork PR workflows manually.
