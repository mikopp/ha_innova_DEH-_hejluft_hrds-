# tests/ha: the default place for tests

The real Home Assistant core inside pytest, the integration's real pymodbus
client, and the simulated unit on a real TCP socket (`127.0.0.1`). Read
`../CLAUDE.md` first. If a check can be done here, it belongs here.

## Fixtures (`conftest.py`)
* `sim` / `sim_options`: a running simulator; override `sim_options` per
  module to choose seed and overlays, `entry_options` for the config entry.
* `setup`: a loaded entry (`Setup` helper: `entity_id`, `state`, `service`,
  `device` for the unit's registers and write log). `add_entry` when a test
  must set the entry up itself or unload it.
* `clock`: moves HA's timers without freezing real time (the sync Modbus client
  needs the real clock). `clock.poll()` is one scan interval, `clock.settle()`
  the debounced refresh after a write, `clock.advance(s)` anything else.
* `snapshot`: defined here on purpose. pytest-homeassistant-custom-component
  and syrupy both provide it and whichever loads last wins, which differs
  between machines (on GitHub's runner syrupy's plain version looked in
  `__snapshots__`). A conftest fixture beats both.
* `_no_ha_deprecations` (autouse): fails a test during which HA logs a
  deprecation naming this integration.

## Restarts
`test_restart.py` unloads and sets up the entry again (`restart()`); put
Home Assistant's last-state data in place *between* unload and setup
(`restart(..., restore={entity_id: state})`), never before the unload.
That a restart really restores from disk is `../e2e/test_restart.py`.

## Conventions
* One behaviour per test; assert what the unit received with
  `s.device.write_log`, not only what HA shows.
* A new scenario that is also user-visible does **not** get an e2e copy.
* Changing entities or states: update the snapshots
  (`pytest tests/ha/test_seeds.py --snapshot-update`) and read the diff.
