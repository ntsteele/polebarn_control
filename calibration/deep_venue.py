#!/usr/bin/env python3
"""
deep_venue.py – Multi-pass Deep Venue Calibration
-------------------------------------------------
Plays 3 calibrated sweeps per speaker, verifies mic levels,
and saves averaged recordings for analysis.
"""

import os, time, json, math, numpy as np, sounddevice as sd
from datetime import datetime
from pathlib import Path

# ───────── CONFIG ─────────
SAMPLE_RATE = 48000
DURATION = 10.0          # seconds per sweep
START_GAIN = 0.025
MAX_GAIN = 0.05
TARGET_PEAK = 0.2
MIN_PEAK = 0.05
N_PASSES = 3

XR18_IP = "192.168.4.136"
DATA_ROOT = Path.home() / "polebarn_control" / "data"

# ───────── FUNCTIONS ─────────
def make_sweep(duration=DURATION, rate=SAMPLE_RATE):
    t = np.linspace(0, duration, int(rate * duration))
    sweep = np.sin(2 * np.pi * 20 * ((duration / np.log(20000/20)) *
             (np.exp(t * np.log(20000/20) / duration) - 1)))
    return sweep.astype(np.float32)

def record_pass(label, sig, gain, passnum):
    print(f"▶ {label} Pass {passnum+1}/{N_PASSES} @ gain={gain:.3f}")
    sd.play(sig * gain)
    rec = sd.rec(len(sig), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()
    peak = float(np.max(np.abs(rec)))
    return rec, peak

def calibrate_channel(label, sig):
    gain = START_GAIN
    all_passes, peaks = [], []
    for i in range(N_PASSES):
        rec, peak = record_pass(label, sig, gain, i)
        if peak < MIN_PEAK and gain * 1.4 <= MAX_GAIN:
            gain *= 1.4
            print(f"⚠️ Low mic level ({peak:.3f}), boosting gain to {gain:.3f}")
            continue
        all_passes.append(rec)
        peaks.append(peak)
        time.sleep(1.0)
    if not all_passes:
        raise RuntimeError(f"❌ No valid recordings for {label}")
    avg = np.mean(np.stack(all_passes), axis=0)
    return avg, peaks

# ───────── MAIN ─────────
def main():
    sweep = make_sweep()
    folder = DATA_ROOT / f"cal_{datetime.now():%Y%m%d_%H%M%S_Center}"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"🚀 Starting deep-venue calibration → {folder}")

    results = {}
    for label in ["MainL", "MainR", "Subwoofer"]:
        avg, peaks = calibrate_channel(label, sweep)
        np.save(folder / f"{label}_response.npy", avg)
        results[label] = {"peaks": peaks, "avg_peak": float(np.mean(peaks))}

    with open(folder / "summary.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Saved averaged responses + summary.json")

if __name__ == "__main__":
    main()
