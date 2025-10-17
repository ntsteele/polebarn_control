#!/usr/bin/env python3
from flask import Blueprint, jsonify, request
import subprocess, psutil, time, json
from datetime import timedelta
from pathlib import Path

sys_bp = Blueprint("system", __name__)

# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────
def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return ""

def get_service_status(service):
    try:
        result = run_cmd(["systemctl", "is-active", service])
        if "active" in result:
            return "active"
        elif "activating" in result:
            return "activating"
        else:
            return "inactive"
    except Exception:
        return "unknown"

# ───────────────────────────────────────────────
# API Endpoints
# ───────────────────────────────────────────────
@sys_bp.route("/api/system/status")
def api_system_status():
    try:
        temp_out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
        temp = float(temp_out.split("=")[1].split("'")[0])
    except Exception:
        temp = 0.0

    try:
        cpu = psutil.cpu_percent(interval=0.4)
        mem = psutil.virtual_memory().percent
    except Exception:
        cpu, mem = 0.0, 0.0

    data = {
        "cpu": cpu,
        "mem": mem,
        "temp": temp,
        "uptime": str(timedelta(seconds=int(time.time() - psutil.boot_time()))),
        "polebarn": get_service_status("polebarn-web.service"),
        "qlcplus": get_service_status("qlcplus.service"),
        "auto_volume": get_service_status("polebarn-auto-volume.service"),
        "beat_detect": get_service_status("polebarn-beat-detect.service"),
        "lighting_auto": get_service_status("polebarn-lighting-auto.service"),
    }

    telemetry_dir = Path("/tmp/polebarn_status")
    for key in ("volume", "beat", "lighting"):
        fpath = telemetry_dir / f"{key}.json"
        try:
            data[f"{key}_info"] = json.load(open(fpath)) if fpath.exists() else {}
        except Exception:
            data[f"{key}_info"] = {}

    return jsonify(data)


@sys_bp.post("/api/system/action")
def api_system_action():
    data = request.get_json(force=True)
    action = data.get("action", "")
    print(f"[system] Received action: {action}")

    actions = {
        "restart_polebarn": ["sudo", "systemctl", "restart", "polebarn-web.service"],
        "restart_qlc": ["sudo", "systemctl", "restart", "qlcplus.service"],
        "stop_qlc": ["sudo", "systemctl", "stop", "qlcplus.service"],
        "reboot_pi": ["sudo", "reboot"],
    }

    if action not in actions:
        return jsonify({"ok": False, "err": f"Invalid action: {action}"}), 400

    try:
        subprocess.Popen(actions[action])
        return jsonify({"ok": True, "action": action})
    except Exception as e:
        print(f"[ERR] system action failed: {e}")
        return jsonify({"ok": False, "err": str(e)}), 500
