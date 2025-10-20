#!/usr/bin/env python3
"""
refmic_cal.py – Mic SPL calibration (no playback, XR18 silenced)
- Silences XR18 USB 17/18 sends & LR/Bus paths via OSC to guarantee no sound.
- Records ONLY from the iRig input (no playback).
- Waits for user to press Enter when 94 dB @ 1 kHz calibrator is on the mic.
- Computes correct SPL offset: SPL = dBFS + offset, where offset = CAL_SPL - dbfs.
- Saves to calibration/configs/equipment.json
"""

import os, json
from pathlib import Path
import numpy as np
import sounddevice as sd
from pythonosc.udp_client import SimpleUDPClient

# ── Config ───────────────────────────────────────────────────────────────────
CAL_FILE = Path.home() / "polebarn_control" / "calibration" / "configs" / "equipment.json"
SAMPLE_RATE = 48000
DURATION = 3.0
CAL_SPL = 94.0

# XR18 for safety mute (adjust IP/port if needed)
XR18_IP, XR18_PORT = "192.168.4.136", 10024
BUS_SUB, BUS_REAR = 6, 5

# iRig input selection
REC_DEVICE_HINT  = os.environ.get("REC_DEVICE_HINT", "iRig")
REC_DEVICE_INDEX = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None, "", "None") else None
FALLBACK_INDEX   = 1

# ── XR18 safety: silence everything (no USB return, no LR/Bus paths) ─────────
def _b(v): return 1 if v else 0
def xr18_silence_all():
    try:
        osc = SimpleUDPClient(XR18_IP, XR18_PORT)
        # Turn off USB return sends (LR + Bus5 + Bus6) and set their faders to 0
        osc.send_message("/rtn/aux/mix/on", 0)
        osc.send_message("/rtn/aux/mix/fader", 0.0)
        osc.send_message(f"/rtn/aux/mix/{BUS_SUB}/on", 0)
        osc.send_message(f"/rtn/aux/mix/{BUS_SUB}/fader", 0.0)
        osc.send_message(f"/rtn/aux/mix/{BUS_REAR}/on", 0)
        osc.send_message(f"/rtn/aux/mix/{BUS_REAR}/fader", 0.0)
        # Optionally turn off LR/Bus masters during calibration
        osc.send_message("/lr/mix/on", 0)
        osc.send_message(f"/bus/{BUS_SUB}/mix/on", 0)
        osc.send_message(f"/bus/{BUS_REAR}/mix/on", 0)
    except Exception as e:
        print(f"⚠️  Could not contact XR18 to silence outputs: {e}")

# ── Input device pick ────────────────────────────────────────────────────────
def pick_record_device():
    devs = sd.query_devices()
    if REC_DEVICE_INDEX is not None:
        return REC_DEVICE_INDEX
    hint = (REC_DEVICE_HINT or "").lower()
    for i, d in enumerate(devs):
        if d["max_input_channels"] > 0 and hint in d["name"].lower():
            return i
    if FALLBACK_INDEX is not None and sd.query_devices(FALLBACK_INDEX)["max_input_channels"] > 0:
        return FALLBACK_INDEX
    for i, d in enumerate(devs):
        if d["max_input_channels"] > 0:
            return i
    raise RuntimeError("No input device found (is the iRig connected?)")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("🎙️  Microphone SPL Calibration (XR18 silenced, no playback)")
    xr18_silence_all()

    dev = pick_record_device()
    info = sd.query_devices(dev)
    print(f"Using input device index {dev}: {info['name']}")
    print(f"\n👉 Slip the {CAL_SPL:.0f} dB @ 1 kHz calibrator over the mic capsule and turn it on.")
    input("Press [Enter] to record 3 seconds… ")

    # Record ONLY from the chosen input device; no playback device is opened.
    # Ensure we don't accidentally route output by fixing default device to (None, dev).
    sd.default.device = (None, dev)

    rec = sd.rec(int(DURATION * SAMPLE_RATE),
                 samplerate=SAMPLE_RATE,
                 channels=1,
                 device=dev,
                 dtype='float32')
    sd.wait()

    # Compute dBFS
    rms = float(np.sqrt(np.mean(rec ** 2)))
    dbfs = float(20 * np.log10(rms + 1e-12))

    # Correct offset math: SPL = dBFS + offset  ⇒ offset = CAL_SPL - dbfs
    offset = float(CAL_SPL - dbfs)

    data = {
        "mic_offset_dB": float(offset),
        "ref_level_dbfs": float(dbfs),
        "ref_spl": float(CAL_SPL),
        "sample_rate": int(SAMPLE_RATE),
        "device": str(info['name'])
    }
    CAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAL_FILE.write_text(json.dumps(data, indent=2))

    print("\n✅ Mic calibration complete (no playback used).")
    print(f"   Measured:  {dbfs:.2f} dBFS  →  Offset: +{offset:.2f} dB")
    print(f"   (Future SPL = dBFS + {offset:.2f})")
    print(f"   Saved → {CAL_FILE}")

if __name__ == "__main__":
    main()
