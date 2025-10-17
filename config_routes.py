#!/usr/bin/env python3
from flask import Blueprint, request, jsonify, render_template
import subprocess, os, yaml

cfg_bp = Blueprint("config", __name__)

MODE_FILE = "/etc/default/polebarn_mode"
CONFIG_PATH = "/home/pi/polebarn_control/config.yaml"

# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────
def read_mode():
    try:
        if os.path.exists(MODE_FILE):
            with open(MODE_FILE) as f:
                for line in f:
                    if line.strip().startswith("POLEBARN_MODE="):
                        return line.strip().split("=")[1]
    except Exception:
        pass
    return "kiosk"

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

# ───────────────────────────────────────────────
# Web Page
# ───────────────────────────────────────────────
@cfg_bp.route("/config")
def config_page():
    cfg = load_config()
    beat_source = cfg.get("audio", {}).get("beat_input", "xr18")
    current_mode = read_mode()

    xair = cfg.get("xair", {"ip": "192.168.4.136", "port": 10024})
    qlc = cfg.get("qlc", {"host": "localhost", "web_port": 9999})
    osc = cfg.get("osc", {"host": "127.0.0.1", "port": 7700})

    cfg_text = ""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg_text = f.read()

    qlc_info = {"summary": {}}
    return render_template(
        "config.html",
        cfg_text=cfg_text,
        qlc_info=qlc_info,
        beat_source=beat_source,
        current_mode=current_mode,
        xair=xair,
        qlc=qlc,
        osc=osc
    )

# ───────────────────────────────────────────────
# API Endpoints
# ───────────────────────────────────────────────
@cfg_bp.route("/api/config/mode", methods=["POST"])
def change_mode():
    mode = request.form.get("mode", "").strip()
    if mode not in ("gui", "kiosk", "headless"):
        return jsonify({"ok": False, "err": "Invalid mode"}), 400
    try:
        with open(MODE_FILE, "w") as f:
            f.write(f"POLEBARN_MODE={mode}\n")
        subprocess.run(["sudo", "systemctl", "restart", "qlcplus.service"], check=True)
        return jsonify({"ok": True, "mode": mode})
    except Exception as e:
        return jsonify({"ok": False, "err": str(e)})

@cfg_bp.route("/api/config/mode", methods=["GET"])
def get_mode():
    return jsonify({"ok": True, "mode": read_mode()})

@cfg_bp.route("/api/config/beat_source", methods=["POST"])
def set_beat_source():
    src = request.form.get("source", "").strip()
    if src not in ("xr18", "irig_shared"):
        return jsonify({"ok": False, "err": "Invalid source"}), 400
    try:
        cfg = load_config()
        cfg.setdefault("audio", {})["beat_input"] = src
        save_config(cfg)
        subprocess.run(["sudo", "systemctl", "restart", "polebarn-beat-detect.service"], check=False)
        return jsonify({"ok": True, "source": src})
    except Exception as e:
        return jsonify({"ok": False, "err": str(e)})

@cfg_bp.route("/api/config/beat_source", methods=["GET"])
def get_beat_source():
    cfg = load_config()
    src = cfg.get("audio", {}).get("beat_input", "xr18")
    return jsonify({"ok": True, "source": src})

@cfg_bp.route("/api/config/connections", methods=["POST"])
def save_connections():
    """Save XAir / QLC / OSC connection info."""
    try:
        cfg = load_config()
        cfg.setdefault("xair", {})["ip"] = request.form.get("xair_ip", "192.168.4.136")
        cfg["xair"]["port"] = int(request.form.get("xair_port", 10024))
        cfg.setdefault("qlc", {})["host"] = request.form.get("qlc_host", "localhost")
        cfg["qlc"]["web_port"] = int(request.form.get("qlc_port", 9999))
        cfg.setdefault("osc", {})["host"] = request.form.get("osc_host", "127.0.0.1")
        cfg["osc"]["port"] = int(request.form.get("osc_port", 7700))
        save_config(cfg)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "err": str(e)})
