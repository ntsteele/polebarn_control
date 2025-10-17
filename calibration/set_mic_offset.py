#!/usr/bin/env python3
import json, sys
from pathlib import Path

MIC_FILE = Path.home()/ "polebarn_control"/"calibration"/"mic_offsets.json"

def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("Mic1","Mic2"):
        print("Usage: set_mic_offset.py Mic1|Mic2 <offset_dB>")
        sys.exit(1)
    mic = sys.argv[1]
    val = float(sys.argv[2])
    d = {"Mic1": 0.0, "Mic2": 0.0}
    if MIC_FILE.exists():
        try:
            d.update(json.loads(MIC_FILE.read_text()))
        except Exception:
            pass
    d[mic] = val
    MIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    MIC_FILE.write_text(json.dumps(d, indent=2))
    print(f"Saved {MIC_FILE} → {mic} offset = {val:+.2f} dB")

if __name__ == "__main__":
    main()
