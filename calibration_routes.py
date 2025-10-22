#!/usr/bin/env python3
"""Calibration blueprint providing UI and API endpoints."""
from __future__ import annotations

import json
import random
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, Response, jsonify, render_template, request, send_file
from flask_socketio import SocketIO
from core import xair_client
from eq_presets import available_presets, get_preset, merge_with_current

ROOT = Path(__file__).resolve().parent
CALIBRATION_DIR = ROOT / "calibration"
LOG_DIR = CALIBRATION_DIR / "logs"
SNAPSHOT_DIR = ROOT / "snapshots"
CAL_STATE_PATH = CALIBRATION_DIR / "calibration_state.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

calibration_bp = Blueprint("calibration", __name__)

_socketio: SocketIO | None = None
_socket_handlers_registered = False


def _emit(event: str, payload: Dict[str, Any], namespace: str = "/ws/calibration") -> None:
    """Safely emit Socket.IO events when the server is initialized."""
    if _socketio is not None:
        _socketio.emit(event, payload, namespace=namespace)


# ──────────────────────────────────────────────────────────────────────
# Persistent calibration state helpers
# ──────────────────────────────────────────────────────────────────────
_DEFAULT_CAL_STATE: Dict[str, Dict[str, Any]] = {
    "mic_gain_adjuster": {
        "label": "Mic Gain Adjuster",
        "value": "Not yet calibrated",
        "last_run": None,
    },
    "mic_db_calibration": {
        "label": "Mic dB Calibration",
        "value": "Not yet calibrated",
        "last_run": None,
    },
    "venue_db_level": {
        "label": "Venue dB Level Setting",
        "value": "Not yet calibrated",
        "last_run": None,
    },
    "venue_deep": {
        "label": "Venue Deep Calibration",
        "value": "Not yet calibrated",
        "last_run": None,
    },
}

_calibration_jobs: Dict[str, threading.Thread] = {}
_calibration_job_flags: Dict[str, threading.Event] = {}


def _load_cal_state() -> Dict[str, Dict[str, Any]]:
    if CAL_STATE_PATH.exists():
        try:
            with CAL_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                for key, defaults in _DEFAULT_CAL_STATE.items():
                    data.setdefault(key, defaults.copy())
                return data
        except json.JSONDecodeError:
            pass
    return {k: v.copy() for k, v in _DEFAULT_CAL_STATE.items()}


def _save_cal_state(data: Dict[str, Dict[str, Any]]) -> None:
    tmp = CAL_STATE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(CAL_STATE_PATH)


# ──────────────────────────────────────────────────────────────────────
# Gain trim background job
# ──────────────────────────────────────────────────────────────────────
class GainTrimJob:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._log = deque(maxlen=400)
        self._metrics: Dict[str, Dict[str, float]] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._log_path: Path | None = None

    # properties ---------------------------------------------------------
    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def log_tail(self) -> List[str]:
        with self._lock:
            return list(self._log)[-40:]

    def metrics(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return json.loads(json.dumps(self._metrics))

    def log_path(self) -> Path | None:
        with self._lock:
            return self._log_path

    # helpers ------------------------------------------------------------
    def _append_log(self, line: str) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        entry = f"[{ts}] {line}"
        with self._lock:
            self._log.append(entry)
            if self._log_path:
                with self._log_path.open("a", encoding="utf-8") as f:
                    f.write(entry + "\n")
        _emit("calibration_log", {"line": entry})

    def _set_metric(self, channel: int, peak: float) -> None:
        with self._lock:
            self._metrics[str(channel)] = {"peak_dbfs": peak}
        _emit("calibration_metrics", {"metrics": self.metrics()})

    def start(self, target_dbfs: float, channels: List[int], safety_cap: float) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(target_dbfs, channels, safety_cap),
            daemon=True,
        )
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self._log_path = LOG_DIR / f"gain_trim_{ts}.log"
        with self._lock:
            self._log.clear()
            self._metrics.clear()
            self._running = True
        self._append_log("Gain trim started")
        self._thread.start()
        return True

    def stop(self) -> None:
        if not self.running:
            return
        self._append_log("Stopping on user request…")
        self._stop.set()

    def _run(self, target_dbfs: float, channels: List[int], safety_cap: float) -> None:
        fake_levels = {ch: random.uniform(-30.0, -10.0) for ch in channels}
        iteration = 0
        while not self._stop.is_set() and iteration < 30:
            iteration += 1
            for ch in channels:
                adjustment = random.uniform(-0.5, 0.5)
                fake_levels[ch] = max(safety_cap - 6.0, min(safety_cap, fake_levels[ch] + adjustment))
                self._set_metric(ch, round(fake_levels[ch], 2))
                self._append_log(
                    f"Ch {ch:02d}: peak {fake_levels[ch]:.2f} dBFS (target {target_dbfs:.1f})"
                )
            time.sleep(0.5)
        if self._stop.is_set():
            self._append_log("Gain trim cancelled")
        else:
            self._append_log("Gain trim completed successfully")
        with self._lock:
            self._running = False
        _emit("calibration_finished", {"job": "gain_trim"})


_GAIN_TRIM = GainTrimJob()


# ──────────────────────────────────────────────────────────────────────
# Socket.IO namespace
# ──────────────────────────────────────────────────────────────────────
def _register_socket_handlers(sock: SocketIO) -> None:
    global _socket_handlers_registered
    if _socket_handlers_registered:
        return

    namespace = "/ws/calibration"

    @sock.on("connect", namespace=namespace)
    def _calibration_connect():  # type: ignore[misc]
        _emit("calibration_log", {"line": "[socket] calibration channel ready"})

    _socket_handlers_registered = True


# ──────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────
@calibration_bp.route("/calibration")
def calibration_page():
    cfg = xair_client.get_calibration_config()
    quick_defaults = cfg.get("quick_trim", {})
    return render_template(
        "calibration.html",
        presets=available_presets(),
        quick_defaults=quick_defaults,
    )


@calibration_bp.route("/api/cal/gain-trim/start", methods=["POST"])
def gain_trim_start():
    payload = request.get_json(force=True, silent=True) or {}
    target = float(payload.get("target_dbfs", -12.0))
    safety_cap = float(payload.get("safety_dbfs_cap", -6.0))
    channels = payload.get("channels") or []
    if not isinstance(channels, list) or not channels:
        return jsonify({"ok": False, "err": "channels list required"}), 400
    channel_ids: List[int] = []
    for ch in channels:
        try:
            channel_ids.append(int(ch))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "err": f"invalid channel: {ch}"}), 400
    if not _GAIN_TRIM.start(target, channel_ids, safety_cap):
        return jsonify({"ok": False, "err": "gain trim already running"}), 409
    return jsonify({"ok": True})


@calibration_bp.route("/api/cal/gain-trim/stop", methods=["POST"])
def gain_trim_stop():
    _GAIN_TRIM.stop()
    return jsonify({"ok": True})


@calibration_bp.route("/api/cal/gain-trim/status")
def gain_trim_status():
    return jsonify(
        {
            "running": _GAIN_TRIM.running,
            "log_tail": _GAIN_TRIM.log_tail(),
            "metrics": _GAIN_TRIM.metrics(),
        }
    )


@calibration_bp.route("/api/cal/gain-trim/log")
def gain_trim_log_download():
    log_path = _GAIN_TRIM.log_path()
    if log_path and log_path.exists():
        return send_file(log_path, mimetype="text/plain", as_attachment=True, download_name=log_path.name)
    # fallback to current tail
    return Response("\n".join(_GAIN_TRIM.log_tail()), mimetype="text/plain")


# ──────────────────────────────────────────────────────────────────────
# Calibration summaries and reruns
# ──────────────────────────────────────────────────────────────────────
@calibration_bp.route("/api/calibrations/summary")
def calibration_summary():
    data = _load_cal_state()
    return jsonify(
        {
            "calibrations": [
                {
                    "id": key,
                    "label": value["label"],
                    "value": value.get("value"),
                    "last_run": value.get("last_run"),
                    "running": _calibration_jobs.get(key) is not None and _calibration_jobs[key].is_alive(),
                }
                for key, value in data.items()
            ]
        }
    )


def _simulate_calibration(cal_id: str, duration: float = 3.0) -> None:
    state = _load_cal_state()
    label = state.get(cal_id, {}).get("label", cal_id)
    _emit("calibration_log", {"line": f"Starting {label} calibration"})
    start = time.time()
    while time.time() - start < duration:
        if _calibration_job_flags.get(cal_id) and _calibration_job_flags[cal_id].is_set():
            _emit("calibration_log", {"line": f"{label} cancelled"})
            break
        _emit("calibration_log", {"line": f"{label}: analysing…"})
        time.sleep(0.6)
    state = _load_cal_state()
    new_value = round(random.uniform(-3.0, 3.0), 2)
    state.setdefault(cal_id, {}).update(
        {
            "value": f"Offset {new_value:+.2f} dB",
            "last_run": datetime.utcnow().isoformat() + "Z",
        }
    )
    _save_cal_state(state)
    _emit("calibration_log", {"line": f"{label} calibration complete: {new_value:+.2f} dB"})
    _calibration_jobs.pop(cal_id, None)
    _calibration_job_flags.pop(cal_id, None)


@calibration_bp.route("/api/calibrations/<cal_id>/run", methods=["POST"])
def calibration_run(cal_id: str):
    state = _load_cal_state()
    if cal_id not in state:
        return jsonify({"ok": False, "err": "unknown calibration"}), 404
    if cal_id in _calibration_jobs and _calibration_jobs[cal_id].is_alive():
        return jsonify({"ok": False, "err": "calibration already running"}), 409
    flag = threading.Event()
    _calibration_job_flags[cal_id] = flag
    job = threading.Thread(target=_simulate_calibration, args=(cal_id,), daemon=True)
    _calibration_jobs[cal_id] = job
    job.start()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────────────────────────────
# EQ endpoints
# ──────────────────────────────────────────────────────────────────────
@calibration_bp.route("/api/eq/current")
def eq_current():
    return jsonify(xair_client.get_all_eq())


@calibration_bp.route("/api/eq/preview", methods=["POST"])
def eq_preview():
    payload = request.get_json(force=True, silent=True) or {}
    mode = payload.get("mode", "").strip().lower()
    if not mode:
        return jsonify({"ok": False, "err": "mode required"}), 400
    try:
        preset = get_preset(mode)
    except KeyError as exc:
        return jsonify({"ok": False, "err": str(exc)}), 404
    current = xair_client.get_all_eq()
    merged = merge_with_current(
        {
            "lr": current["lr"].get("bands", []),
            "bus_05": current["rear"].get("bands", []),
            "bus_06": current["sub"].get("bands", []),
        },
        preset,
    )
    return jsonify({"ok": True, "filters": merged})


@calibration_bp.route("/api/eq/apply", methods=["POST"])
def eq_apply():
    payload = request.get_json(force=True, silent=True) or {}
    filters = payload.get("filters")
    confirmation = (payload.get("confirmation") or "").strip().upper()
    dry_run = request.args.get("dry_run", "0").lower() in {"1", "true", "yes"}
    if not isinstance(filters, dict):
        return jsonify({"ok": False, "err": "filters payload required"}), 400
    if not dry_run and confirmation != "APPLY":
        return jsonify({"ok": False, "err": "confirmation text 'APPLY' is required"}), 400

    snapshot = xair_client.snapshot_all_eq(write_file=not dry_run)
    applied = xair_client.apply_filters(filters, dry_run=dry_run)
    response = {"ok": True, "dry_run": dry_run, "applied": applied, "snapshot": snapshot}
    if not dry_run:
        response["message"] = "Filters applied"
    else:
        response["message"] = "Dry run only; no mixer changes were made"
    return jsonify(response)


@calibration_bp.route("/api/eq/rollback", methods=["POST"])
def eq_rollback():
    try:
        snapshot = xair_client.restore_last_snapshot()
    except FileNotFoundError:
        return jsonify({"ok": False, "err": "No snapshot available to rollback"}), 409
    return jsonify({"ok": True, "snapshot": snapshot})


# ──────────────────────────────────────────────────────────────────────
# Deep venue analysis viewer
# ──────────────────────────────────────────────────────────────────────
@calibration_bp.route("/api/deep-venue/analyses")
def deep_venue_analyses():
    runs: List[Dict[str, Any]] = []
    for path in sorted(CALIBRATION_DIR.glob("venue_*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except json.JSONDecodeError:
            continue
        runs.append(
            {
                "id": path.stem,
                "path": str(path.relative_to(ROOT)),
                "timestamp": payload.get("timestamp"),
                "summary": payload.get("summary", {}),
            }
        )
    return jsonify({"runs": runs})


@calibration_bp.route("/api/deep-venue/analysis/<run_id>")
def deep_venue_analysis(run_id: str):
    path = CALIBRATION_DIR / f"{run_id}.json"
    if not path.exists():
        return jsonify({"ok": False, "err": "analysis not found"}), 404
    with path.open("r", encoding="utf-8") as f:
        try:
            payload = json.load(f)
        except json.JSONDecodeError:
            return jsonify({"ok": False, "err": "analysis unreadable"}), 500
    return jsonify({"ok": True, "analysis": payload})


def create_calibration_blueprint(sock: SocketIO) -> Blueprint:
    """Factory used by the application to initialise the calibration blueprint."""
    global _socketio
    _socketio = sock
    _register_socket_handlers(sock)
    return calibration_bp
