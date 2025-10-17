#!/usr/bin/env python3
"""
preamp_match_irig.py
Match iRig PRO DUO preamp gains (Input 1 vs Input 2) using ONE mic + calibrator.

Workflow
--------
1) Put the calibrator on your mic. Plug the SAME mic into iRig INPUT 1.
2) Script records a short tone => measures RMS/Peak dBFS.
3) Move the SAME mic to iRig INPUT 2. Script records => measures RMS/Peak dBFS.
4) It prints the difference and tells you which knob to nudge.
5) Press [y] to loop until the inputs match within your tolerance.

Notes
-----
- This matches the *preamp gains*. Use ONE mic to remove capsule variance.
- Works with any steady calibrator tone (e.g., 1 kHz @ 94 dB).
- No changes to mixer/EQ/etc. This is only measuring the audio interface inputs.
"""

import os, sys, time, json, math, numpy as np
from pathlib import Path
from datetime import datetime
import sounddevice as sd

# ── CONFIG ───────────────────────────────────────────────────────────────────
REC_DEVICE_HINT   = os.environ.get("REC_DEVICE_HINT", "iRig")  # matches "iRig PRO DUO"
REC_DEVICE_INDEX  = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX  = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None,"","None") else None

FS                = 48000       # sample rate
DURATION_S        = 4.0         # record time per input (seconds)
SETTLE_MS         = 300         # discard initial ms to avoid handling noise
TARGET_RMS_MIN    = -28.0       # acceptable dBFS range for RMS
TARGET_RMS_MAX    = -10.0
PEAK_NEAR_CLIP    = -1.5        # warn if peak is above this
FREQ_CHECK_HZ     = 1000.0      # expected calibrator tone (for info only)
TOLERANCE_DB      = 1.0         # goal: |Input2 - Input1| <= this many dB

OUT_ROOT = Path.home() / "polebarn_control" / "data" / f"preamp_match_{datetime.now():%Y%m%d_%H%M%S}"
# ─────────────────────────────────────────────────────────────────────────────

def pick_record_device():
    devs = sd.query_devices()
    if REC_DEVICE_INDEX is not None:
        info = devs[REC_DEVICE_INDEX]
        if info["max_input_channels"] < 2:
            raise RuntimeError(f"Selected device index {REC_DEVICE_INDEX} does not have 2 inputs.")
        print(f"🎛️ Using device index {REC_DEVICE_INDEX}: {info['name']}")
        return REC_DEVICE_INDEX
    hint = (REC_DEVICE_HINT or "").lower()
    for i, d in enumerate(devs):
        if d["max_input_channels"] >= 2 and hint in d["name"].lower():
            print(f"🎛️ Using device by hint '{REC_DEVICE_HINT}': index {i} – {d['name']}")
            return i
    # fallback: first with 2 inputs
    for i, d in enumerate(devs):
        if d["max_input_channels"] >= 2:
            print(f"🎛️ Using first 2-in device: index {i} – {d['name']}")
            return i
    raise RuntimeError("No suitable 2-input device found (is the iRig connected?)")

def dbfs(x):
    x = np.asarray(x, dtype=np.float64)
    # drop first few hundred ms to avoid handling thump
    n_drop = int((SETTLE_MS/1000.0) * FS)
    if x.size > n_drop:
        x = x[n_drop:]
    rms = np.sqrt(np.mean(np.square(x))) + 1e-20
    peak = np.max(np.abs(x)) + 1e-20
    return float(20*np.log10(rms)), float(20*np.log10(peak))

def freq_peak_hz(x):
    x = np.asarray(x, dtype=np.float32)
    n = int(2**int(np.ceil(np.log2(len(x)))))
    w = np.hanning(len(x))
    xw = np.zeros(n, np.float32)
    xw[:len(x)] = x * w
    X = np.fft.rfft(xw)
    f = np.fft.rfftfreq(n, 1/FS)
    mag = np.abs(X)
    idx = int(np.argmax(mag))
    return float(f[idx])

def record_input(dev_index, ch_index, label):
    input(f"\n👉 Put the calibrator on the SAME mic plugged into iRig INPUT {ch_index+1} ({label}). "
          f"Press Enter to record {DURATION_S:.1f}s…")
    frames = int(DURATION_S * FS)
    rec = sd.rec(frames, samplerate=FS, channels=2, device=dev_index)
    sd.wait()
    ch = rec[:, ch_index].astype(np.float32).flatten()
    rms_db, peak_db = dbfs(ch)
    f0 = freq_peak_hz(ch)
    print(f"   {label}: RMS {rms_db:6.1f} dBFS | Peak {peak_db:6.1f} dBFS | f≈{f0:7.1f} Hz")
    if peak_db > PEAK_NEAR_CLIP:
        print("   ⚠️ Peak is close to 0 dBFS (near clipping). Turn that input DOWN a touch and re-run.")
    if rms_db < TARGET_RMS_MIN or rms_db > TARGET_RMS_MAX:
        print(f"   ⚠️ RMS outside target range [{TARGET_RMS_MIN:.0f},{TARGET_RMS_MAX:.0f}] dBFS. "
              f"Adjust that input for a comfy level.")
    if abs(f0 - FREQ_CHECK_HZ) > 20:
        print("   ℹ️ Detected tone is not ~1 kHz; that’s OK if your calibrator uses a different frequency.")
    return rms_db, peak_db, f0

def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    dev_index = pick_record_device()

    print("\nSet BOTH iRig gain knobs around 12 o’clock. Phantom on if your mic needs it.")
    print(f"Target per input: RMS ~ {TARGET_RMS_MIN:.0f} to {TARGET_RMS_MAX:.0f} dBFS; Peak below {PEAK_NEAR_CLIP:.1f} dBFS.")
    print("Use ONE mic and the same calibrator setting for both inputs.\n")

    history = []
    while True:
        rms1, peak1, f1 = record_input(dev_index, 0, "Input 1")
        rms2, peak2, f2 = record_input(dev_index, 1, "Input 2")

        diff = float(rms2 - rms1)  # positive => Input 2 hotter than Input 1
        direction = "DOWN" if diff > 0 else "UP"
        which = "Input 2" if diff > 0 else "Input 2"  # we adjust Input 2 to match Input 1
        print("\n──────── Comparison ────────")
        print(f"Input 1 RMS: {rms1:6.1f} dBFS")
        print(f"Input 2 RMS: {rms2:6.1f} dBFS")
        print(f"Δ (Input2 − Input1): {diff:+.2f} dB")

        if abs(diff) <= TOLERANCE_DB:
            print(f"✅ Matched within ±{TOLERANCE_DB:.1f} dB. You’re good!")
        else:
            print(f"➡️  Turn {which} gain {direction} by ≈ {abs(diff):.1f} dB and test again.")

        # Save a small JSON record each pass
        rec = {
            "fs": FS,
            "duration_s": DURATION_S,
            "rms_dbfs_input1": float(rms1),
            "rms_dbfs_input2": float(rms2),
            "peak_dbfs_input1": float(peak1),
            "peak_dbfs_input2": float(peak2),
            "freq_hz_input1": float(f1),
            "freq_hz_input2": float(f2),
            "delta_db_input2_minus_input1": float(diff),
            "tolerance_db": float(TOLERANCE_DB),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        history.append(rec)
        with open(OUT_ROOT / "preamp_match_log.json", "w") as f:
            json.dump(history, f, indent=2)

        if abs(diff) <= TOLERANCE_DB:
            print(f"\nLog saved to: {OUT_ROOT/'preamp_match_log.json'}")
            break

        ans = input("\nRepeat measurement? [y/N]: ").strip().lower()
        if ans != "y":
            print(f"\nStopped. Log saved to: {OUT_ROOT/'preamp_match_log.json'}")
            break

if __name__ == "__main__":
    main()
