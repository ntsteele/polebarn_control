#!/usr/bin/env python3
"""
eq_apply.py – Safe EQ & Delay Application
----------------------------------------
Reads analyzed results, applies limited EQ/delay via OSC.
"""

import os, json
from pathlib import Path
from pythonosc.udp_client import SimpleUDPClient

XR18_IP, XR18_PORT = "192.168.4.136", 10024
QLC_IP,  QLC_PORT  = "127.0.0.1", 7700
DATA_ROOT = Path.home() / "polebarn_control" / "data"
MAX_GAIN = 3.0

def latest_results():
    folders = sorted(DATA_ROOT.glob("cal_*"), key=os.path.getmtime)
    if not folders: raise FileNotFoundError("❌ No calibration folder.")
    res = folders[-1] / "results_analysis.json"
    if not res.exists(): raise FileNotFoundError("❌ No results_analysis.json.")
    return json.load(open(res))

def send(client, path, val, dtype="f"):
    try:
        client.send_message(path, val)
        print(f"{path:<30} {val}")
    except Exception as e:
        print(f"⚠️  OSC send failed: {path} ({e})")

def main():
    data = latest_results()
    conf = data.get("confidence", 0)
    if conf < 80: raise RuntimeError(f"❌ Confidence too low ({conf:.1f}%).")

    eq = data["eq_recommendation"]
    bass = max(-MAX_GAIN, min(MAX_GAIN, eq["bass_adjust_db"]))
    treb = max(-MAX_GAIN, min(MAX_GAIN, eq["treble_adjust_db"]))

    mixer = SimpleUDPClient(XR18_IP, XR18_PORT)
    print("🎚️ Applying EQ + delay safely...")

    # Fixed HPF on mains
    send(mixer, "/lr/eq/on", 1, "i")
    eqs = [
        (1, 1, 90, 0.0, 0.7),
        (2, 0, 500, bass/2, 1.2),
        (3, 0, 2000, treb/2, 1.0),
        (4, 0, 5000, treb, 1.0),
        (5, 3,10000, treb, 0.8)
    ]
    for b,t,f,g,q in eqs:
        send(mixer, f"/lr/eq/{b}/type", t, "i")
        send(mixer, f"/lr/eq/{b}/freq", f)
        send(mixer, f"/lr/eq/{b}/gain", g)
        send(mixer, f"/lr/eq/{b}/q", q)
        send(mixer, f"/lr/eq/{b}/on", 1, "i")

    # Sub: fixed LPF 100 Hz
    send(mixer, "/bus/6/eq/on", 1, "i")
    sub = [
        (1, 2, 35, +2.0, 0.7),
        (2, 0, 60, 0.0, 1.0),
        (3, 0,100, -3.0, 1.0)
    ]
    for b,t,f,g,q in sub:
        send(mixer, f"/bus/6/eq/{b}/type", t, "i")
        send(mixer, f"/bus/6/eq/{b}/freq", f)
        send(mixer, f"/bus/6/eq/{b}/gain", g)
        send(mixer, f"/bus/6/eq/{b}/q", q)
        send(mixer, f"/bus/6/eq/{b}/on", 1, "i")

    print("✅ EQ applied successfully.\n")

if __name__ == "__main__":
    main()
