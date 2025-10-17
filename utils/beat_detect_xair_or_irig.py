#!/usr/bin/env python3
"""
beat_detect_xair_or_irig.py — Beat telemetry reader
Reads the beat detection service output from /tmp/polebarn_status/beat.json
Used by Flask routes and automation logic.
"""

import json, time
from pathlib import Path

BEAT_FILE = Path("/tmp/polebarn_status/beat.json")

def get_status():
    """Return latest BPM/intensity info from beat detector service."""
    try:
        if not BEAT_FILE.exists():
            return {"bpm": 0, "intensity": 0, "status": "no_file"}
        data = json.loads(BEAT_FILE.read_text())
        age = time.time() - data.get("timestamp", 0)
        data["age"] = round(age, 2)
        data["status"] = "ok" if age < 5 else "stale"
        return data
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(get_status())
