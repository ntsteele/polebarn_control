#!/usr/bin/env python3
"""Deep Venue auto-calibration demo utilities."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from pythonosc.udp_client import SimpleUDPClient

from core.xair_probe import find_xair_ip, update_config

XR18_PORT = 10024
RESULTS_FILE = Path(os.path.expanduser("~/polebarn_control/calibration/deep_venue_results.json"))


def run(timeout: float = 3) -> Optional[Dict[str, Dict[str, float]]]:
    """Execute the demo calibration workflow.

    Returns the generated EQ dataset or ``None`` if the XR18 mixer could not
    be discovered.
    """

    ip = find_xair_ip(timeout=timeout)
    if not ip:
        print("❌ XR18 not found on network.")
        return None

    update_config(ip)
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    client = SimpleUDPClient(ip, XR18_PORT)
    print(f"🎚️ Calibrating via XR18 at {ip}")

    channels = {"LR": [1, 2], "Sub": [15], "Rear": [13]}
    eq_results: Dict[str, Dict[str, float]] = {}
    for name, chs in channels.items():
        print(f"• Measuring {name} ...")
        time.sleep(1.5)
        eq_results[name] = {
            "gain_trim": float(np.random.uniform(-2, 2)),
            "eq_offset": float(np.random.uniform(-1, 1)),
        }

    with RESULTS_FILE.open("w") as f:
        json.dump(eq_results, f, indent=2)
    print("✅ Deep Venue results saved.")

    for name, vals in eq_results.items():
        gain = vals["gain_trim"]
        for ch in channels[name]:
            client.send_message(f"/ch/{ch}/mix/fader", [gain])
    print("✅ EQ applied.")
    return eq_results


if __name__ == "__main__":
    run()
