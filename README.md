# Polebarn Control

Polebarn Control bundles the web UI and automation tooling that runs on
the Raspberry Pi 5 based rig.  The Flask app can be launched locally for
UI development or remote management.

## Calibration Page

* Navigate to `/calibration` to open the Calibration Center.  The page
  hosts quick gain trim, routine calibration summaries, EQ preset tools,
  and the deep venue analysis viewer.
* **Quick Gain Trim** simulates the live calibration worker.  Select the
  channels, target level, and safety cap before pressing **Start**.
  Real-time logs stream into the page via Socket.IO, and a per-channel
  table reports the most recent peak values.  Use **Stop** to cancel the
  worker and **Save Log** to download the most recent log file.
* **Calibration Routines** shows the last recorded value for each
  routine (Mic Gain Adjuster, Mic dB Calibration, Venue dB Level Setting,
  and Venue Deep Calibration).  Press **Rerun** to launch a simulated run
  for any routine.
* **EQ Adjust / Presets** reads the current XR18 EQ snapshot and lets you
  preview the house/flat/speech/dj presets.  To apply changes for real,
  type `APPLY` into the confirmation field and press **Apply**.  Use the
  **Dry Run** button to preview the results without mutating the mixer
  state, and **Rollback** to restore the most recent snapshot.
* **Deep Venue Analysis Viewer** loads any saved `calibration/venue_*.json`
  files and renders their contents directly in the browser.

## Development Shortcuts

* `make dev` — run the Flask development server on port 5050.
* `make test` — execute the pytest suite.
* `make lint` — run `ruff check` when available.
