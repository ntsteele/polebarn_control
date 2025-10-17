#!/usr/bin/env python3
import time, json, os, random

TELEMETRY_PATH = "/tmp/polebarn_status"
SCENES = ["Chill Amber", "Party Blue", "Warm White", "Strobe FX", "Rock Show"]

def write_telemetry(filename, data):
    os.makedirs(TELEMETRY_PATH, exist_ok=True)
    with open(os.path.join(TELEMETRY_PATH, filename), "w") as f:
        json.dump(data, f)

if __name__ == "__main__":
    print("[LightingAuto] running...")
    while True:
        scene = random.choice(SCENES)
        write_telemetry("lighting.json", {
            "scene": scene,
            "timestamp": time.time()
        })
        time.sleep(2)
