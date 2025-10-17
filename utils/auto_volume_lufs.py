#!/usr/bin/env python3
import time, json, os, random

TELEMETRY_PATH = "/tmp/polebarn_status"

def write_telemetry(filename, data):
    os.makedirs(TELEMETRY_PATH, exist_ok=True)
    with open(os.path.join(TELEMETRY_PATH, filename), "w") as f:
        json.dump(data, f)

def measure_lufs():
    # placeholder: replace with real LUFS measurement
    return round(-20 + random.random() * 4 - 2, 2)

def current_gain_adjustment():
    # placeholder: pretend it’s auto-balancing
    return round(random.uniform(-1.5, 1.5), 2)

if __name__ == "__main__":
    print("[AutoVolume] running...")
    while True:
        lufs = measure_lufs()
        gain = current_gain_adjustment()
        write_telemetry("volume.json", {
            "lufs": lufs,
            "gain": gain,
            "timestamp": time.time()
        })
        time.sleep(1)
