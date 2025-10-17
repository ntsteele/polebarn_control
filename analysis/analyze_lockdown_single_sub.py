#!/usr/bin/env python3
"""
analyze_lockdown_single_sub.py – Visual analyzer for MainL/MainR/Sub
Reads latest lockdown_singleSub_* folder and plots three responses.
"""

import numpy as np, matplotlib.pyplot as plt
from pathlib import Path

DATA_ROOT = Path.home() / "polebarn_control" / "data"

def latest_single():
    f = sorted(DATA_ROOT.glob("lockdown_singleSub_*"), key=lambda p: p.stat().st_mtime)
    if not f: raise FileNotFoundError("❌ No lockdown_singleSub_* folders found.")
    return f[-1]

def fft_db(x, fs=48000):
    spec = np.fft.rfft(x.flatten())
    mag = 20*np.log10(np.abs(spec)+1e-10)
    freq = np.fft.rfftfreq(len(x), 1/fs)
    return freq, mag

def smooth(y, n=32):
    import numpy as np
    k = np.ones(n)/n
    return np.convolve(y, k, mode="same")

def plot_one(folder, label):
    import numpy as np
    sig = np.load(folder / f"{label}_response.npy")
    f, m = fft_db(sig)
    m = smooth(m, 32)
    plt.figure(figsize=(8,4))
    plt.semilogx(f, m)
    plt.title(f"{label} Frequency Response (Lockdown Single-Sub)")
    plt.xlabel("Frequency (Hz)"); plt.ylabel("Magnitude (dB)")
    plt.grid(True, which="both")
    out = folder / f"{label}_fft.png"
    plt.savefig(out); plt.close()
    print(f"  ↳ Saved {out.name}")

def main():
    folder = latest_single()
    print(f"📊 Analyzing: {folder}")
    for label in ["MainL","MainR","Sub"]:
        plot_one(folder, label)
    print("✅ Done.\n")

if __name__ == "__main__":
    main()
