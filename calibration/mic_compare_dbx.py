#!/usr/bin/env python3
"""
mic_compare_dbx.py
Compare two DBX measurement microphones using an acoustic calibrator.

Fix: ensure all JSON fields are plain Python floats (not numpy float32).
"""

import os, sys, time, json, math, numpy as np
from pathlib import Path
from datetime import datetime
import sounddevice as sd
import matplotlib.pyplot as plt

# ==== CONFIG ================================================================
REC_DEVICE_HINT  = os.environ.get("REC_DEVICE_HINT", "iRig")  # matches "iRig PRO DUO"
REC_DEVICE_INDEX = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None,"","None") else None

FS          = 48000
DURATION_S  = 6.0         # record time per mic
CAL_FREQ_HZ = 1000.0      # typical calibrator frequency
CAL_SPL_DB  = 94.0        # set to your calibrator level (94 or 114 dB)
PEAK_WARN_DBFS = -1.0     # warn if above this (close to clip)
RMS_LOW_DBFS  = -40.0     # warn if lower than this (too low)

OUT_ROOT = Path.home() / "polebarn_control" / "data" / f"mic_test_{datetime.now():%Y%m%d_%H%M%S}"
# ===========================================================================

def pick_record_device():
    devs = sd.query_devices()
    if REC_DEVICE_INDEX is not None:
        info = devs[REC_DEVICE_INDEX]
        if info["max_input_channels"] < 2:
            raise RuntimeError(f"Selected device index {REC_DEVICE_INDEX} does not have 2 inputs.")
        print(f"🎙️ Using device index {REC_DEVICE_INDEX}: {info['name']}")
        return REC_DEVICE_INDEX
    hint = (REC_DEVICE_HINT or "").lower()
    for i, d in enumerate(devs):
        if d["max_input_channels"] >= 2 and hint in d["name"].lower():
            print(f"🎙️ Using device by hint '{REC_DEVICE_HINT}': index {i} – {d['name']}")
            return i
    # fallback: first with 2 inputs
    for i, d in enumerate(devs):
        if d["max_input_channels"] >= 2:
            print(f"🎙️ Using first 2-in device: index {i} – {d['name']}")
            return i
    raise RuntimeError("No suitable 2-input device found (is the iRig connected?)")

def dbfs(x):
    x = np.asarray(x, dtype=np.float64)
    rms = np.sqrt(np.mean(np.square(x)))
    peak = np.max(np.abs(x))
    rms_db = 20*np.log10(rms + 1e-20)
    peak_db = 20*np.log10(peak + 1e-20)
    return float(rms_db), float(peak_db)

def thd_percent(x, fs, f0=1000.0, window=True):
    """Very simple THD estimate (H2+H3 only) around f0 using FFT bins."""
    x = np.asarray(x, dtype=np.float32)
    N = int(2**int(np.ceil(np.log2(len(x)))))  # next pow2
    if window:
        w = np.hanning(len(x))
        xw = np.zeros(N, np.float32); xw[:len(x)] = x * w
    else:
        xw = np.zeros(N, np.float32); xw[:len(x)] = x
    X = np.fft.rfft(xw)
    f = np.fft.rfftfreq(N, 1/fs)
    mag = np.abs(X)

    def band_power(freq_center, bw_hz=10.0):
        sel = (f >= freq_center - bw_hz) & (f <= freq_center + bw_hz)
        return float(np.sum(mag[sel]**2) + 1e-30)

    p1 = band_power(f0, 10.0)
    p2 = band_power(2*f0, 10.0)
    p3 = band_power(3*f0, 10.0)
    thd = math.sqrt((p2 + p3) / p1) if p1 > 0 else float("nan")
    return float(thd * 100.0)

def freq_verification(x, fs, expected=1000.0):
    """Check peak frequency near expected tone."""
    x = np.asarray(x, dtype=np.float32)
    N = int(2**int(np.ceil(np.log2(len(x)))))  # zero-pad
    w = np.hanning(len(x))
    xw = np.zeros(N, np.float32); xw[:len(x)] = x * w
    X = np.fft.rfft(xw)
    f = np.fft.rfftfreq(N, 1/fs)
    mag = np.abs(X)
    idx = int(np.argmax(mag))
    peak_hz = float(f[idx])
    return peak_hz

def plot_spectrum(x, fs, title, out_png, fmax=5000):
    x = np.asarray(x, dtype=np.float32)
    N = int(2**int(np.ceil(np.log2(len(x)))))
    w = np.hanning(len(x))
    xw = np.zeros(N, np.float32); xw[:len(x)] = x * w
    X = np.fft.rfft(xw)
    f = np.fft.rfftfreq(N, 1/fs)
    m_db = 20*np.log10(np.abs(X) + 1e-20)
    plt.figure(figsize=(8,4))
    plt.plot(f, m_db)
    plt.xlim(0, fmax)
    plt.ylim(-140, 0)
    plt.grid(True, which="both")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Magnitude (dBFS)")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_png, dpi=120)
    plt.close()

def record_channel(dev_index, ch_index, label):
    """
    Record stereo, but evaluate just the requested channel index (0 or 1).
    Prompts the user to attach the calibrator to the right mic.
    """
    input(f"\n👉 Put the calibrator on {label} (iRig INPUT {ch_index+1}) at {CAL_SPL_DB:.0f} dB / {CAL_FREQ_HZ:.0f} Hz, then press Enter...")
    duration_frames = int(DURATION_S * FS)
    rec = sd.rec(duration_frames, samplerate=FS, channels=2, device=dev_index)
    sd.wait()
    ch = rec[:, ch_index].astype(np.float32).flatten()
    return ch

def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Output folder: {OUT_ROOT}")

    dev_index = pick_record_device()
    print("\nSet both iRig gain knobs to ~12 o'clock. Turn on 48V if your DBX mics need phantom.")
    print("Goal: peak between -12 and -3 dBFS; RMS ~ -24 to -12 dBFS.\n")

    # Mic 1 (good / new) on INPUT 1
    ch1 = record_channel(dev_index, 0, "Mic 1")
    rms1, peak1 = dbfs(ch1)
    peak_hz_1 = freq_verification(ch1, FS, CAL_FREQ_HZ)
    thd1 = thd_percent(ch1, FS, CAL_FREQ_HZ)

    # Mic 2 (dropped) on INPUT 2
    ch2 = record_channel(dev_index, 1, "Mic 2")
    rms2, peak2 = dbfs(ch2)
    peak_hz_2 = freq_verification(ch2, FS, CAL_FREQ_HZ)
    thd2 = thd_percent(ch2, FS, CAL_FREQ_HZ)

    # Compare sensitivities (dB difference)
    delta_db = float(rms2 - rms1)  # positive means Mic2 hotter
    verdict = []
    if peak1 > PEAK_WARN_DBFS or peak2 > PEAK_WARN_DBFS:
        verdict.append("⚠️ One or both recordings are near clipping; reduce gain and re-test.")
    if rms1 < RMS_LOW_DBFS or rms2 < RMS_LOW_DBFS:
        verdict.append("⚠️ One or both recordings are very low; raise gain and re-test.")

    # Damage heuristics
    if abs(delta_db) > 6.0:
        verdict.append("❌ Sensitivity difference > 6 dB → likely damaged capsule or preamp path.")
    elif abs(delta_db) > 3.0:
        verdict.append("⚠️ Sensitivity difference > 3 dB → possible damage or drift; recheck gains & re-test.")
    else:
        verdict.append("✅ Sensitivity within ±3 dB → broadly consistent.")

    # THD check
    thd_flag = []
    if not math.isnan(thd1) and thd1 > 2.0: thd_flag.append("Mic 1 THD high")
    if not math.isnan(thd2) and thd2 > 2.0: thd_flag.append("Mic 2 THD high")
    if thd_flag: verdict.append("⚠️ " + ", ".join(thd_flag) + " under the calibrator tone.")

    # Plots
    plot_spectrum(ch1, FS, f"Mic 1 spectrum (Cal {CAL_SPL_DB:.0f} dB @ {CAL_FREQ_HZ:.0f} Hz)", OUT_ROOT/"mic1_spectrum.png")
    plot_spectrum(ch2, FS, f"Mic 2 spectrum (Cal {CAL_SPL_DB:.0f} dB @ {CAL_FREQ_HZ:.0f} Hz)", OUT_ROOT/"mic2_spectrum.png")

    # Save JSON (cast everything to plain float)
    rep = {
        "fs": FS,
        "duration_s": DURATION_S,
        "calibrator": {"spl_db": float(CAL_SPL_DB), "freq_hz": float(CAL_FREQ_HZ)},
        "mic1": {"rms_dbfs": float(rms1), "peak_dbfs": float(peak1), "peak_freq_hz": float(peak_hz_1), "thd_percent": float(thd1)},
        "mic2": {"rms_dbfs": float(rms2), "peak_dbfs": float(peak2), "peak_freq_hz": float(peak_hz_2), "thd_percent": float(thd2)},
        "delta_db_mic2_minus_mic1": float(delta_db),
        "verdict": verdict
    }
    with open(OUT_ROOT/"report.json", "w") as f:
        json.dump(rep, f, indent=2)

    # Console summary
    print("\n──────── Results ────────")
    print(f"Mic 1: RMS {rms1:6.1f} dBFS, Peak {peak1:6.1f} dBFS, f≈{peak_hz_1:7.1f} Hz, THD≈{thd1:.2f}%")
    print(f"Mic 2: RMS {rms2:6.1f} dBFS, Peak {peak2:6.1f} dBFS, f≈{peak_hz_2:7.1f} Hz, THD≈{thd2:.2f}%")
    print(f"Sensitivity delta (Mic2−Mic1): {delta_db:+.2f} dB")
    print("\n" + "\n".join(verdict))
    print(f"\nSaved: {OUT_ROOT/'report.json'}")
    print(f"Plots: {OUT_ROOT/'mic1_spectrum.png'}, {OUT_ROOT/'mic2_spectrum.png'}\n")

if __name__ == "__main__":
    main()
