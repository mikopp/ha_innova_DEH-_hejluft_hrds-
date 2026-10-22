---
paths:
  - "CHANGELOG.md"
---

# Writing a CHANGELOG entry

Decision behind this: ADR-0032. The release notes are cut from this file by
`scripts/release.py notes`, so write each entry as a release note.

1. Add to `## Unreleased`, the first section. Create it (above the newest
   version, followed by `---`) if it is missing. Never write a version
   heading and never change the version in `manifest.json` or the README
   banners: `scripts/release.py` does that at release time (ADR-0031).
2. Use only these subsections, in this order, and leave out empty ones:

   ```
   ### ⚠️ Breaking changes       what a user must do after updating
   ### ✨ Highlights             new things a user notices
   ### 🛠️ Fixes and other changes
   ### 📚 Documentation
   ### 🧪 Tests and CI
   ```

   Breaking, Highlights and Fixes go into the release notes verbatim;
   Documentation and Tests and CI are folded under a `<details>` block.
3. One bullet per change, written for a user, not a developer:
   * a **bold lead sentence** saying what changed for them;
   * then at most two lines of why or how;
   * sub-bullets only for steps the user must take;
   * renamed entity ids as an `| Old | New |` table under Breaking, with
     "update automations, scripts and dashboards";
   * register numbers, test names and internals go under Documentation or
     Tests and CI, or into the PR, not into Highlights.
4. A change already listed in Unreleased: edit that bullet instead of adding
   a second one.
5. Check: `python3 scripts/release.py check` (runs in lint).

Example (from the v0.9.3 notes):

```
### ⚠️ Breaking changes

- **The Modbus enables are now yours.** PH02, PH28 and PH27 are no longer
  written at setup, so an enable you switch off stays off.
  - To control the unit, turn on the enables you need on the setup device,
    then *Allow operational requests* (README setup step 4).

### ✨ Highlights

- **New: Auto mode.** Offered when a display or room probe can start
  requests by itself; the unit then regulates on its own setpoints.
```
