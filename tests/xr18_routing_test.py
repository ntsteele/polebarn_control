#!/usr/bin/env python3
"""
XR18 Routing Verification – Corrected for /lr/mix paths and 0.0–1.0 pan scale
Plays tone through Left, Right, and Sub (Bus 6) via USB 17/18 return.
"""

import time, os, subprocess
import numpy as np
import pytest

sf = pytest.importorskip("soundfile")
from pythonosc.udp_client import SimpleUDPClient

XR18_IP     = "192.168.4.136"
XR18_PORT   = 10024
XR18_DEVICE = "plughw:CARD=X18XR18,DEV=0"
SAMPLE_RATE = 48000
GAIN        = 0.03
DURATION    = 3.0

client = SimpleUDPClient(XR18_IP, XR18_PORT)
DATA = os.path.expanduser("~/polebarn_control/data")
os.makedirs(DATA, exist_ok=True)

# ───────── Audio helpers ─────────
def make_tone(freq=1000):
    t = np.linspace(0, DURATION, int(SAMPLE_RATE*DURATION), endpoint=False)
    tone = (np.sin(2*np.pi*freq*t) * GAIN).astype(np.float32)
    path = os.path.join(DATA, "xr18_test_tone.wav")
    sf.write(path, tone, SAMPLE_RATE)
    return path

def play(path):
    subprocess.run(["aplay", "-D", XR18_DEVICE, path], check=True)

# ───────── XR18 helpers ─────────
def mute_all():
    """Ensure everything starts muted."""
    client.send_message("/lr/mix/on", 0.0)
    client.send_message("/bus/06/mix/on", 0.0)
    client.send_message("/rtn/aux/mix/on", 0.0)
    for i in range(1, 7):
        client.send_message(f"/rtn/aux/mix/{i:02d}/on", 0.0)
    time.sleep(0.3)

def unmute_mains(pan_val):
    """Enable USB → LR, set pan (0.0=L, 1.0=R)."""
    client.send_message("/bus/06/mix/on", 0.0)
    client.send_message("/lr/mix/on", 1.0)
    client.send_message("/rtn/aux/mix/on", 1.0)
    client.send_message("/rtn/aux/mix/06/on", 0.0)
    client.send_message("/lr/mix/pan", pan_val)
    print(f"   → LR pan {pan_val:.2f}")

def unmute_sub():
    """Enable USB → Bus 6 (Sub)."""
    client.send_message("/lr/mix/on", 0.0)
    client.send_message("/bus/06/mix/on", 1.0)
    client.send_message("/rtn/aux/mix/on", 1.0)
    client.send_message("/rtn/aux/mix/06/on", 1.0)
    client.send_message("/rtn/aux/mix/06/level", 0.8)

# ───────── Test sequence ─────────
def run_test():
    tone = make_tone()
    print("🚀 XR18 Routing Verification (firmware v1.22 /lr/mix paths)\n")

    # MAIN LEFT
    print("🎧 Step 1: Left")
    mute_all(); unmute_mains(0.0)
    time.sleep(0.5); play(tone)

    # MAIN RIGHT
    print("\n🎧 Step 2: Right")
    mute_all(); unmute_mains(1.0)
    time.sleep(0.5); play(tone)

    # SUB (AUX 6)
    print("\n🎧 Step 3: Subwoofer (Bus 6)")
    mute_all(); unmute_sub()
    time.sleep(0.5); play(tone)

    # RESET
    mute_all()
    client.send_message("/lr/mix/pan", 0.5)
    print("\n✅ Finished; all outputs muted.")

if __name__ == "__main__":
    run_test()
