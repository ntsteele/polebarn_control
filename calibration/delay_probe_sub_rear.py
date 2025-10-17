#!/usr/bin/env python3
"""
Measure delays of Sub (Bus6) and Rear (Bus5) vs Mains in ONE take.
Plays 3 sweeps: Mains → Sub → Rear via USB 17/18 (18ch WAV).
Adds guard time around each slice so the matched filter can find the onset.
Optionally apply delays with --apply-sub / --apply-rear (adds delay only if EARLY).
"""

import os, sys, time, argparse, numpy as np, sounddevice as sd
from pythonosc.udp_client import SimpleUDPClient

# helpers for USB 17/18 playback
sys.path.append(os.path.dirname(__file__))
from audio_io import build_wav_usb_17_18, play_wav_async, cleanup_tmp

# ── CONFIG ───────────────────────────────────────────────────────────────────
XR18_IP, XR18_PORT = "192.168.4.136", 10024
BUS_SUB, BUS_REAR = 6, 5
FS = 48000

SWEEP_SEC = 8.0       # can reduce to 6.0 if needed
GAP_SEC   = 0.50
PRE_SEC   = 0.15
POST_SEC  = 0.30
GUARD_MS  = 300       # ↑ extra room at lower level

GAIN      = 0.015     # ↓ from 0.030 (quieter)
MIN_PEAK  = 0.03
MAX_VALID_MS = 200.0  # reject absurd timings

# iRig selection
REC_DEVICE_HINT  = os.environ.get("REC_DEVICE_HINT","iRig")
REC_DEVICE_INDEX = os.environ.get("REC_DEVICE_INDEX")
REC_DEVICE_INDEX = int(REC_DEVICE_INDEX) if REC_DEVICE_INDEX not in (None,"","None") else None
FALLBACK_INDEX   = 1

# ── OSC helpers (mute/unmute + optional delay writes) ────────────────────────
osc = SimpleUDPClient(XR18_IP, XR18_PORT)
def _b(v): return 1 if v else 0
def lr_on(v=True):               osc.send_message("/lr/mix/on", _b(v))
def bus_on(bus,v=True):          osc.send_message(f"/bus/{bus}/mix/on", _b(v))
def rtn_on(v=True):              osc.send_message("/rtn/aux/mix/on", _b(v))
def rtn_to_bus(bus,v=True):      osc.send_message(f"/rtn/aux/mix/{bus}/on", _b(v))
def set_delay(bus, ms):          (osc.send_message(f"/bus/{bus}/delay/on",1), osc.send_message(f"/bus/{bus}/delay/value", float(ms)))
def reset_defaults():
    rtn_on(True); lr_on(True)
    for b in (BUS_SUB, BUS_REAR): bus_on(b, True); rtn_to_bus(b, True)

# ── utility ──────────────────────────────────────────────────────────────────
def pick_rec():
    devs=sd.query_devices()
    if REC_DEVICE_INDEX is not None:
        if devs[REC_DEVICE_INDEX]["max_input_channels"]<1: raise RuntimeError("Selected device has no input.")
        print(f"🎙️ Using input index {REC_DEVICE_INDEX}: {devs[REC_DEVICE_INDEX]['name']}"); return REC_DEVICE_INDEX
    hint=(REC_DEVICE_HINT or "").lower()
    for i,d in enumerate(devs):
        if d["max_input_channels"]>0 and hint in d["name"].lower():
            print(f"🎙️ Using input by hint '{REC_DEVICE_HINT}': {i} – {d['name']}"); return i
    if FALLBACK_INDEX is not None and devs[FALLBACK_INDEX]["max_input_channels"]>0:
        print(f"🎙️ Using fallback index {FALLBACK_INDEX}: {devs[FALLBACK_INDEX]['name']}"); return FALLBACK_INDEX
    for i,d in enumerate(devs):
        if d["max_input_channels"]>0: print(f"🎙️ Using first input: {i} – {d['name']}"); return i
    raise RuntimeError("No input device.")

def sweep(sec=SWEEP_SEC, fs=FS):
    t=np.linspace(0,sec,int(fs*sec))
    return np.sin(2*np.pi*20*((sec/np.log(20000/20))*(np.exp(t*np.log(20000/20)/sec)-1))).astype(np.float32)

def arrival_idx(rec_seg, ref):
    # matched filter (time-reversed ref), return index of best alignment
    x=rec_seg.astype(np.float32); r=ref.astype(np.float32)
    x-=x.mean(); r-=r.mean()
    c=np.correlate(x, r[::-1], mode="valid")
    return int(np.argmax(c))

def play_block(lbuf, rbuf):
    tmp=build_wav_usb_17_18(lbuf,rbuf,FS)
    p=play_wav_async(tmp); p.wait(); cleanup_tmp(tmp)

# ── main ─────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--apply-sub", action="store_true")
    ap.add_argument("--apply-rear", action="store_true")
    ap.add_argument("--max-ms", type=float, default=80.0)
    args=ap.parse_args(argv)

    reset_defaults()
    dev=pick_rec()
    s=sweep(); L=s*GAIN; R=s*GAIN

    pre  = int(PRE_SEC  * FS)
    gap  = int(GAP_SEC  * FS)
    post = int(POST_SEC * FS)
    guard = int((GUARD_MS/1000.0) * FS)

    # total frames across 3 sweeps
    N = pre + len(s) + gap + len(s) + gap + len(s) + post

    try:
        rec=sd.rec(N, samplerate=FS, channels=1, device=dev)
        sd.sleep(int(PRE_SEC*1000))

        # 1) MAIN: LR ON, buses OFF
        lr_on(True);  bus_on(BUS_SUB, False); rtn_to_bus(BUS_SUB, False)
        bus_on(BUS_REAR, False); rtn_to_bus(BUS_REAR, False)
        play_block(L,R)

        sd.sleep(int(GAP_SEC*1000))

        # 2) SUB: LR OFF, Sub ON
        lr_on(False); bus_on(BUS_SUB, True); rtn_to_bus(BUS_SUB, True)
        bus_on(BUS_REAR, False); rtn_to_bus(BUS_REAR, False)
        play_block(L,R)

        sd.sleep(int(GAP_SEC*1000))

        # 3) REAR: LR OFF, Rear ON
        lr_on(False); bus_on(BUS_SUB, False); rtn_to_bus(BUS_SUB, False)
        bus_on(BUS_REAR, True); rtn_to_bus(BUS_REAR, True)
        play_block(L,R)

        sd.wait()
    finally:
        reset_defaults()

    rec=rec.flatten()

    # coarse nominal windows
    i0=pre;            i1=i0+len(s)               # main
    j0=i1+gap;         j1=j0+len(s)               # sub
    k0=j1+gap;         k1=k0+len(s)               # rear

    # slice with guard
    def slice_guard(a0, a1):
        g0 = max(0, a0 - guard)
        g1 = min(rec.size, a1 + guard)
        return rec[g0:g1], g0

    main_win, main_base = slice_guard(i0, i1)
    sub_win,  sub_base  = slice_guard(j0, j1)
    rear_win, rear_base = slice_guard(k0, k1)

    # peaks for sanity
    pk_m=float(np.max(np.abs(main_win))); pk_s=float(np.max(np.abs(sub_win))); pk_r=float(np.max(np.abs(rear_win)))
    print(f"Peaks (guarded windows) → Main {pk_m:.3f}, Sub {pk_s:.3f}, Rear {pk_r:.3f}")
    if min(pk_m,pk_s,pk_r) < MIN_PEAK: print("⚠️ One or more peaks are low; consider raising level slightly.")

    # refine arrivals inside each guarded window
    off_m=arrival_idx(main_win, s)
    off_s=arrival_idx(sub_win,  s)
    off_r=arrival_idx(rear_win, s)

    abs_m = main_base + off_m
    abs_s = sub_base  + off_s
    abs_r = rear_base + off_r

    lag_samp_sub  = abs_s - abs_m
    lag_samp_rear = abs_r - abs_m
    ms_sub  = lag_samp_sub  * 1000.0 / FS
    ms_rear = lag_samp_rear * 1000.0 / FS

    def valid(ms): return abs(ms) <= MAX_VALID_MS

    print(f"\n⏱️ Sub vs Mains:  {lag_samp_sub:+d} samp  ≈ {ms_sub:+.2f} ms  "
          f"({'EARLY add delay' if ms_sub<0 else 'LATE reduce delay' if ms_sub>0 else 'aligned'})")
    print(  f"⏱️ Rear vs Mains: {lag_samp_rear:+d} samp  ≈ {ms_rear:+.2f} ms  "
          f"({'EARLY add delay' if ms_rear<0 else 'LATE reduce delay' if ms_rear>0 else 'aligned'})")

    # sanity: reject absurd values
    if not valid(ms_sub):  print("❌ Sub timing invalid (>|±200| ms). Re-run (levels ok? guards ok?).")
    if not valid(ms_rear): print("❌ Rear timing invalid (>|±200| ms). Re-run (levels ok? guards ok?).")

    # apply only when EARLY (we can safely add delay). Clamp by --max-ms
    if args.apply_sub and valid(ms_sub):
        add = max(0.0, -ms_sub); add=min(add, args.max_ms)
        set_delay(BUS_SUB, add); print(f"🛠️ Applied Bus6 delay = {add:.2f} ms")
    if args.apply_rear and valid(ms_rear):
        add = max(0.0, -ms_rear); add=min(add, args.max_ms)
        set_delay(BUS_REAR, add); print(f"🛠️ Applied Bus5 delay = {add:.2f} ms")

if __name__ == "__main__":
    main()
