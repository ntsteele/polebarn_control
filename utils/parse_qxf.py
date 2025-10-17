#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import json
from pathlib import Path

def parse_qxf(path: Path):
    """Parse a QLC+ fixture definition (.qxf) for channels, modes, and metadata."""
    path = Path(path)
    if not path.exists():
        return {"error": f"Fixture file not found: {path}"}

    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception as e:
        return {"error": f"Failed to parse {path}: {e}"}

    def strip_ns(tag):
        return tag.split('}', 1)[-1] if '}' in tag else tag

    for elem in root.iter():
        elem.tag = strip_ns(elem.tag)

    info = {
        "manufacturer": root.findtext("Manufacturer", "Unknown"),
        "model": root.findtext("Model", "Unknown"),
        "type": root.findtext("Type", "Generic"),
        "channels": [],
        "modes": []
    }

    # ─── Channels ──────────────────────────────
    for ch in root.findall(".//Channel"):
        ch_name = ch.findtext("Name", "Unnamed")
        group_elem = ch.find("Group")
        group = group_elem.attrib.get("Byte") if group_elem is not None else ""
        group_name = group_elem.text if group_elem is not None else "Unknown"

        caps = []
        for cap in ch.findall("Capability"):
            caps.append({
                "min": cap.attrib.get("Min", "0"),
                "max": cap.attrib.get("Max", "255"),
                "name": cap.text or ""
            })

        info["channels"].append({
            "name": ch_name,
            "group": group_name,
            "byte": group,
            "capabilities": caps
        })

    # ─── Modes ─────────────────────────────────
    for mode in root.findall(".//Mode"):
        mode_name = mode.attrib.get("Name", "Unnamed Mode")
        mode_channels = []
        for ch in mode.findall("Channel"):
            mode_channels.append({
                "number": ch.attrib.get("Number"),
                "name": ch.attrib.get("Name", "")
            })
        info["modes"].append({
            "name": mode_name,
            "channels": mode_channels
        })

    info["summary"] = {
        "manufacturer": info["manufacturer"],
        "model": info["model"],
        "channel_count": len(info["channels"]),
        "mode_count": len(info["modes"])
    }

    return info

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python parse_qxf.py <fixture_file.qxf>")
        sys.exit(1)
    data = parse_qxf(Path(sys.argv[1]))
    print(json.dumps(data, indent=2))
