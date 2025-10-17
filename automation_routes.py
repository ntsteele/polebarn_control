#!/usr/bin/env python3
from flask import Blueprint, render_template, jsonify
import time, json, os, glob

auto_bp = Blueprint("automation", __name__)

STATUS_PATH = "/tmp/polebarn_status"

def read_json_safe(path):
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

@auto_bp.route("/automation")
def automation_page():
    return render_template("automation.html")

@auto_bp.route("/api/automation/feed")
def automation_feed():
    """Return real-time automation feed based on actual telemetry."""
    feed = []
    now = time.time()

    # --- Beat info ---
    beat_data = read_json_safe(f"{STATUS_PATH}/beat.json")
    bpm = beat_data.get("bpm")
    intensity = beat_data.get("intensity", 0)
    conf = beat_data.get("confidence", 0)
    if bpm:
        feed.append({"time": time.strftime("%H:%M:%S"),
                     "event": f"Beat steady at {bpm} BPM (conf {conf:.2f})"})

    # --- Scene changes ---
    scene_log = read_json_safe(f"{STATUS_PATH}/scene_log.json")
    if isinstance(scene_log, list):
        recent = [e for e in scene_log if (now - e.get("ts", 0)) < 15]
        for e in recent:
            feed.append({"time": time.strftime("%H:%M:%S", time.localtime(e["ts"])),
                         "event": f'Scene changed → {e.get("scene","Unknown")}'})

    # --- Audio changes ---
    audio_events = read_json_safe(f"{STATUS_PATH}/audio_events.json")
    if isinstance(audio_events, list):
        recent = [e for e in audio_events if (now - e.get("ts", 0)) < 15]
        for e in recent:
            if "fader" in e:
                feed.append({"time": time.strftime("%H:%M:%S", time.localtime(e["ts"])),
                             "event": f'{e["channel"]} fader adjusted {e["fader"]:+.1f} dB'})
            elif e.get("mute") is not None:
                state = "Muted" if e["mute"] else "Unmuted"
                feed.append({"time": time.strftime("%H:%M:%S", time.localtime(e["ts"])),
                             "event": f'{e["channel"]} {state}'})

    # Sort newest first, limit size
    feed = sorted(feed, key=lambda e: e["time"], reverse=True)[:10]

    return jsonify({
        "feed": feed,
        "beat_info": {"bpm": bpm, "intensity": intensity}
    })
