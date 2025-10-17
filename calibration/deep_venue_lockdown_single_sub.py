#!/usr/bin/env python3
"""
deep_venue_lockdown_single_sub.py – Lockdown measurement with ONE sub on Aux 6
• Records from iRig explicitly (auto-detect by name, or override index via env)
• Plays via XR18 USB Returns 17/18 (18-ch WAV; others silent)
• MAIN L/R passes: Main LR ON, Aux 6 (sub) MUTED and Return→Bus6 OFF
• SUB pass: Main LR OFF, Aux 6 ON and Return→Bus6 ON
• NO EQ or delay changes; only LR/Aux6 mute toggles
• FIX: arm recording, pre-roll, async playback, post-roll, then slice window
"""

import os, sys, time, json, numpy as np, sounddevice as sd
from datetime import datetime
from pathlib import Path
from pythonosc.udp_client import SimpleUDPClient

# import helper from this folder (USB 17/18 playback)
sys.path.append(os.path.dirname(__file__))
from audio_io import build_wav_usb_17_18, play_wav_async, cleanup_tmp

# ── CONFIG ────────────────────────────────────────────────────────────────────
XR18_IP, XR18_PORT = "192.168.4.136", 10024
SUB_BUS = 6                       # your sub is on Aux/Bus 6
SAMPLE_RATE = 48000
DURATION    = 10.0
START_GAIN  = 0.025
MAX_GAIN    = 0.06
MIN_PEAK    = 0.05
N_PASSES    = 3

# recording timing
PREROLL_SEC  = 0.10   # record this long before starting playback
POSTROLL_SEC = 0.20   # record this long after playback ends

# Input device selection (prefer iRig)
REC_DEVICE_HINT  = os.environ.get("REC_DEVICE_HINT", "iRig")
REC_DEVICE_INDEX = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None, "", "None") else None
FALLBACK_INDEX   = 1  # from your device list: index 1 = iRig PRO DUO

DATA_ROOT = Path.home() / "polebarn_control" / "data"

# ── OSC HELPERS (mute/unmute only) ────────────────────────────────────────────
osc = SimpleUDPClient(XR18_IP, XR18_PORT)
def _b(v): return 1 if v else 0
def lr_on(v=True):           osc.send_message("/lr/mix/on", _b(v))
def bus_on(bus,v=True):      osc.send_message(f"/bus/{bus}/mix/on", _b(v))
def rtn_on(v=True):          osc.send_message("/rtn/aux/mix/on", _b(v))
def rtn_to_bus(bus,v=True):  osc.send_message(f"/rtn/aux/mix/{bus}/on", _b(v))

def reset_to_known_state():
    # Audible defaults: LR ON, Sub bus ON, USB Return to Sub ON
    rtn_on(True)
    lr_on(True)
    bus_on(SUB_BUS, True)
    rtn_to_bus(SUB_BUS, True)

# ── INPUT DEVICE PICKER ──────────────────────────────────────────────────────
def pick_record_device():
    devices = sd.query_devices()

    if REC_DEVICE_INDEX is not None:
        info = devices[REC_DEVICE_INDEX]
        if info["max_input_channels"] < 1:
            raise RuntimeError(f"Device index {REC_DEVICE_INDEX} has no input channels.")
        print(f"🎙️ Using input device index {REC_DEVICE_INDEX}: {info['name']}")
        return REC_DEVICE_INDEX

    hint = (REC_DEVICE_HINT or "").lower()
    for idx, d in enumerate(devices):
        if d["max_input_channels"] > 0 and hint in d["name"].lower():
            print(f"🎙️ Using input device by hint '{REC_DEVICE_HINT}': index {idx} – {d['name']}")
            return idx

    if FALLBACK_INDEX is not None and devices[FALLBACK_INDEX]["max_input_channels"] > 0:
        print(f"🎙️ Using fallback input device index {FALLBACK_INDEX}: {devices[FALLBACK_INDEX]['name']}")
        return FALLBACK_INDEX

    for idx, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            print(f"🎙️ Using first available input device: index {idx} – {d['name']}")
            return idx

    raise RuntimeError("❌ No input-capable audio device found (is iRig connected?)")

# ── SWEEP GEN ────────────────────────────────────────────────────────────────
def make_sweep(duration=DURATION, rate=SAMPLE_RATE):
    t = np.linspace(0, duration, int(rate * duration))
    # 20 Hz → 20 kHz exponential sweep
    sweep = np.sin(2*np.pi*20 * ((duration/np.log(20000/20)) * (np.exp(t*np.log(20000/20)/duration)-1)))
    return sweep.astype(np.float32)

# ── RECORD ONE PASS (arm → preroll → async play → postroll → slice) ─────────
def record_pass(label, left, right, rec_dev_index):
    # build temp WAV for USB 17/18 playback
    tmp = build_wav_usb_17_18(left, right, SAMPLE_RATE)

    # total recording length = preroll + sweep + postroll
    pre  = int(PREROLL_SEC  * SAMPLE_RATE)
    post = int(POSTROLL_SEC * SAMPLE_RATE)
    total_frames = pre + len(left) + post

    # arm recorder FIRST (non-blocking), then give it a moment
    rec = sd.rec(total_frames, samplerate=SAMPLE_RATE, channels=1, device=rec_dev_index)
    sd.sleep(int(PREROLL_SEC * 1000))  # actual preroll time

    # start playback asynchronously
    proc = play_wav_async(tmp)

    # wait for playback to finish, then for recording to finish
    proc.wait()
    sd.wait()  # now we block until the recording completes

    # cleanup temp file
    cleanup_tmp(tmp)

    # slice out the sweep region (drop pre/post roll)
    start = pre
    stop  = pre + len(left)
    rec_seg = rec[start:stop].copy()

    peak = float(np.max(np.abs(rec_seg)))
    return rec_seg, peak

def capture_avg(label, play_left, play_right, rec_dev_index):
    gain = START_GAIN; passes=[]; peaks=[]
    while len(passes) < N_PASSES:
        rec, peak = record_pass(label, play_left*gain, play_right*gain, rec_dev_index)
        if peak < MIN_PEAK and gain*1.4 <= MAX_GAIN:
            gain *= 1.4
            print(f"⚠️  {label}: mic peak {peak:.3f} too low → gain→{gain:.3f}, retrying pass"); time.sleep(0.3); continue
        passes.append(rec); peaks.append(peak); time.sleep(0.3)
    return np.mean(np.stack(passes), axis=0), peaks

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    rec_dev_index = pick_record_device()  # choose iRig (or override)
    sweep = make_sweep(); zeros = np.zeros_like(sweep)

    folder = DATA_ROOT / f"lockdown_singleSub_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"🔒 Lockdown (Main L/R with Sub muted, then Sub on Aux6) → {folder}")

    reset_to_known_state(); time.sleep(0.2)
    results = {}

    # MAIN L: LR ON; SUB OFF; Return→Bus6 OFF
    lr_on(True); rtn_to_bus(SUB_BUS, False); bus_on(SUB_BUS, False)
    avg, peaks = capture_avg("MainL", sweep, zeros, rec_dev_index)
    np.save(folder/"MainL_response.npy", avg)
    results["MainL"] = {"peaks":[float(p) for p in peaks], "avg_peak":float(np.mean(peaks))}
    print("✓ MainL done")

    # MAIN R: LR ON; SUB OFF; Return→Bus6 OFF
    avg, peaks = capture_avg("MainR", zeros, sweep, rec_dev_index)
    np.save(folder/"MainR_response.npy", avg)
    results["MainR"] = {"peaks":[float(p) for p in peaks], "avg_peak":float(np.mean(peaks))}
    print("✓ MainR done")

    # SUB (Aux6): LR OFF; SUB ON; Return→Bus6 ON
    lr_on(False); bus_on(SUB_BUS, True); rtn_to_bus(SUB_BUS, True)
    avg, peaks = capture_avg("Sub", sweep, sweep, rec_dev_index)  # bus sums mono
    np.save(folder/"Sub_response.npy", avg)
    results["Sub"] = {"peaks":[float(p) for p in peaks], "avg_peak":float(np.mean(peaks))}
    print("✓ Sub (Aux 6) done")

    # restore defaults
    reset_to_known_state()

    with open(folder/"summary.json","w") as f: json.dump(results, f, indent=2)
    print("\n✅ Saved averaged responses (MainL/MainR/Sub) & summary.json")
    print("   Recorded from input device index:", rec_dev_index, "\n")

if __name__ == "__main__":
    main()
