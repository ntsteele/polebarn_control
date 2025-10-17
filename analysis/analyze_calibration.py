#!/usr/bin/env python3
"""
analyze_calibration.py – Multi-pass Analyzer
--------------------------------------------
Performs FFT analysis, evaluates consistency, and outputs EQ suggestions.
"""

import numpy as np, json, matplotlib.pyplot as plt
from pathlib import Path

DATA_ROOT = Path.home() / "polebarn_control" / "data"
MIN_CONFIDENCE = 80.0  # percent threshold

def latest_folder():
    return sorted(DATA_ROOT.glob("cal_*"), key=lambda p: p.stat().st_mtime)[-1]

def fft_db(signal, fs=48000):
    spec = np.fft.rfft(signal.flatten())
    mag = 20*np.log10(np.abs(spec) + 1e-10)
    freq = np.fft.rfftfreq(len(signal), 1/fs)
    return freq, mag

def analyze_channel(label, sig):
    freq, mag = fft_db(sig)
    mag_smooth = np.convolve(mag, np.ones(32)/32, mode="same")
    low = np.mean(mag_smooth[(freq>40)&(freq<120)])
    high = np.mean(mag_smooth[(freq>4000)&(freq<10000)])
    bass_adj = (high - low)/5
    confidence = 100 - np.std(mag_smooth[(freq>100)&(freq<10000)])*0.2
    return {"freq": freq.tolist(), "mag": mag_smooth.tolist(),
            "bass_adj": bass_adj, "confidence": confidence}

def analyze():
    folder = latest_folder()
    results, plots = {}, {}
    for label in ["MainL","MainR","Subwoofer"]:
        sig = np.load(folder / f"{label}_response.npy")
        results[label] = analyze_channel(label, sig)

        plt.figure(figsize=(6,3))
        plt.semilogx(results[label]["freq"], results[label]["mag"])
        plt.title(f"{label} Frequency Response")
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Magnitude (dB)")
        plt.grid(True, which="both")
        plt.savefig(folder / f"{label}_fft.png")
        plt.close()

    confs = [results[ch]["confidence"] for ch in results]
    confidence_avg = np.mean(confs)
    if confidence_avg < MIN_CONFIDENCE:
        raise RuntimeError(f"❌ Low confidence ({confidence_avg:.1f}%), abort EQ run.")

    eqrec = {
        "bass_adjust_db": float(np.mean([results[ch]["bass_adj"] for ch in results])),
        "treble_adjust_db": float(-np.mean([results[ch]["bass_adj"] for ch in results]))
    }

    data = {"analysis": results, "eq_recommendation": eqrec,
            "confidence": confidence_avg}
    with open(folder / "results_analysis.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Analysis complete (confidence {confidence_avg:.1f}%)")

if __name__ == "__main__":
    analyze()
