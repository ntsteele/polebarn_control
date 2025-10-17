#!/usr/bin/env python3
"""
analyze_lockdown.py – Visual Analyzer Only
------------------------------------------
Plots and compares response curves.
No EQ or OSC commands.
"""
import numpy as np, json, matplotlib.pyplot as plt
from pathlib import Path

DATA_ROOT = Path.home() / "polebarn_control" / "data"

def latest_lockdown():
    folders = sorted(DATA_ROOT.glob("lockdown_*"), key=lambda p: p.stat().st_mtime)
    if not folders:
        raise FileNotFoundError("❌ No lockdown calibration folders found.")
    return folders[-1]

def fft_db(signal, fs=48000):
    spec = np.fft.rfft(signal.flatten())
    mag = 20*np.log10(np.abs(spec) + 1e-10)
    freq = np.fft.rfftfreq(len(signal), 1/fs)
    return freq, mag

def analyze():
    folder = latest_lockdown()
    print(f"📊 Analyzing lockdown folder: {folder}")
    for label in ["MainL", "MainR", "Subwoofer"]:
        sig = np.load(folder / f"{label}_response.npy")
        freq, mag = fft_db(sig)
        mag_smooth = np.convolve(mag, np.ones(32)/32, mode="same")

        plt.figure(figsize=(7,4))
        plt.semilogx(freq, mag_smooth, label=label)
        plt.title(f"{label} Frequency Response (Lockdown)")
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Magnitude (dB)")
        plt.grid(True, which="both")
        plt.savefig(folder / f"{label}_fft.png")
        plt.close()
        print(f"  ↳ Saved {label}_fft.png")

    print(f"✅ Analysis complete → {folder}\n")

if __name__ == "__main__":
    analyze()
