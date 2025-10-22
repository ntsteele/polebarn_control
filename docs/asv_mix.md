# Augmented Soundguy View (Mix Coach v1)

The **Augmented Soundguy View (ASV)** provides a single surface to balance the show mix, monitor the crowd, and keep the system in a safe window. It leans on XR18 capabilities (6-band PEQ/TEQ, RTA pre/post switching) and the Polebarn control helpers to automate the repetitive work so the operator can focus on musical choices.

## Page layout

`/asv/mix` loads the current show, roster, and mode. The page contains:

* **Roster Selector** – choose one of the JSON show profiles from `shows/`. The profile defines the channels that appear in the fader lane and which outputs make up the front-of-house (FOH) group.
* **Mix Template Selector** – templates from `profiles/mix_templates/` define balance targets (`offset_db`) and pan hints for each channel role. These targets fuel the level coach suggestions and stage-map presets.
* **Mode Selector** – modes from `profiles/modes/` define safe SPL windows, attack/release, and maximum rate of change for the FOH virtual master.
* **Fader Lane** – one card per channel with XR18 fader and pan controls. Dragging the control writes directly to the mixer via OSC.
* **Pan Presets** – quick stage maps sourced from the active mix template. Applying a preset updates all visible channels.
* **Level Coach badges** – each channel badge shows a recommended ±dB nudge based on recent RMS readings compared with the template target. Clicking a badge applies the micro-move (max ±1.5 dB per action).
* **Beat + SPL Coach** – telemetry cards show short/long BPM, SPL fast/slow, iRig safety hints, and whether the master coach is nudging the FOH group.
* **Master Slider** – adjusts the virtual FOH master. The coach proportionally moves Main LR, Sub, and Rear buses to match the master target without consuming a DCA.

## Safety overlays and helpers

* The iRig Pro Duo input helper surfaces LED state reminders (green/amber = healthy, red = clipping) and the Direct Monitor caveat. Disable software monitoring if Direct Monitor is engaged to avoid a doubled feed.
* When the selected measurement mic profile lists the DBX RTA-M, ASV reminds the operator to enable +48 V phantom power on the XR18 preamp that feeds the mic (the capsule requires 9–52 V phantom).
* RTA overlays respect the XR18 pre/post EQ switch. When the RTA is pre-EQ the template plots show expected changes before the graphic/parametric filters; post-EQ shows the compensated TEQ response.

## Data files

* `profiles/mix_templates/*.json` – balance targets, stage maps, and descriptive text for the coach.
* `profiles/modes/*.json` – SPL safe windows and dynamics for the master coach.
* `shows/*.json` – nightly roster (channels + FOH members) and default mode/template for that show.

Each file is human-editable. Reloading the ASV page picks up new profiles without a server restart.

## OSC behavior

ASV uses `core.osc_client.XR18` helpers. New convenience methods handle pan and fader reads/writes for input channels as well as the FOH group members (Main LR, Aux/Sub, Rear). The FOH virtual master applies an offset (in dB) to each member before converting back to the XR18 linear fader scale and sending the update.

## Telemetry

`analysis/beat_spl.py` provides:

* `BeatTracker` – maintains a deque of onset timestamps, computes a short-window BPM, and keeps a long-term EMA that falls slowly once the band stops.
* `SPLTracker` – two-pole RMS tracker with fast (~125 ms) and slow (~1 s) time constants plus optional A-weighting.
* `MasterCoach` – PI-style controller that compares SPL to the active mode target. It returns gentle dB adjustments, rate-limited according to the mode config, and logs any overrides required to keep the crowd in the safe zone.

The background telemetry loop feeds measurements, updates recommendations, and emits live data over `ws://…/ws/asv`.

## XR18 feature reminders

* **Graphic vs. True EQ** – TEQ (true EQ) on the XR18 compensates for adjacent band interaction and represents the actual acoustic curve. ASV always references TEQ when plotting graphic moves.
* **RTA pre/post EQ** – the XR18 RTA can sit pre or post EQ. The overlays and guidance respect the current selection so the operator is always comparing the correct curve.

## Network guidance

When ASV surfaces XR18 connection helpers, it lists XR18 AP limitations (max four clients, WEP only, defaults to `192.168.1.1`) and recommends using LAN/Wi‑Fi client mode for reliability. Recovery tips follow the existing system guidance.

---

For deeper customization, extend the JSON profiles or drop in new ones, and the UI will populate the options automatically.
