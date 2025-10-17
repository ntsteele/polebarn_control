#!/usr/bin/env python3
"""
scene_loader.py — merges parsed XR18 scene data into config.yaml
Safely preserves existing keys (IP, port, features, web settings, etc.)
while updating only channel/bus/DCA names.
"""

import yaml, sys, json
from pathlib import Path
from yaml.representer import SafeRepresenter

CONFIG_PATH = Path.home() / "polebarn_control" / "config.yaml"

# --- Always quote zero-padded keys in YAML output ---
class QuotedString(str):
    pass

def quoted_scalar_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")

yaml.add_representer(QuotedString, quoted_scalar_representer, Dumper=yaml.SafeDumper)

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}
    return cfg

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)

def force_padded_keys(section):
    out = {}
    for k, v in section.items():
        try:
            key = QuotedString(f"{int(k):02d}")  # pad and quote
        except ValueError:
            key = QuotedString(str(k))
        out[key] = str(v)
    return out

def merge_scene(scene_data, cfg):
    # Preserve existing keys
    xair = cfg.setdefault("xair", {})
    xair.setdefault("ip", "192.168.4.136")
    xair.setdefault("port", 10024)
    xair.setdefault("channel_names", {})
    xair.setdefault("bus_names", {})
    xair.setdefault("dca_names", {})

    # Merge parsed names
    if "channels" in scene_data and scene_data["channels"]:
        xair["channel_names"] = force_padded_keys(scene_data["channels"])
    if "buses" in scene_data and scene_data["buses"]:
        xair["bus_names"] = force_padded_keys(scene_data["buses"])
    if "dcas" in scene_data and scene_data["dcas"]:
        xair["dca_names"] = force_padded_keys(scene_data["dcas"])
    if "fx" in scene_data and scene_data["fx"]:
        xair["fx_names"] = force_padded_keys(scene_data["fx"])

    xair["scene_path"] = "scene.json"
    cfg["xair"] = xair

    # Keep non-xair data intact
    cfg.setdefault("features", {})
    cfg.setdefault("web", {"brand": "Polebarn Signature", "theme": "dark", "port": 5055})
    cfg.setdefault("paths", {"scene_json": "scene.json", "telemetry_dir": "/tmp/polebarn_status"})

    return cfg


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: scene_loader.py scene.json")
        sys.exit(1)

    scene_file = Path(sys.argv[1])
    if not scene_file.exists():
        sys.exit(f"[!] File not found: {scene_file}")

    with open(scene_file) as f:
        scene_data = json.load(f)
    cfg = load_config()
    cfg = merge_scene(scene_data, cfg)
    save_config(cfg)

    print(f"[scene_loader] Updated {CONFIG_PATH}")
    print(yaml.safe_dump(cfg["xair"], sort_keys=False))
