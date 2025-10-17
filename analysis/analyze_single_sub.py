#!/usr/bin/env python3
"""
analyze_single_sub.py – Visual + numeric analyzer for Lockdown Single-Sub runs
Reads the latest lockdown_singleSub_* folder created by deep_venue_lockdown_single_sub.py
Outputs:
  • Smoothed FFT plots for MainL, MainR, Sub
  • results_analysis.json with band metrics
  • Console summary with suggested *manual* trims (no OSC writes)
"""

import json, numpy as np, matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

DATA_ROOT = Path.home() / "polebarn_control" / "data"
OUT_JSON  = "results_analysis.json"

def latest_folder():
    cands = sorted(DATA_ROOT.glob("lockdown_singleSub_*"), key=lambda p: p.stat().st_mtime)
    if not cands:
        raise FileNotFoundError("No lockdown_singleSub_* folders found.")
    return cands[-1]

def fft_mag_db(x, fs=48000):
    x = np.asarray(x, dtype=np.float32).flatten()
    spec = np.fft.rfft(x)
    mag  = 20*np.log10(np.abs(spec)+1e-12)
    freq = np.fft.rfftfreq(len(x), d=1/fs)
    return freq, mag

def smooth_db(mag, n=32):
    kern = np.ones(n)/n
    return np.convolve(mag, kern, mode="same")

def band_mean(freq, mag, lo, hi):
    sel = (freq >= lo) & (freq < hi)
    if not np.any(sel): return float("nan")
    return float(np.mean(mag[sel]))

def analyze_channel(path_npy, label, fs=48000, smooth_n=32):
    x = np.load(path_npy)
    f, m = fft_mag_db(x, fs)
    m_s = smooth_db(m, smooth_n)
    # Plot
    plt.figure(figsize=(8,4))
    plt.semilogx(f, m_s)
    plt.title(f"{label} Frequency Response")
    plt.xlabel("Frequency (Hz)"); plt.ylabel("Magnitude (dB)")
    plt.grid(True, which="both")
    out_png = path_npy.with_name(f"{label}_fft.png")
    plt.savefig(out_png, dpi=120, bbox_inches="tight"); plt.close()

    # Bands
    metrics = {
        "very_low_25_45": band_mean(f, m_s, 25, 45),
        "low_45_90":      band_mean(f, m_s, 45, 90),
        "xover_90_120":   band_mean(f, m_s, 90, 120),
        "lowmid_120_300": band_mean(f, m_s, 120, 300),
        "mid_300_1000":   band_mean(f, m_s, 300, 1000),
        "presence_1k_8k": band_mean(f, m_s, 1000, 8000),
        "air_8k_16k":     band_mean(f, m_s, 8000, 16000),
        "peak_db": float(np.max(m_s))
    }
    return {"label": label, "png": str(out_png), "metrics": metrics}

def printable_db(x):
    return "—" if np.isnan(x) else f"{x:6.1f} dB"

def main():
    folder = latest_folder()
    print(f"📂 Analyzing: {folder}")

    paths = {
        "MainL": folder / "MainL_response.npy",
        "MainR": folder / "MainR_response.npy",
        "Sub":   folder / "Sub_response.npy",
    }
    for k,p in paths.items():
        if not p.exists():
            raise FileNotFoundError(f"Missing {k} file: {p}")

    res = {lbl: analyze_channel(p, lbl) for lbl,p in paths.items()}

    # Helpful deltas
    ML = res["MainL"]["metrics"]; MR = res["MainR"]["metrics"]; SB = res["Sub"]["metrics"]
    # L/R match (presence band often best for imaging check)
    lr_diff = (ML["presence_1k_8k"] - MR["presence_1k_8k"])
    # Sub vs mains near crossover
    sub_90  = SB["xover_90_120"]; mains_90 = np.mean([ML["xover_90_120"], MR["xover_90_120"]])
    xover_delta = sub_90 - mains_90  # + means sub hotter around 90–120 Hz

    # Suggest gentle manual trims (for human guidance ONLY)
    suggestions = {}
    # L/R balance
    if abs(lr_diff) >= 1.5:
        if lr_diff > 0:
            suggestions["LR_balance"] = "Right a tad lower in presence; consider -1 to -2 dB around 2–6 kHz on MainR."
        else:
            suggestions["LR_balance"] = "Left a tad lower in presence; consider -1 to -2 dB around 2–6 kHz on MainL."
    else:
        suggestions["LR_balance"] = "Left/Right presence balanced (±1.5 dB)."

    # Sub ↔ mains handoff
    if xover_delta > 2.0:
        suggestions["Sub_vs_Mains"] = "Sub is hot near crossover (+2 dB vs mains @ ~100 Hz). Consider -1 to -2 dB at 90–120 Hz on the Sub."
    elif xover_delta < -2.0:
        suggestions["Sub_vs_Mains"] = "Sub is light near crossover (−2 dB vs mains @ ~100 Hz). Consider +1 to +2 dB at 90–120 Hz on the Sub."
    else:
        suggestions["Sub_vs_Mains"] = "Crossover region looks well balanced (±2 dB)."

    # Deep bass shape
    deep_vs_upper = (SB["very_low_25_45"] - SB["low_45_90"])
    if deep_vs_upper < -3.0:
        suggestions["Deep_bass"] = "Sub rolls off below 45 Hz (~3 dB down). Normal for many boxes; boost only if desired."
    elif deep_vs_upper > 3.0:
        suggestions["Deep_bass"] = "Strong <45 Hz energy. Ensure room/ports aren't bloating; consider a small cut around 35–45 Hz if boomy."

    # Save JSON
    out = {
        "folder": str(folder),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "channels": res,
        "deltas": {
            "L_minus_R_presence_db": float(lr_diff),
            "sub_minus_mains_xover_db": float(xover_delta)
        },
        "suggestions": suggestions
    }
    with open(folder / OUT_JSON, "w") as f:
        json.dump(out, f, indent=2)

    # Console summary
    print("\n──────── SUMMARY (means of smoothed dB within bands) ────────")
    def row(lbl, m):
        print(f"{lbl:6}  "
              f"25–45 {printable_db(m['very_low_25_45'])}   "
              f"45–90 {printable_db(m['low_45_90'])}   "
              f"90–120 {printable_db(m['xover_90_120'])}   "
              f"1k–8k {printable_db(m['presence_1k_8k'])}")
    row("MainL", ML); row("MainR", MR); row("Sub", SB)

    print("\nL/R presence delta (L−R): "
          f"{lr_diff:+.1f} dB   |   Sub vs Mains @ ~100 Hz: {xover_delta:+.1f} dB")
    print("\nSuggestions:")
    for k,v in suggestions.items():
        print(f" • {k}: {v}")

    print(f"\n📁 Saved: {folder / OUT_JSON}")
    print(f"🖼️ Plots: {folder / 'MainL_fft.png'}, {folder / 'MainR_fft.png'}, {folder / 'Sub_fft.png'}\n")

if __name__ == "__main__":
    main()
