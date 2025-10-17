#!/usr/bin/env python3
import json, numpy as np, matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
DATA_ROOT = Path.home()/ "polebarn_control"/"data"

def latest():
    c = sorted(DATA_ROOT.glob("lockdown_LR_SubRear_*"), key=lambda p: p.stat().st_mtime)
    if not c: raise FileNotFoundError("No lockdown_LR_SubRear_* folders found.")
    return c[-1]

def fft_db(x, fs=48000):
    x = np.asarray(x).flatten()
    f = np.fft.rfftfreq(x.size, 1/fs)
    m = 20*np.log10(np.abs(np.fft.rfft(x))+1e-12)
    return f, m

def smooth(m, n=32):
    k = np.ones(n)/n
    return np.convolve(m, k, "same")

def band_mean(f,m,lo,hi):
    sel = (f>=lo)&(f<hi)
    return float(np.mean(m[sel])) if np.any(sel) else float("nan")

def analyze_one(path, label, fs=48000):
    x = np.load(path)
    f,m = fft_db(x, fs); ms = smooth(m, 32)
    plt.figure(figsize=(8,4)); plt.semilogx(f,ms); plt.grid(True,which="both")
    plt.title(f"{label} Frequency Response"); plt.xlabel("Frequency (Hz)"); plt.ylabel("Magnitude (dB)")
    out = path.with_name(f"{label}_fft.png"); plt.savefig(out, dpi=120, bbox_inches="tight"); plt.close()
    metrics = {
        "25_45":  band_mean(f,ms,25,45),
        "45_90":  band_mean(f,ms,45,90),
        "90_120": band_mean(f,ms,90,120),
        "120_300":band_mean(f,ms,120,300),
        "1k_8k":  band_mean(f,ms,1000,8000),
    }
    return {"png": str(out), "metrics": metrics}

def main():
    folder = latest()
    paths = {
        "MainL": folder/"MainL_response.npy",
        "MainR": folder/"MainR_response.npy",
        "Sub":   folder/"Sub_response.npy",
        "Rear":  folder/"Rear_response.npy",
    }
    for k,p in paths.items():
        if not p.exists(): raise FileNotFoundError(p)

    res = {k: analyze_one(p,k) for k,p in paths.items()}
    ML, MR, SB, RE = [res[k]["metrics"] for k in ("MainL","MainR","Sub","Rear")]

    lr_presence = ML["1k_8k"] - MR["1k_8k"]
    sub_xo = SB["90_120"] - 0.5*(ML["90_120"]+MR["90_120"])
    rear_xo = RE["90_120"] - 0.5*(ML["90_120"]+MR["90_120"])

    out = {
        "folder": str(folder),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "channels": res,
        "deltas": {
            "L_minus_R_presence_db": float(lr_presence),
            "Sub_minus_Mains_100Hz_db": float(sub_xo),
            "Rear_minus_Mains_100Hz_db": float(rear_xo),
        }
    }
    with open(folder/"results_analysis.json","w") as f: json.dump(out,f,indent=2)

    print(f"📂 {folder}")
    print(f"L−R presence: {lr_presence:+.1f} dB | Sub@XO: {sub_xo:+.1f} dB | Rear@XO: {rear_xo:+.1f} dB")
    print(f"Saved: {folder/'results_analysis.json'}")
    print("PNGs:", *(folder/f"{k}_fft.png" for k in paths), sep="\n  ")

if __name__ == "__main__":
    main()
