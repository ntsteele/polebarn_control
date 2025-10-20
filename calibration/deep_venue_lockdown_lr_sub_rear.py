#!/usr/bin/env python3
"""
deep_venue_lockdown_lr_sub_rear.py – SPL-calibrated version
------------------------------------------------------------
Performs 4-pass lockdown capture with XR18:

  1) Main L  (LR ON, Bus6 OFF, Bus5 OFF)
  2) Main R  (LR ON, Bus6 OFF, Bus5 OFF)
  3) Sub     (LR OFF, Bus6 ON,  Bus5 OFF)
  4) Rear    (LR OFF, Bus6 OFF, Bus5 ON)

• Plays via USB Returns 17/18 (true 18-ch WAV; others silent).
• Records from iRig or any calibrated mic (uses equipment.json offset).
• Saves SPL-calibrated metrics and frequency responses.
"""

import os, sys, time, json, numpy as np, sounddevice as sd
from datetime import datetime
from pathlib import Path
from pythonosc.udp_client import SimpleUDPClient

# ───────────────────────────────────────────────────────────────
# Local imports
# ───────────────────────────────────────────────────────────────
sys.path.append(os.path.dirname(__file__))
from audio_io import build_wav_usb_17_18, play_wav_async, cleanup_tmp

# ───────────────────────────────────────────────────────────────
# XR18 CONFIGURATION
# ───────────────────────────────────────────────────────────────
XR18_IP, XR18_PORT = "192.168.4.136", 10024
BUS_SUB  = 6
BUS_REAR = 5
FS = 48000

# Sweep and level configuration
SWEEP_SEC    = 8.0
PREROLL_SEC  = 0.10
POSTROLL_SEC = 0.20
START_GAIN   = 0.015
MAX_GAIN     = 0.040
MIN_PEAK     = 0.03
N_PASSES     = 4

# Mic calibration file
CAL_FILE = Path.home() / "polebarn_control" / "calibration" / "configs" / "equipment.json"
MIC_OFFSET_DB = 0.0
if CAL_FILE.exists():
    try:
        with open(CAL_FILE) as f:
            cfg = json.load(f)
            MIC_OFFSET_DB = float(cfg.get("mic_offset_dB", 0.0))
        print(f"🎚️  Loaded mic calibration offset: +{MIC_OFFSET_DB:.2f} dB SPL correction")
    except Exception as e:
        print(f"⚠️  Could not read mic calibration file ({e}) – using 0 dB offset.")
else:
    print("⚠️  No mic calibration file found – using 0 dB offset.")

# iRig device selection
REC_DEVICE_HINT  = os.environ.get("REC_DEVICE_HINT", "iRig")
REC_DEVICE_INDEX = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None, "", "None") else None
FALLBACK_INDEX   = 1

DATA_ROOT = Path.home() / "polebarn_control" / "data"

# ───────────────────────────────────────────────────────────────
# OSC HELPERS
# ───────────────────────────────────────────────────────────────
osc = SimpleUDPClient(XR18_IP, XR18_PORT)
def _b(v): return 1 if v else 0
def lr_on(v=True):                osc.send_message("/lr/mix/on", _b(v))
def bus_on(bus, v=True):          osc.send_message(f"/bus/{bus}/mix/on", _b(v))
def rtn_on(v=True):               osc.send_message("/rtn/aux/mix/on", _b(v))
def rtn_to_bus(bus, v=True):      osc.send_message(f"/rtn/aux/mix/{bus}/on", _b(v))

def reset_defaults():
    rtn_on(True)
    lr_on(True)
    bus_on(BUS_SUB, True);  rtn_to_bus(BUS_SUB, True)
    bus_on(BUS_REAR, True); rtn_to_bus(BUS_REAR, True)

# ───────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ───────────────────────────────────────────────────────────────
def pick_record_device():
    devs = sd.query_devices()
    if REC_DEVICE_INDEX is not None:
        return REC_DEVICE_INDEX
    hint = (REC_DEVICE_HINT or "").lower()
    for i, d in enumerate(devs):
        if d["max_input_channels"] > 0 and hint in d["name"].lower():
            return i
    if FALLBACK_INDEX is not None and devs[FALLBACK_INDEX]["max_input_channels"] > 0:
        return FALLBACK_INDEX
    for i, d in enumerate(devs):
        if d["max_input_channels"] > 0:
            return i
    raise RuntimeError("No input device found (is iRig connected?)")

def make_sweep(sec=SWEEP_SEC, fs=FS):
    t = np.linspace(0, sec, int(fs * sec))
    s = np.sin(2 * np.pi * 20 * ((sec / np.log(20000 / 20)) * (np.exp(t * np.log(20000 / 20) / sec) - 1)))
    return s.astype(np.float32)

def record_one(left, right, dev_index):
    tmp = build_wav_usb_17_18(left, right, FS)
    pre  = int(PREROLL_SEC * FS)
    post = int(POSTROLL_SEC * FS)
    total = pre + len(left) + post

    rec = sd.rec(total, samplerate=FS, channels=1, device=dev_index)
    sd.sleep(int(PREROLL_SEC * 1000))
    p = play_wav_async(tmp)
    p.wait(); sd.wait()
    cleanup_tmp(tmp)

    seg = rec[pre:pre + len(left)].copy().flatten()
    peak = float(np.max(np.abs(seg)))
    rms = float(np.sqrt(np.mean(seg ** 2)))
    dbfs = 20 * np.log10(rms + 1e-12)
    spl = dbfs + MIC_OFFSET_DB  # calibrated SPL
    return seg, peak, spl

def capture_avg(label, lbuf, rbuf, dev_index):
    gain = START_GAIN
    takes, peaks, spls = [], [], []
    while len(takes) < N_PASSES:
        seg, pk, spl = record_one(lbuf * gain, rbuf * gain, dev_index)
        if pk < MIN_PEAK and gain * 1.35 <= MAX_GAIN:
            gain *= 1.35
            print(f"⚠️  {label}: peak {pk:.3f} too low → gain→{gain:.3f} retrying")
            time.sleep(0.3); continue
        takes.append(seg)
        peaks.append(pk)
        spls.append(spl)
        print(f"📏  {label} pass {len(takes)} – peak {pk:.3f}, avg SPL {spl:.1f} dB")
        time.sleep(0.2)
    return np.mean(np.stack(takes), axis=0), peaks, spls

# ───────────────────────────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────────────────────────
def main():
    dev_index = pick_record_device()
    sweep = make_sweep(); zeros = np.zeros_like(sweep)

    folder = DATA_ROOT / f"lockdown_LR_SubRear_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"🔒 Capture → {folder}")

    reset_defaults(); time.sleep(0.2)
    results = {}

    # 1) MAIN L
    lr_on(True)
    bus_on(BUS_SUB, False); rtn_to_bus(BUS_SUB, False)
    bus_on(BUS_REAR, False); rtn_to_bus(BUS_REAR, False)
    avg, peaks, spls = capture_avg("MainL", sweep, zeros, dev_index)
    np.save(folder / "MainL_response.npy", avg)
    results["MainL"] = {"avg_peak": np.mean(peaks), "avg_SPL_dB": np.mean(spls)}
    print("✓ MainL")

    # 2) MAIN R
    avg, peaks, spls = capture_avg("MainR", zeros, sweep, dev_index)
    np.save(folder / "MainR_response.npy", avg)
    results["MainR"] = {"avg_peak": np.mean(peaks), "avg_SPL_dB": np.mean(spls)}
    print("✓ MainR")

    # 3) SUB (Bus 6)
    lr_on(False)
    bus_on(BUS_SUB, True); rtn_to_bus(BUS_SUB, True)
    bus_on(BUS_REAR, False); rtn_to_bus(BUS_REAR, False)
    avg, peaks, spls = capture_avg("Sub", sweep, sweep, dev_index)
    np.save(folder / "Sub_response.npy", avg)
    results["Sub"] = {"avg_peak": np.mean(peaks), "avg_SPL_dB": np.mean(spls)}
    print("✓ Sub")

    # 4) REAR (Bus 5)
    lr_on(False)
    bus_on(BUS_SUB, False); rtn_to_bus(BUS_SUB, False)
    bus_on(BUS_REAR, True); rtn_to_bus(BUS_REAR, True)
    avg, peaks, spls = capture_avg("Rear", sweep, sweep, dev_index)
    np.save(folder / "Rear_response.npy", avg)
    results["Rear"] = {"avg_peak": np.mean(peaks), "avg_SPL_dB": np.mean(spls)}
    print("✓ Rear")

    # restore defaults
    reset_defaults()
    with open(folder / "summary.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n✅ Saved MainL/MainR/Sub/Rear responses & summary.json")
    for ch, vals in results.items():
        print(f"   {ch:<5} – avg peak {vals['avg_peak']:.3f}, avg SPL {vals['avg_SPL_dB']:.1f} dB SPL")

if __name__ == "__main__":
    main()
