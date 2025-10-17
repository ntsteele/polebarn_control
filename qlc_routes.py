#!/usr/bin/env python3
from flask import Blueprint, jsonify, request
from pythonosc import udp_client
from utils.parse_qxw import parse_qlc_workspace

qlc_bp = Blueprint("qlc", __name__)

QLC_OSC_IP = "127.0.0.1"
QLC_OSC_PORT = 7700
osc_client = udp_client.SimpleUDPClient(QLC_OSC_IP, QLC_OSC_PORT)

# ───────────────────────────────────────────────
# QLC+ Functions & OSC
# ───────────────────────────────────────────────
@qlc_bp.route("/api/qlc/functions", methods=["GET"])
def api_qlc_functions():
    return jsonify(parse_qlc_workspace())

@qlc_bp.post("/api/qlc/trigger")
def api_qlc_trigger():
    """Trigger QLC+ Function via OSC."""
    data = request.get_json(force=True)
    fid = data.get("id")
    if fid is None:
        return jsonify({"ok": False, "err": "Missing id"}), 400
    try:
        osc_client.send_message(f"/qlcplus/function/{fid}/start", [])
        print(f"[OSC] Triggered Function ID {fid}")
        return jsonify({"ok": True, "id": fid})
    except Exception as e:
        print(f"[ERR] OSC send failed: {e}")
        return jsonify({"ok": False, "err": str(e)}), 500


@qlc_bp.route("/api/qlc/info", methods=["GET"])
def api_qlc_info():
    """Return summary info for Config + Diagnostics pages."""
    data = parse_qlc_workspace()
    data["timestamp"] = __import__("time").strftime("%H:%M:%S")
    return jsonify(data)
