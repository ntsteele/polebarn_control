#!/usr/bin/env python3
"""
deep_venue_lrsub_lockdown.py – Lockdown measurement with separate Sub L / Sub R
Only uses mute/unmute on XR18. No EQ or delay changes. No pan changes.
Playback is forced through XR18 USB via aplay.
"""

import time, json, numpy as np, sounddevice as sd
from datetime import datetime
from pathlib import Path
from pythonosc.udp_client import SimpleUDPClient
from audio_io import play_stereo_through_xr18

# ── CONFIG ────────────────────────────────────────────────────────────────────
XR18_IP, XR18_PORT = "192.168.4.136", 10024
SUB_L_BUS, SUB_R_BUS = 5, 6        # which buses feed Sub Left / Sub Right
SAMPLE_RATE = 48000
DURATION = 10.0
START_GAIN = 0.025
MAX_GAIN   = 0.06
MIN_PEAK   = 0.05
N_PASSES   = 3

DATA_ROOT = Path.home() / "polebarn_control" / "data"

# ── OSC HELPERS (mute/unmute only) ────────────────────────────────────────────
osc = SimpleUDPClient(XR18_IP, XR18_PORT)

def osc_bool(path, val):
    osc.send_message(path, int(1 if val else 0))

def lr_on(val=True):
    osc_bool("/lr/mix/on", val)

def bus_on(bus, val=True):
    osc_bool(f"/bus/{bus}/mix/on", val)

def rtn_on(val=True):
    osc_bool("/rtn/aux/mix/on", val)

def rtn_to_bus(bus, val=True):
    # this toggles the send from USB Return (Aux) to a given bus (mute state)
    osc_bool(f"/rtn/aux/mix/{bus}/on", val)

def reset_to_known_state():
    # Ensure returns and buses are on; LR on
    rtn_on(True)
    lr_on(True)
    bus_on(SUB_L_BUS, True)
    bus_on(SUB_R_BUS, True)
    # Enable sends to both subs by default
    rtn_to_bus(SUB_L_BUS, True)
    rtn_to_bus(SUB_R_BUS, True)

# ── AUDIO SWEEP GEN ──────────────────────────────────────────────────────────
def make_sweep(duration=DURATION, rate=SAMPLE_RATE):
    t = np.linspace(0, duration, int(rate * duration))
    # 20 Hz → 20 kHz exponential sweep
    sweep = np.sin(2*np.pi*20 * ((duration/np.log(20000/20)) * (np.exp(t*np.log(20000/20)/duration)-1)))
    return sweep.astype(np.float32)

# ── RECORD ONE PASS (play via XR18 USB, record via Pi input) ─────────────────
def record_pass_stereo(label, left, right):
    # play to XR18 USB stereo
    play_stereo_through_xr18(left, right, SAMPLE_RATE)
    # record mic
    rec = sd.rec(len(left), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()
    peak = float(np.max(np.abs(rec)))
    return rec, peak

# ── MULTI-PASS CAPTURE FOR ONE CHANNEL ───────────────────────────────────────
def capture_avg(label, play_left, play_right):
    gain = START_GAIN
    passes, peaks = [], []
    while len(passes) < N_PASSES:
        lbuf = play_left  * gain
        rbuf = play_right * gain
        rec, peak = record_pass_stereo(label, lbuf, rbuf)
        if peak < MIN_PEAK and gain * 1.4 <= MAX_GAIN:
            gain *= 1.4
            print(f"⚠️  {label}: mic peak {peak:.3f} too low → gain→{gain:.3f}, retrying pass")
            time.sleep(0.3)
            continue
        passes.append(rec); peaks.append(peak)
        time.sleep(0.3)
    avg = np.mean(np.stack(passes), axis=0)
    return avg, peaks

# ── MAIN FLOW ────────────────────────────────────────────────────────────────
def main():
    sweep = make_sweep()
    zeros = np.zeros_like(sweep)

    folder = DATA_ROOT / f"lockdown_lrsub_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"🔒 Lockdown LR+Sub(L/R) run → {folder}")

    # put mixer into a known, audible state
    reset_to_known_state()
    time.sleep(0.2)

    results = {}

    # ── MAIN L: LR on; subs OFF
    rtn_to_bus(SUB_L_BUS, False)
    rtn_to_bus(SUB_R_BUS, False)
    lr_on(True)
    avg, peaks = capture_avg("MainL", sweep, zeros)   # LEFT only
    np.save(folder / "MainL_response.npy", avg)
    results["MainL"] = {"peaks": [float(p) for p in peaks], "avg_peak": float(np.mean(peaks))}
    print("✓ MainL done")

    # ── MAIN R: LR on; subs OFF
    avg, peaks = capture_avg("MainR", zeros, sweep)   # RIGHT only
    np.save(folder / "MainR_response.npy", avg)
    results["MainR"] = {"peaks": [float(p) for p in peaks], "avg_peak": float(np.mean(peaks))}
    print("✓ MainR done")

    # ── SUB L: LR OFF, Bus5 send ON, Bus6 send OFF
    lr_on(False)
    rtn_to_bus(SUB_L_BUS, True)
    rtn_to_bus(SUB_R_BUS, False)
    # send identical L/R to the USB return; bus send is mono → content doesn't matter
    avg, peaks = capture_avg("SubL", sweep, sweep)
    np.save(folder / "SubL_response.npy", avg)
    results["SubL"] = {"peaks": [float(p) for p in peaks], "avg_peak": float(np.mean(peaks))}
    print("✓ SubL done")

    # ── SUB R: LR OFF, Bus6 send ON, Bus5 send OFF
    rtn_to_bus(SUB_L_BUS, False)
    rtn_to_bus(SUB_R_BUS, True)
    avg, peaks = capture_avg("SubR", sweep, sweep)
    np.save(folder / "SubR_response.npy", avg)
    results["SubR"] = {"peaks": [float(p) for p in peaks], "avg_peak": float(np.mean(peaks))}
    print("✓ SubR done")

    # ── RESTORE audible defaults (nothing left muted)
    reset_to_known_state()

    with open(folder / "summary.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n✅ Saved averaged responses (MainL/MainR/SubL/SubR) & summary.json")
    print("   Next: run your analyzer to plot/compare. No EQ or delay were changed.\n")

if __name__ == "__main__":
    main()
