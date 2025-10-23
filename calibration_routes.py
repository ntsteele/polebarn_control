#!/usr/bin/env python3
"""Routes for Deep Venue auto-calibration demo."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from calibration import deep_venue_autocal

calibration_bp = Blueprint("calibration", __name__)


@calibration_bp.route("/calibration")
def calibration_dashboard():
    """Serve the calibration control panel."""
    return render_template("calibration.html", title="Calibration")


@calibration_bp.route("/calibrate/deep_venue", methods=["POST"])
def deep_venue_calibrate():
    """Run the Deep Venue auto-calibration routine."""
    try:
        result = deep_venue_autocal.run()
    except Exception as exc:  # pragma: no cover - network dependent
        return jsonify({"status": "error", "msg": str(exc)}), 500
    if not result:
        return jsonify({"status": "error", "msg": "XR18 not found"}), 404
    return jsonify({"status": "ok", "results": result})
