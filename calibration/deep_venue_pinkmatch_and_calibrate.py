#!/usr/bin/env python3
"""
deep_venue_pinkmatch_and_calibrate.py
-------------------------------------
One-button workflow:

1) Load mic calibration offset (dB).
2) Pink-noise level-match LR, Sub (Bus6), Rear (Bus5) to TARGET_SPL (85 dB).
   • Never set any fader above 1.00 (0 dB).
   • Start from a safe level; auto-adjust in small steps until ±0.5 dB.
   • Show you the proposed levels & SPLs; wait for confirmation.
3) Run deep venue lockdown sweeps for MainL, MainR, Sub, Rear in one take.
4) Analyze and generate Live Karaoke “House Smile” EQ recommendations.
5) Save recommendations to JSON and offer to apply via OSC (opt-in).
"""

import os, sys, time, json, math, subprocess
from pathlib import Path
from datetime import datetime

import numpy as np
import sounddevice as sd
from pythonosc.udp_client import SimpleUDPClient

# ─────────────────────────────────────────────────────────────────────────────
# Local helper (USB 17/18 playback)
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
from audio_io import build_wav_usb_17_18, play_wav_async, cleanup_tmp

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
FS = 48000
XR18_IP, XR18_PORT = "192.168.4.136", 10024
BUS_SUB, BUS_REAR = 6, 5

TARGET_SPL = 85.0       # dB SPL pink-noise target
TOL_DB = 0.5            # tolerance
START_TEST_FADER = 0.40 # safe start (~ -10 dB)
MAX_FADER = 1.00        # never exceed 0 dB on the desk

PINK_BLOCK_SEC = 2.5    # measurement block duration
QUIET_GAP_SEC  = 0.25   # gap between blocks

# Mic calibration file
CAL_FILE = Path.home() / "polebarn_control" / "calibration" / "configs" / "equipment.json"
MIC_OFFSET_DB = 0.0

# Audio input selection
REC_DEVICE_HINT  = os.environ.get("REC_DEVICE_HINT", "iRig")
REC_DEVICE_INDEX = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None,"","None") else None
FALLBACK_INDEX   = 1

# Data output
DATA_ROOT = Path.home() / "polebarn_control" / "data"

# Paths to analyzers (already in your repo)
ANALYSIS_DIR = Path.home() / "polebarn_control" / "analysis"
ANALYZER = ANALYSIS_DIR / "analyze_lr_sub_rear.py"

# ─────────────────────────────────────────────────────────────────────────────
# OSC helpers
# ─────────────────────────────────────────────────────────────────────────────
osc = SimpleUDPClient(XR18_IP, XR18_PORT)

def _b(v): return 1 if v else 0

def lr_on(v=True):           osc.send_message("/lr/mix/on", _b(v))
def bus_on(bus, v=True):     osc.send_message(f"/bus/{bus}/mix/on", _b(v))
def rtn_on(v=True):          osc.send_message("/rtn/aux/mix/on", _b(v))
def rtn_to_bus(bus, v=True): osc.send_message(f"/rtn/aux/mix/{bus}/on", _b(v))

def set_fader(path, value):
    val = max(0.0, min(MAX_FADER, float(value)))
    osc.send_message(path, val)

def reset_defaults():
    rtn_on(True)
    lr_on(True)
    for b in (BUS_SUB, BUS_REAR):
        bus_on(b, True); rtn_to_bus(b, True)

def set_matrix_for(label):
    """Mute/unmute routing for target label: 'LR', 'Sub', or 'Rear'."""
    if label == "LR":
        lr_on(True)
        bus_on(BUS_SUB, False); rtn_to_bus(BUS_SUB, False)
        bus_on(BUS_REAR, False); rtn_to_bus(BUS_REAR, False)
    elif label == "Sub":
        lr_on(False)
        bus_on(BUS_SUB, True);  rtn_to_bus(BUS_SUB, True)
        bus_on(BUS_REAR, False); rtn_to_bus(BUS_REAR, False)
    elif label == "Rear":
        lr_on(False)
        bus_on(BUS_SUB, False); rtn_to_bus(BUS_SUB, False)
        bus_on(BUS_REAR, True); rtn_to_bus(BUS_REAR, True)
    else:
        raise ValueError("Unknown label for matrix")

def fader_path(label):
    if label == "LR":   return "/lr/mix/fader"
    if label == "Sub":  return f"/bus/{BUS_SUB}/mix/fader"
    if label == "Rear": return f"/bus/{BUS_REAR}/mix/fader"
    raise ValueError("Unknown label for fader")

# ─────────────────────────────────────────────────────────────────────────────
# Mic + pink noise generation
# ─────────────────────────────────────────────────────────────────────────────
def load_mic_offset():
    global MIC_OFFSET_DB
    if CAL_FILE.exists():
        try:
            cfg = json.loads(CAL_FILE.read_text())
            MIC_OFFSET_DB = float(cfg.get("mic_offset_dB", 0.0))
            print(f"🎚️  Mic calibration loaded: +{MIC_OFFSET_DB:.2f} dB SPL offset")
        except Exception as e:
            print(f"⚠️  Could not read {CAL_FILE} ({e}); using 0 dB offset.")
    else:
        print("⚠️  No mic calibration file found; using 0 dB offset.")

def pick_record_device():
    devs = sd.query_devices()
    if REC_DEVICE_INDEX is not None:
        if devs[REC_DEVICE_INDEX]["max_input_channels"] < 1:
            raise RuntimeError("Selected input device has no channels.")
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
    raise RuntimeError("No input device found (is iRig connected?)")

def pink_noise(n, rng=None):
    """Voss-McCartney-ish pink noise (simple filtered white)."""
    rng = rng or np.random.default_rng()
    white = rng.standard_normal(n).astype(np.float32)
    # simple 1st-order low-shelving to approximate pink tilt
    # H(z) ~ (1 + a z^-1) / (1 + b z^-1)
    a, b = 0.985, 0.999
    y = np.zeros_like(white)
    for i in range(1, n):
        y[i] = white[i] + a * white[i-1] - b * y[i-1]
    # normalize
    y /= max(np.max(np.abs(y)), 1e-6)
    return y * 0.5  # modest amplitude

def build_pink_block(sec=PINK_BLOCK_SEC, fs=FS):
    n = int(sec * fs)
    p = pink_noise(n)
    return p.astype(np.float32)

def measure_spl_from_playback(lbuf, rbuf, dev_index):
    """Play a temp 18ch WAV (signal in 17/18), record mic, return SPL (dB)."""
    pre  = int(0.10 * FS)
    post = int(0.20 * FS)
    total = pre + len(lbuf) + post

    tmp = build_wav_usb_17_18(lbuf, rbuf, FS)

    rec = sd.rec(total, samplerate=FS, channels=1, device=dev_index, dtype='float32')
    sd.sleep(100)  # let recording settle
    p = play_wav_async(tmp)
    p.wait(); sd.wait()
    cleanup_tmp(tmp)

    seg = rec[pre:pre + len(lbuf)].copy().flatten()
    rms = float(np.sqrt(np.mean(seg**2)))
    dbfs = 20 * np.log10(rms + 1e-12)
    return dbfs + MIC_OFFSET_DB

# ─────────────────────────────────────────────────────────────────────────────
# Level matching
# ─────────────────────────────────────────────────────────────────────────────
def smart_step(current_db, target_db):
    """Convert dB error to a fader step (clamped). Approximate mapping."""
    err = target_db - current_db  # + means too quiet → increase fader
    # ~0.04 per dB gives gentle correction; clamp to avoid jumps
    step = max(-0.08, min(0.08, 0.04 * err))
    return step

def level_match(label, dev_index, start_fader=START_TEST_FADER):
    print(f"\n🎯 Level match → {label}")
    set_matrix_for(label)
    # set safe start fader
    set_fader(fader_path(label), start_fader)
    time.sleep(0.15)

    # run iterative adjustments
    max_iter = 12
    fader = start_fader
    last_db = None
    for k in range(1, max_iter+1):
        blk = build_pink_block()
        spl = measure_spl_from_playback(blk, blk, dev_index)  # mono pink into both USB returns
        last_db = spl
        print(f"  pass {k:>2}: {spl:6.2f} dB SPL  (fader {fader:0.2f})")

        if abs(spl - TARGET_SPL) <= TOL_DB:
            break

        step = smart_step(spl, TARGET_SPL)
        new_fader = max(0.0, min(MAX_FADER, fader + step))
        # if we hit ceiling and still low, stop (won't exceed 0 dB)
        if new_fader == fader:
            print("  • Reached fader limit; cannot raise further safely.")
            break
        fader = new_fader
        set_fader(fader_path(label), fader)
        time.sleep(QUIET_GAP_SEC)

    return fader, last_db

# ─────────────────────────────────────────────────────────────────────────────
# Deep sweep capture (reusing your lockdown approach)
# ─────────────────────────────────────────────────────────────────────────────
def exp_sweep(sec=8.0, fs=FS):
    t = np.linspace(0, sec, int(fs*sec))
    return np.sin(2*np.pi*20*((sec/np.log(20000/20))*(np.exp(t*np.log(20000/20)/sec)-1))).astype(np.float32)

def capture_lockdown_LR_SubRear(dev_index, folder):
    sweep = exp_sweep(); zeros = np.zeros_like(sweep)
    pre  = int(0.15 * FS); gap = int(0.50 * FS); post = int(0.30 * FS)
    total = pre + len(sweep) + gap + len(sweep) + gap + len(sweep) + gap + len(sweep) + post

    print("\n📡 Starting single-take lockdown capture (L→R→Sub→Rear)…")
    reset_defaults()
    try:
        rec = sd.rec(total, samplerate=FS, channels=1, device=dev_index, dtype='float32')
        sd.sleep(int(0.15*1000))

        # MAIN L
        set_matrix_for("LR")
        blk = build_wav_usb_17_18(sweep, zeros, FS)
        p = play_wav_async(blk); p.wait(); cleanup_tmp(blk); sd.sleep(int(0.50*1000))

        # MAIN R
        set_matrix_for("LR")
        blk = build_wav_usb_17_18(zeros, sweep, FS)
        p = play_wav_async(blk); p.wait(); cleanup_tmp(blk); sd.sleep(int(0.50*1000))

        # SUB
        set_matrix_for("Sub")
        blk = build_wav_usb_17_18(sweep, sweep, FS)
        p = play_wav_async(blk); p.wait(); cleanup_tmp(blk); sd.sleep(int(0.50*1000))

        # REAR
        set_matrix_for("Rear")
        blk = build_wav_usb_17_18(sweep, sweep, FS)
        p = play_wav_async(blk); p.wait(); cleanup_tmp(blk)

        sd.wait()
    finally:
        reset_defaults()

    # Slice windows
    rec = rec.flatten()
    i0 = pre;          i1 = i0 + len(sweep)
    j0 = i1 + gap;     j1 = j0 + len(sweep)
    k0 = j1 + gap;     k1 = k0 + len(sweep)
    m0 = k1 + gap;     m1 = m0 + len(sweep)

    np.save(folder/"MainL_response.npy", rec[i0:i1])
    np.save(folder/"MainR_response.npy", rec[j0:j1])
    np.save(folder/"Sub_response.npy",   rec[k0:k1])
    np.save(folder/"Rear_response.npy",  rec[m0:m1])
    print("✅ Saved responses for MainL/MainR/Sub/Rear")

# ─────────────────────────────────────────────────────────────────────────────
# House Smile recommendation (not applied without consent)
# ─────────────────────────────────────────────────────────────────────────────
def house_smile_recommendation(folder):
    """
    Build a friendly 'live karaoke' EQ suggestion.
    We keep it gentle and musical, ready for XR18 bands:

    Mains (/lr/eq):
      B1: HPF 90 Hz (type=1)
      B2: +2.0 dB @ 80 Hz, Q=0.8 (type=0 peak or shelf depending on taste)
      B3: -1.0 dB @ 400 Hz, Q=1.2
      B4: +1.8 dB @ 3.0 kHz, Q=1.0
      B5: +1.5 dB @ 10 kHz, Q=0.8 (air/presence)

    Sub (/bus/6/eq):
      B1: +1.5 dB @ 40 Hz,  Q=0.7 (type=2 low-shelf)
      B2: -2.0 dB @ 100 Hz, Q=1.0 (tighten crossover)
      B3: LPF 100 Hz (type=3 or implement via B3 gain -3 @ 100 Hz if shelf limited)

    Rear (/bus/5/eq) — slightly darker so mains dominate vocals up front:
      B1: -1.0 dB @ 8 kHz  Q=0.9
      B2: +0.5 dB @ 120 Hz Q=1.0
    """
    rec = {
        "mains": [
            {"band":1, "type":1, "freq":90,   "gain":0.0, "q":0.7, "on":1},   # HPF
            {"band":2, "type":0, "freq":80,   "gain":+2.0,"q":0.8, "on":1},
            {"band":3, "type":0, "freq":400,  "gain":-1.0,"q":1.2, "on":1},
            {"band":4, "type":0, "freq":3000, "gain":+1.8,"q":1.0, "on":1},
            {"band":5, "type":3, "freq":10000,"gain":+1.5,"q":0.8, "on":1},
        ],
        "sub": [
            {"band":1, "type":2, "freq":40,  "gain":+1.5, "q":0.7, "on":1},
            {"band":2, "type":0, "freq":100, "gain":-2.0, "q":1.0, "on":1},
            {"band":3, "type":0, "freq":100, "gain":-3.0, "q":1.0, "on":1},  # emulate LPF-ish tilt
        ],
        "rear": [
            {"band":1, "type":0, "freq":8000, "gain":-1.0, "q":0.9, "on":1},
            {"band":2, "type":0, "freq":120,  "gain":+0.5, "q":1.0, "on":1},
        ]
    }
    out = folder / "house_smile_recommendation.json"
    out.write_text(json.dumps(rec, indent=2))
    return rec, out

def apply_eq_block(path_base, block):
    # path_base e.g. "/lr/eq" or f"/bus/{BUS}/eq"
    for b in block:
        band = b["band"]
        osc.send_message(f"{path_base}/{band}/type", int(b["type"]))
        osc.send_message(f"{path_base}/{band}/freq", float(b["freq"]))
        osc.send_message(f"{path_base}/{band}/gain", float(b["gain"]))
        osc.send_message(f"{path_base}/{band}/q",    float(b["q"]))
        osc.send_message(f"{path_base}/{band}/on",   int(b["on"]))

# ─────────────────────────────────────────────────────────────────────────────
# Main flow
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("Polebarn • Pink-Match + Deep Calibration • Live Karaoke Mode\n")

    # Record user's Main DCA (informational only)
    try:
        dca_note = input("Type your Main DCA setting (e.g., '0 dB' or '-5 dB') for the log (Enter to skip): ").strip()
    except KeyboardInterrupt:
        dca_note = ""

    # Mic & calibration
    load_mic_offset()
    dev_index = pick_record_device()
    print(f"🎙️ Using input device {dev_index}: {sd.query_devices(dev_index)['name']}")

    # Data folder
    folder = DATA_ROOT / f"lockdown_LR_SubRear_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "target_spl_db": TARGET_SPL,
        "tolerance_db": TOL_DB,
        "mic_offset_db": MIC_OFFSET_DB,
        "main_dca_user_note": dca_note,
        "precal_faders": {},
        "postcal_faders": {}
    }

    # Start with safe test faders
    print("\n🔉 Setting safe start faders…")
    for lbl in ("LR","Sub","Rear"):
        set_fader(fader_path(lbl), START_TEST_FADER)
        summary["precal_faders"][lbl] = START_TEST_FADER
    reset_defaults(); time.sleep(0.2)

    # Level-match each bus
    results = {}
    for lbl in ("LR","Sub","Rear"):
        f, spl = level_match(lbl, dev_index, start_fader=START_TEST_FADER)
        results[lbl] = {"fader": float(f), "measured_spl_db": float(spl)}
        summary["postcal_faders"][lbl] = float(f)

    # Show results and confirm
    print("\n──────────────── Level Match Result ────────────────")
    for lbl in ("LR","Sub","Rear"):
        print(f"{lbl:>4} → {results[lbl]['measured_spl_db']:6.2f} dB SPL  | fader {results[lbl]['fader']:.2f}")
    print("───────────────────────────────────────────────────")
    input("If these look good, press [Enter] to continue to full calibration… ")

    # Deep sweep capture (single take)
    capture_lockdown_LR_SubRear(dev_index, folder)

    # Run analyzer to produce band metrics + plots
    try:
        print("📊 Running analyzer…")
        subprocess.run([sys.executable, str(ANALYZER)], check=True)
    except Exception as e:
        print(f"⚠️ Analyzer run failed: {e}")

    # Build karaoke House Smile
    rec, rec_path = house_smile_recommendation(folder)
    print(f"\n🎤 Live Karaoke ‘House Smile’ recommendation saved → {rec_path}")
    print("  Mains:", *(f"[B{b['band']} type{b['type']} {b['freq']}Hz {b['gain']}dB Q{b['q']}]" for b in rec["mains"]), sep="\n    ")
    print("  Sub:  ", *(f"[B{b['band']} type{b['type']} {b['freq']}Hz {b['gain']}dB Q{b['q']}]" for b in rec["sub"]), sep="\n    ")
    print("  Rear: ", *(f"[B{b['band']} type{b['type']} {b['freq']}Hz {b['gain']}dB Q{b['q']}]" for b in rec["rear"]), sep="\n    ")

    # Offer to apply now
    try:
        ans = input("\nApply this House-Smile EQ to XR18 now? [y/N]: ").strip().lower()
    except KeyboardInterrupt:
        ans = "n"

    if ans == "y":
        print("🛠️ Applying EQ to XR18 (Mains, Sub, Rear)…")
        apply_eq_block("/lr/eq", rec["mains"])
        apply_eq_block(f"/bus/{BUS_SUB}/eq", rec["sub"])
        apply_eq_block(f"/bus/{BUS_REAR}/eq", rec["rear"])
        print("✅ EQ applied.")
        summary["applied_house_smile"] = True
    else:
        print("Skipping EQ application (recommendation saved).")
        summary["applied_house_smile"] = False

    # Write summary
    (folder/"summary_levelmatch.json").write_text(json.dumps({
        "level_match": results,
        **summary
    }, indent=2))
    print(f"\n📁 Wrote: {folder/'summary_levelmatch.json'}")
    print("Done.\n")

if __name__ == "__main__":
    main()
