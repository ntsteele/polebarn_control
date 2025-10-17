#!/usr/bin/env python3
"""
deep_venue_lockdown.py – Manual EQ Lockdown Mode
------------------------------------------------
Performs deep calibration recordings only.
No EQ or delay commands are sent to XR18 or QLC+.
Perfect for testing manual EQ baselines.
"""
import os, time, json, numpy as np, sounddevice as sd
from datetime import datetime
from pathlib import Path

SAMPLE_RATE = 48000
DURATION = 10.0
START_GAIN = 0.025
MAX_GAIN = 0.05
MIN_PEAK = 0.05
N_PASSES = 3
DATA_ROOT = Path.home() / "polebarn_control" / "data"

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
    avg = np.mean(np.stack(all_passes), axis=0)
    return avg, peaks

def main():
    sweep = make_sweep()
    folder = DATA_ROOT / f"lockdown_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"🔒 Starting lockdown calibration → {folder}")
    results = {}
    for label in ["MainL", "MainR", "Subwoofer"]:
        avg, peaks = calibrate_channel(label, sweep)
        np.save(folder / f"{label}_response.npy", avg)
        results[label] = {"peaks": peaks, "avg_peak": float(np.mean(peaks))}
    with open(folder / "summary.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n✅ Saved averaged responses (no EQ applied).")
    print("   Next step: run analyze_lockdown.py to plot results.\n")

if __name__ == "__main__":
    main()
