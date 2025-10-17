#!/usr/bin/env python3
"""
scene_parser.py — parse Behringer X AIR .scn files (XR18 format)
Extract channel, bus, DCA, and FX return names for Polebarn integration.
"""

import re, sys, json

def parse_scene(path):
    result = {
        "channels": {},
        "buses": {},
        "dcas": {},
        "fx": {},
    }

    # Match: /ch/01/config "Name" ...
    ch_pattern = re.compile(r"^/ch/(\d{2})/config\s+\"([^\"]+)\"")
    # Match: /bus/01/config "Name" ...
    bus_pattern = re.compile(r"^/bus/(\d{2})/config\s+\"([^\"]+)\"")
    # Match: /dca/1/config "Name"
    dca_pattern = re.compile(r"^/dca/(\d{1})/config\s+\"([^\"]+)\"")
    # Match: /fxrtn/1/config "Name"
    fx_pattern = re.compile(r"^/fxrtn/(\d{1})/config\s+\"([^\"]+)\"")

    with open(path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if m := ch_pattern.match(line):
                result["channels"][m.group(1)] = m.group(2)
            elif m := bus_pattern.match(line):
                result["buses"][m.group(1)] = m.group(2)
            elif m := dca_pattern.match(line):
                result["dcas"][m.group(1)] = m.group(2)
            elif m := fx_pattern.match(line):
                result["fx"][m.group(1)] = m.group(2)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: scene_parser.py file.scn")
        sys.exit(1)

    path = sys.argv[1]
    data = parse_scene(path)
    print(json.dumps(data, indent=2))
