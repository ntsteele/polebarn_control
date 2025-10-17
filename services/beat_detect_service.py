#!/usr/bin/env python3
"""
beat_detect_xair_or_irig.py — Adaptive beat detection for Polebarn
Reads preferred input device (xr18 or irig_shared) from config.yaml
Outputs /tmp/polebarn_status/beat.json for diagnostics + automation.
"""

import os, sys, time, json, numpy as np, sounddevice as sd, yaml
from pathlib import Path
from collections import deque

# ───────────────────────────────────────────────
# Config
# ───────────────────────────────────────────────
CONFIG_PATH = "/home/pi/polebarn_control/config.yaml"
try:
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}
        DEVICE = cfg.get("audio", {}).get("beat_input", "xr18")
except Exception:
    DEVICE = "xr18"

SAMPLE_RATE = 48000
BLOCK_SIZE = 2048
ROLL_WINDOW = 40
THRESH_MULT = 1.6
MIN_INTERVAL = 0.25
SMOOTH_ALPHA = 0.2
DEBUG = True

TELEMETRY = Path("/tmp/polebarn_status")
TELEMETRY.mkdir(parents=True, exist_ok=True)
BEAT_FILE = TELEMETRY / "beat.json"

rms_hist = deque(maxlen=ROLL_WINDOW)
beat_times = deque(maxlen=10)
last_beat = 0.0
smooth_bpm = 0.0
smooth_intensity = 0.0

# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────
def write_telemetry(bpm, intensity):
    data = {
        "bpm": round(bpm, 1),
        "intensity": round(intensity * 100, 1),
        "timestamp": time.time()
    }
    BEAT_FILE.write_text(json.dumps(data))

def ema(old, new, alpha):
    return (alpha * new) + ((1 - alpha) * old)

# ───────────────────────────────────────────────
# Audio callback
# ───────────────────────────────────────────────
def callback(indata, frames, time_info, status):
    global last_beat, smooth_bpm, smooth_intensity

    mono = np.mean(indata, axis=1)
    rms = float(np.sqrt(np.mean(mono**2)))
    rms_hist.append(rms)

    avg_rms = np.mean(rms_hist) if rms_hist else 0.0
    threshold = avg_rms * THRESH_MULT if avg_rms > 0 else 0.001

    now = time.time()
    if rms > threshold and (now - last_beat) > MIN_INTERVAL:
        beat_times.append(now)
        last_beat = now

    if len(beat_times) > 2:
        intervals = np.diff(beat_times)
        inst_bpm = float(np.clip(60.0 / np.mean(intervals), 40, 180))
        smooth_bpm = ema(smooth_bpm, inst_bpm, SMOOTH_ALPHA)
    else:
        smooth_bpm = ema(smooth_bpm, 0.0, SMOOTH_ALPHA)

    inst_intensity = float(np.clip(rms / (avg_rms + 1e-9), 0, 2.0))
    normalized = np.interp(inst_intensity, [0, 2.0], [0, 1.0])
    smooth_intensity = ema(smooth_intensity, normalized, SMOOTH_ALPHA)
    write_telemetry(smooth_bpm, smooth_intensity)

    if DEBUG:
        sys.stdout.write(f"\r[BPM:{smooth_bpm:6.1f}] [Intensity:{smooth_intensity*100:5.1f}%]")
        sys.stdout.flush()

# ───────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[BeatDetect] Using ALSA device '{DEVICE}' @ {SAMPLE_RATE}Hz")

    try:
        with sd.InputStream(device=DEVICE, channels=1, samplerate=SAMPLE_RATE,
                            blocksize=BLOCK_SIZE, callback=callback):
            print("[BeatDetect] Running...")
            while True:
                time.sleep(0.05)
    except Exception as e:
        print(f"[BeatDetect] ERROR: {e}")
        while True:
            write_telemetry(0, 0)
            time.sleep(1)
