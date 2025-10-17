#!/usr/bin/env python3
"""
Audio I/O helper for XR18 USB playback.
Plays tones or sweeps safely via /rtn/aux (USB 17/18).
"""
import os, subprocess, numpy as np, soundfile as sf

SAMPLE_RATE = 48000
XR18_DEVICE = "plughw:CARD=X18XR18,DEV=0"
DATA_DIR = os.path.expanduser("~/polebarn_control/data")
os.makedirs(DATA_DIR, exist_ok=True)

def generate_tone(freq=1000, duration=3.0, gain=0.03):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    tone = (np.sin(2 * np.pi * freq * t) * gain).astype(np.float32)
    filename = os.path.join(DATA_DIR, f"tone_{freq}Hz.wav")
    sf.write(filename, tone, SAMPLE_RATE)
    return filename

def play_audio(wav_path):
    """Play file through XR18 USB return."""
    subprocess.run(["aplay", "-D", XR18_DEVICE, wav_path], check=True)

def play_tone(freq=1000, duration=3.0, gain=0.03):
    path = generate_tone(freq, duration, gain)
    print(f"▶ {freq} Hz tone → XR18 USB (gain={gain:.3f})")
    play_audio(path)
    print("✅ done")

if __name__ == "__main__":
    play_tone()
