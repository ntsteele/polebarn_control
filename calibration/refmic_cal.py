#!/usr/bin/env python3
import numpy as np, sounddevice as sd, json, os
from core.audio_io import SAMPLE_RATE

CAL_FILE = "configs/equipment.json"

def play_tone(freq=1000, level_db=-12, dur=5):
    """Play a reference sine tone."""
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur))
    tone = np.sin(2 * np.pi * freq * t) * (10 ** (level_db / 20))
    sd.play(tone, samplerate=SAMPLE_RATE, blocking=True)

def main():
    print("Playing 1kHz reference tone… measure with phone SPL app.")
    play_tone()
    user_db = float(input("Enter SPL reading from phone (dB): "))
    if not os.path.exists("configs"):
        os.makedirs("configs")
    offset = 80 - user_db
    with open(CAL_FILE, "w") as f:
        json.dump({"mic_offset_dB": offset}, f, indent=2)
    print(f"Saved calibration offset: {offset:+.2f} dB → {CAL_FILE}")

if __name__ == "__main__":
    main()
