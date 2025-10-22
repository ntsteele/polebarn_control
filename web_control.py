#!/usr/bin/env python3
"""
Polebarn Control — Modular Flask Application
--------------------------------------------
Main entry point for the Polebarn Control system.
"""

import os, threading
from pathlib import Path
from flask import Flask
from flask_socketio import SocketIO

# ───────────────────────────────────────────────
# App Initialization
# ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
app = Flask(
    __name__,
    static_folder=str(ROOT / "static"),
    template_folder=str(ROOT / "templates")
)
app.config["SECRET_KEY"] = "polebarn-secret"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ───────────────────────────────────────────────
# Global State (temporary until config.yaml sync)
# ───────────────────────────────────────────────
_state_lock = threading.Lock()
_state = {
    "features": {
        "autovolume_enabled": False,
        "beat_enabled": False,
        "lighting_enabled": False
    },
    "xair": {
        "ip": "192.168.4.136",
        "port": 10024
    },
    "web": {
        "brand": "Polebarn Signature",
        "theme": "dark"
    }
}

@app.context_processor
def inject_state():
    """Expose state globally to Jinja templates."""
    with _state_lock:
        return dict(state=_state)

# ───────────────────────────────────────────────
# Import Blueprints
# ───────────────────────────────────────────────
from home_routes import home_bp
from qlc_routes import qlc_bp
from system_routes import sys_bp
from config_routes import cfg_bp
from automation_routes import auto_bp
from diagnostics_routes import diag_bp
from playground_routes import playground_bp  # NEW
from calibration_routes import calibration_bp

# ───────────────────────────────────────────────
# Register Blueprints
# ───────────────────────────────────────────────
app.register_blueprint(home_bp)
app.register_blueprint(qlc_bp)
app.register_blueprint(sys_bp)
app.register_blueprint(cfg_bp)
app.register_blueprint(auto_bp)
app.register_blueprint(diag_bp)
app.register_blueprint(playground_bp)  # NEW
app.register_blueprint(calibration_bp)

# ───────────────────────────────────────────────
# SocketIO Events
# ───────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    print("[socketio] Client connected")

@socketio.on("ui_action")
def handle_ui_action(data):
    """Receive UI events from client (button/slider/toggle)."""
    print(f"[socketio] UI action: {data}")
    socketio.emit("ui_feedback", {"status": "ok", "echo": data})

# ───────────────────────────────────────────────
# Run Application
# ───────────────────────────────────────────────
if __name__ == "__main__":
    print("[Polebarn] Web Control starting on :5055")
    socketio.run(app, host="0.0.0.0", port=5055)
