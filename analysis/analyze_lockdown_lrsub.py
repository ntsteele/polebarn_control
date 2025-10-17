#!/usr/bin/env python3
"""
analyze_lockdown_lrsub.py – Visual Analyzer for MainL/MainR/SubL/SubR
No mixer changes. Produces smoothed FFT plots for each capture.
"""

import numpy as np, json, matplotlib.pyplot as plt
from pathlib import Path

DATA_ROOT = Path.home() / "polebarn_control" / "data"

def latest_lockdown():
    folders = sorted(DATA_ROOT.glob("lockdown_lrsub_*"), key=lambda p: p.stat().st_mtime)
    if not folders: raise FileNotFoundError("❌ No lockdown_lrsub_* folders found.")
    return folders[-1]

def fft_db(signal, fs=48000):
    spec = np.fft.rfft(signal.flatten())
    mag = 20*np.log10(np.abs(spec) + 1e-10)
    freq = np.fft.rfftfreq(len(signal), 1/fs)
    return freq, mag

def smooth(vec, n=32):
    kern = np.ones(n)/n
    return np.convolve(vec, kern, mode="same")

def save_plot(folder, label, sig):
    f, m = fft_db(sig)
    m = smooth(m, 32)
    plt.figure(figsize=(8,4))
    plt.semilogx(f, m)
    plt.title(f"{label} Frequency Response (Lockdown)")
    plt.xlabel("Frequency (Hz)"); plt.ylabel("Magnitude (dB)")
    plt.grid(True, which="both")
    out = folder / f"{label}_fft.png"
    plt.savefig(out); plt.close()
    print(f"  ↳ Saved {out.name}")

def main():
    folder = latest_lockdown()
    print(f"📊 Analyzing: {folder}")
    for label in ["MainL","MainR","SubL","SubR"]:
        sig = np.load(folder / f"{label}_response.npy")
        save_plot(folder, label, sig)
    print("✅ Done.\n")

if __name__ == "__main__":
    main()
