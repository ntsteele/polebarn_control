#!/usr/bin/env python3
"""
mic_compare_dbx_multi.py
Compare iRig INPUT 1 vs INPUT 2 with a calibrator (multi-pass, robust median).
Optionally writes mic_offsets.json so analysis can compensate the lower mic.

Usage:
  python3 mic_compare_dbx_multi.py            # measure only
  python3 mic_compare_dbx_multi.py --save MicGood MicDropped
    - Will save offsets assuming the mic on INPUT 1 is "MicGood" (reference 0 dB),
      and the mic on INPUT 2 is "MicDropped" (gets +offset to compensate).

Tips:
- Use ONE mic on INPUT 1 for 3 passes, then move the SAME mic to INPUT 2 for 3 passes.
- Seat the calibrator fully with the 1/2" adaptor, slight twist, same depth each time.
"""

import os, sys, json, math, numpy as np, sounddevice as sd
from pathlib import Path
from statistics import median

# ---------- Config ----------
REC_DEVICE_HINT = os.environ.get("REC_DEVICE_HINT", "iRig")
REC_DEVICE_INDEX = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None,"","None") else None

FS = 48000
DURATION_S = 4.0
SETTLE_S = 0.3
TAKES = 3
FREQ_HZ = 1000.0
NEAR_CLIP = -1.5
TARGET_RMS = (-28.0, -10.0)

OFFSETS_FILE = Path.home()/ "polebarn_control"/"calibration"/"mic_offsets.json"
# ---------------------------

def pick_record_device():
    devs = sd.query_devices()
    if REC_DEVICE_INDEX is not None and devs[REC_DEVICE_INDEX]["max_input_channels"] >= 2:
        print(f"🎙️ Using device index {REC_DEVICE_INDEX}: {devs[REC_DEVICE_INDEX]['name']}")
        return REC_DEVICE_INDEX
    for i,d in enumerate(devs):
        if d["max_input_channels"] >= 2 and REC_DEVICE_HINT.lower() in d["name"].lower():
            print(f"🎙️ Using device by hint '{REC_DEVICE_HINT}': index {i} – {d['name']}")
            return i
    for i,d in enumerate(devs):
        if d["max_input_channels"] >= 2:
            print(f"🎙️ Using first 2-in device: index {i} – {d['name']}")
            return i
    raise RuntimeError("No 2-input device found.")

def dbfs(x):
    n_drop = int(SETTLE_S*FS)
    if x.size > n_drop: x = x[n_drop:]
    rms = float(np.sqrt(np.mean(np.square(x))) + 1e-20)
    pk  = float(np.max(np.abs(x)) + 1e-20)
    return 20*np.log10(rms), 20*np.log10(pk)

def freq_peak(x):
    n = 1<<int(np.ceil(np.log2(len(x))))
    w = np.hanning(len(x))
    X = np.fft.rfft(np.pad(x*w,(0,n-len(x))))
    f = np.fft.rfftfreq(n, 1/FS)
    return float(f[int(np.argmax(np.abs(X)))])

def take_for_channel(dev, ch, label):
    input(f"\n👉 Seat the calibrator on the mic at iRig INPUT {ch+1} ({label}). Press Enter to record {DURATION_S:.1f}s…")
    frames = int(DURATION_S*FS)
    rec = sd.rec(frames, samplerate=FS, channels=2, device=dev)
    sd.wait()
    x = rec[:, ch].astype(np.float32).flatten()
    rms, pk = dbfs(x)
    f0 = freq_peak(x)
    print(f"   {label}: RMS {rms:6.1f} dBFS | Peak {pk:6.1f} dBFS | f≈{f0:7.1f} Hz")
    if pk > NEAR_CLIP: print("   ⚠️ Near clipping — back off that input a touch.")
    lo, hi = TARGET_RMS
    if not (lo <= rms <= hi): print(f"   ⚠️ RMS outside target [{lo:.0f},{hi:.0f}] dBFS.")
    return rms

def collect(dev, ch, label):
    vals=[]
    for i in range(TAKES):
        print(f"\n— {label}: take {i+1}/{TAKES} —")
        vals.append(take_for_channel(dev, ch, label))
    vals = np.array(vals, float)
    med = float(median(vals))
    # reject a wild outlier (>2 dB from median) and recompute
    keep = np.abs(vals - med) <= 2.0
    if not np.all(keep):
        vals = vals[keep]
        med = float(median(vals))
        print(f"   (Dropped outliers; using {len(vals)} takes.)")
    print(f"⇒ {label} median RMS: {med:.2f} dBFS (from {len(vals)} takes)")
    return med

def save_offsets(name_ref, name_other, delta_db):
    # Ref mic gets 0.0 dB; other mic gets +delta_db compensation
    d = {"Mic1": 0.0, "Mic2": 0.0}
    if OFFSETS_FILE.exists():
        try: d.update(json.loads(OFFSETS_FILE.read_text()))
        except Exception: pass
    d[name_ref]  = 0.0
    d[name_other]= float(round(delta_db,2))
    OFFSETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSETS_FILE.write_text(json.dumps(d, indent=2))
    print(f"\n💾 Wrote {OFFSETS_FILE} → {name_ref}: 0.00 dB, {name_other}: +{delta_db:.2f} dB")

def main(argv=None):
    args = sys.argv[1:]
    save = False
    names = ("Mic1","Mic2")
    if len(args) == 3 and args[0] == "--save":
        save = True
        names = (args[1], args[2])  # e.g., MicGood MicDropped

    dev = pick_record_device()
    print("\nUse ONE mic for both inputs. We’ll do 3 takes on Input 1, then 3 on Input 2.")
    print("Seat the calibrator fully the same each time (same adaptor, depth).")

    rms1 = collect(dev, 0, "Input 1")
    rms2 = collect(dev, 1, "Input 2")

    delta = rms2 - rms1  # positive => Input 2 hotter
    print("\n──────── Summary ────────")
    print(f"Input 1 median RMS: {rms1:6.2f} dBFS")
    print(f"Input 2 median RMS: {rms2:6.2f} dBFS")
    print(f"Δ (Input2 − Input1): {delta:+.2f} dB")

    if save:
        # Treat Input 1’s mic name as the reference (0 dB); Input 2 gets +delta compensation
        save_offsets(names[0], names[1], -delta)  # negative delta means Input2 lower → +comp
        print("Next: your analysis scripts should multiply by 10**(offset/20) per mic name.")

if __name__ == "__main__":
    main()
