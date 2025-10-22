#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from flask import Blueprint, jsonify, render_template, request
from flask_socketio import Namespace, emit

from analysis.beat_spl import BeatTracker, MasterCoach, SPLTracker
from core.osc_client import XR18

ASV_DATA_ROOT = Path(__file__).resolve().parent
MIX_TEMPLATE_DIR = ASV_DATA_ROOT / "profiles" / "mix_templates"
MODE_DIR = ASV_DATA_ROOT / "profiles" / "modes"
SHOW_DIR = ASV_DATA_ROOT / "shows"


def db_to_linear(db: float) -> float:
    return max(0.0, 10 ** (db / 20.0))


def linear_to_db(linear: float) -> float:
    linear = max(linear, 1e-6)
    return 20.0 * math.log10(linear)


def pan_percent_to_linear(percent: float) -> float:
    return max(0.0, min(1.0, 0.5 + float(percent) / 200.0))


def pan_linear_to_percent(value: float) -> float:
    return round((max(0.0, min(1.0, value)) - 0.5) * 200.0, 1)


@dataclass
class ChannelState:
    id: str
    label: str
    role: str
    xr18_channel: int
    fader_linear: float
    pan_linear: float
    meter_db: float
    suggestion_db: float = 0.0

    @property
    def fader_db(self) -> float:
        return linear_to_db(self.fader_linear)


class ASVState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.templates = self._load_directory(MIX_TEMPLATE_DIR)
        self.modes = self._load_directory(MODE_DIR)
        self.shows = self._load_directory(SHOW_DIR)
        self.channels: List[ChannelState] = []
        self.current_show: Optional[str] = None
        self.current_template: Optional[str] = None
        self.current_mode: Optional[str] = None
        self.master_db: float = 0.0
        self.foh_members: List[Dict[str, float]] = []
        self.spl_tracker = SPLTracker()
        self.beat_tracker = BeatTracker()
        self.master_coach = MasterCoach()
        self._last_tick = time.time()
        self._virtual_phase = 0.0
        self._virtual_bpm = 96.0
        self._spl_snapshot = self.spl_tracker.update(-80.0)
        self._beat_snapshot = self.beat_tracker.decay()
        self._last_master_message = "Initializing"
        self._last_adjust = 0.0
        self._osc: Optional[XR18] = None
        self.ensure_defaults()

    # ── data loading ────────────────────────────────────────────────
    def _load_directory(self, path: Path) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        if not path.exists():
            return out
        for file in sorted(path.glob("*.json")):
            try:
                with open(file) as f:
                    data = json.load(f)
                data.setdefault("id", file.stem)
                out[data["id"]] = data
            except Exception as exc:
                print(f"[ASV] Failed to load {file}: {exc}")
        return out

    def ensure_defaults(self) -> None:
        with self.lock:
            if not self.shows:
                self.current_show = None
                return
            default_show = self.current_show or next(iter(self.shows))
            self._apply_show(default_show)

    # ── OSC helper ─────────────────────────────────────────────────
    def _osc_client(self) -> Optional[XR18]:
        if self._osc is not None:
            return self._osc
        ip = os.environ.get("XAIRMIX_IP", "192.168.4.136")
        try:
            self._osc = XR18(ip)
        except Exception as exc:
            print(f"[ASV] Could not init XR18 client ({exc})")
            self._osc = None
        return self._osc

    # ── show/template/mode selection ───────────────────────────────
    def _apply_show(self, show_id: str) -> None:
        show = self.shows.get(show_id)
        if not show:
            raise ValueError("Unknown show profile")
        template_id = show.get("mix_template") or next(iter(self.templates))
        mode_id = show.get("mode") or next(iter(self.modes))
        template = self.templates.get(template_id)

        self.current_show = show_id
        self.current_template = template_id
        self.current_mode = mode_id
        self.master_db = 0.0
        self.foh_members = list(show.get("foh", []))
        self.channels.clear()

        ref_db = template.get("reference_level_db", -18.0) if template else -18.0
        targets = template.get("targets", {}) if template else {}

        for ch in show.get("channels", []):
            role = ch.get("role", ch.get("id"))
            target = targets.get(role, {"offset_db": 0.0, "pan_hint": 0})
            fader_db = ref_db + target.get("offset_db", 0.0)
            fader_linear = max(0.0, min(1.0, db_to_linear(fader_db)))
            pan = pan_percent_to_linear(target.get("pan_hint", 0.0))
            meter_db = fader_db + random.uniform(-2.0, 2.0)
            self.channels.append(
                ChannelState(
                    id=ch.get("id", ch["label"]),
                    label=ch.get("label", ch.get("id", "Ch")),
                    role=role,
                    xr18_channel=int(ch.get("xr18_channel", 1)),
                    fader_linear=max(0.0, min(1.0, fader_linear)),
                    pan_linear=pan,
                    meter_db=meter_db,
                )
            )

        self.master_coach.set_mode(self.modes.get(mode_id))
        self._apply_master_to_foh()

    def set_show(self, show_id: str) -> None:
        with self.lock:
            self._apply_show(show_id)

    def set_template(self, template_id: str) -> None:
        with self.lock:
            if template_id not in self.templates:
                raise ValueError("Unknown template")
            self.current_template = template_id

    def set_mode(self, mode_id: str) -> None:
        with self.lock:
            if mode_id not in self.modes:
                raise ValueError("Unknown mode")
            self.current_mode = mode_id
            self.master_coach.set_mode(self.modes.get(mode_id))

    # ── channel helpers ────────────────────────────────────────────
    def _template_target(self, role: str) -> float:
        template = self.templates.get(self.current_template or "", {})
        ref = template.get("reference_level_db", -18.0)
        offset = template.get("targets", {}).get(role, {}).get("offset_db", 0.0)
        return ref + offset

    def update_fader(self, channel_id: str, linear_value: float) -> ChannelState:
        with self.lock:
            ch = self._find_channel(channel_id)
            ch.fader_linear = max(0.0, min(1.0, float(linear_value)))
            osc = self._osc_client()
            if osc:
                try:
                    osc.set_channel_fader(ch.xr18_channel, ch.fader_linear)
                except Exception as exc:
                    print(f"[ASV] Failed to set fader ch{ch.xr18_channel}: {exc}")
            return ch

    def nudge_fader_db(self, channel_id: str, delta_db: float) -> ChannelState:
        with self.lock:
            ch = self._find_channel(channel_id)
            new_db = ch.fader_db + float(delta_db)
            new_linear = max(0.0, min(1.0, db_to_linear(new_db)))
            ch.fader_linear = new_linear
            osc = self._osc_client()
            if osc:
                try:
                    osc.set_channel_fader(ch.xr18_channel, new_linear)
                except Exception as exc:
                    print(f"[ASV] Failed to nudge fader ch{ch.xr18_channel}: {exc}")
            return ch

    def set_pan(self, channel_id: str, linear_value: float) -> ChannelState:
        with self.lock:
            ch = self._find_channel(channel_id)
            ch.pan_linear = max(0.0, min(1.0, float(linear_value)))
            osc = self._osc_client()
            if osc:
                try:
                    osc.set_channel_pan(ch.xr18_channel, ch.pan_linear)
                except Exception as exc:
                    print(f"[ASV] Failed to set pan ch{ch.xr18_channel}: {exc}")
            return ch

    def apply_pan_preset(self, preset_id: str) -> None:
        with self.lock:
            template = self.templates.get(self.current_template or "")
            if not template:
                raise ValueError("Template not loaded")
            presets = template.get("pan_presets", [])
            preset = next((p for p in presets if p.get("id") == preset_id or p.get("name") == preset_id), None)
            if not preset:
                raise ValueError("Unknown preset")
            for ch in self.channels:
                hint = preset.get("hints", {}).get(ch.role)
                if hint is None:
                    continue
                ch.pan_linear = pan_percent_to_linear(hint)
                osc = self._osc_client()
                if osc:
                    try:
                        osc.set_channel_pan(ch.xr18_channel, ch.pan_linear)
                    except Exception as exc:
                        print(f"[ASV] Failed to set pan ch{ch.xr18_channel}: {exc}")

    def _find_channel(self, channel_id: str) -> ChannelState:
        for ch in self.channels:
            if ch.id == channel_id:
                return ch
        raise ValueError("Unknown channel")

    # ── master helpers ─────────────────────────────────────────────
    def set_master_db(self, master_db: float) -> None:
        with self.lock:
            self.master_db = float(master_db)
            self._apply_master_to_foh()

    def _apply_master_to_foh(self) -> None:
        osc = self._osc_client()
        for member in self.foh_members:
            base_db = float(member.get("base_db", -3.0))
            target_db = base_db + self.master_db
            linear = max(0.0, min(1.0, db_to_linear(target_db)))
            member["current_db"] = target_db
            member["current_linear"] = linear
            path = member.get("path", "/main/st")
            address = path.rstrip("/")
            if not address.startswith("/"):
                address = "/" + address
            if not address.endswith("/mix/fader"):
                address = f"{address}/mix/fader"
            if osc:
                try:
                    osc.send(address, float(linear))
                except Exception as exc:
                    print(f"[ASV] Failed to set FOH fader {path}: {exc}")

    # ── telemetry ---------------------------------------------------
    def tick(self) -> dict:
        with self.lock:
            now = time.time()
            dt = max(1e-3, now - self._last_tick)
            self._last_tick = now

            # Simulate onsets for beat tracking using virtual BPM
            beats_per_sec = self._virtual_bpm / 60.0
            self._virtual_phase += beats_per_sec * dt
            while self._virtual_phase >= 1.0:
                beat_ts = now - (self._virtual_phase - 1.0) / max(beats_per_sec, 1e-6)
                self.beat_tracker.add_onset(beat_ts)
                self._virtual_phase -= 1.0
            self._beat_snapshot = self.beat_tracker.decay()

            template = self.templates.get(self.current_template or "")
            targets = template.get("targets", {}) if template else {}
            ref_db = template.get("reference_level_db", -18.0) if template else -18.0

            for ch in self.channels:
                target_db = ref_db + targets.get(ch.role, {}).get("offset_db", 0.0)
                diff = target_db - ch.meter_db
                ch.meter_db += diff * 0.2 + random.uniform(-0.2, 0.2)
                delta = target_db - ch.meter_db
                if abs(delta) < 0.3:
                    ch.suggestion_db = 0.0
                else:
                    step = max(-1.5, min(1.5, round(delta * 2) / 2.0))
                    ch.suggestion_db = step

            # Approximate crowd SPL as average of meters + random vibe factor
            avg_meter = sum(ch.meter_db for ch in self.channels) / max(len(self.channels), 1)
            crowd_level = avg_meter + random.uniform(-1.0, 1.5)
            self._spl_snapshot = self.spl_tracker.update(crowd_level)

            coach = self.master_coach.update(
                self._spl_snapshot.spl_fast,
                self._spl_snapshot.spl_slow,
                self.master_db,
                now,
            )
            if coach.delta_db:
                self.master_db = coach.master_db
                self._apply_master_to_foh()
                self._last_adjust = coach.delta_db
            else:
                self._last_adjust = 0.0
            self._last_master_message = coach.message

            return self.snapshot(include_options=False)

    def snapshot(self, include_options: bool = True) -> dict:
        mode_cfg = self.modes.get(self.current_mode or "", {})

        data = {
            "ok": True,
            "show": self.current_show,
            "template": self.current_template,
            "mode": self.current_mode,
            "channels": [
                {
                    "id": ch.id,
                    "label": ch.label,
                    "role": ch.role,
                    "xr18_channel": ch.xr18_channel,
                    "fader_linear": ch.fader_linear,
                    "fader_db": round(ch.fader_db, 2),
                    "pan_linear": ch.pan_linear,
                    "pan_percent": pan_linear_to_percent(ch.pan_linear),
                    "meter_db": round(ch.meter_db, 2),
                    "suggestion_db": round(ch.suggestion_db, 2),
                }
                for ch in self.channels
            ],
            "master": {
                "master_db": round(self.master_db, 2),
                "last_adjust_db": round(self._last_adjust, 3),
                "message": self._last_master_message,
                "foh": [
                    {
                        "id": m.get("id"),
                        "label": m.get("label"),
                        "path": m.get("path"),
                        "base_db": m.get("base_db"),
                        "current_db": round(m.get("current_db", 0.0), 2),
                        "current_linear": round(m.get("current_linear", 0.0), 3),
                    }
                    for m in self.foh_members
                ],
                "log": self.master_coach.snapshot_log(),
            },
            "telemetry": {
                "bpm_short": round(self._beat_snapshot.bpm_short, 1),
                "bpm_long": round(self._beat_snapshot.bpm_long, 1),
                "bpm_confidence": round(self._beat_snapshot.confidence, 2),
                "spl_fast": round(self._spl_snapshot.spl_fast, 1),
                "spl_slow": round(self._spl_snapshot.spl_slow, 1),
                "weighting": self._spl_snapshot.weighting,
                "target_min": mode_cfg.get("safe_spl_min"),
                "target_max": mode_cfg.get("safe_spl_max"),
            },
        }
        if include_options:
            data.update(
                {
                    "shows": [
                        {"id": sid, "name": prof.get("name", sid)}
                        for sid, prof in self.shows.items()
                    ],
                    "templates": [
                        {"id": tid, "name": tpl.get("name", tid)}
                        for tid, tpl in self.templates.items()
                    ],
                    "modes": [
                        {"id": mid, "name": mode.get("name", mid)}
                        for mid, mode in self.modes.items()
                    ],
                    "pan_presets": self._current_pan_presets(),
                }
            )
        return data

    def _current_pan_presets(self) -> List[dict]:
        template = self.templates.get(self.current_template or "")
        if not template:
            return []
        return [
            {"id": preset.get("id"), "name": preset.get("name")}
            for preset in template.get("pan_presets", [])
        ]


state = ASVState()
asv_bp = Blueprint("asv", __name__)


@asv_bp.route("/asv/mix")
def asv_mix() -> str:
    return render_template("asv_mix.html", title="ASV Mix Coach")


@asv_bp.route("/api/asv/roster", methods=["GET"])
def api_get_roster():
    return jsonify(state.snapshot(include_options=True))


@asv_bp.route("/api/asv/roster", methods=["POST"])
def api_set_roster():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        if "show" in payload:
            state.set_show(payload["show"])
        if "template" in payload:
            state.set_template(payload["template"])
        if "mode" in payload:
            state.set_mode(payload["mode"])
    except ValueError as exc:
        return jsonify({"ok": False, "err": str(exc)}), 400
    return jsonify(state.snapshot(include_options=True))


@asv_bp.route("/api/asv/pan_preset", methods=["POST"])
def api_pan_preset():
    payload = request.get_json(force=True, silent=True) or {}
    preset_id = payload.get("preset")
    if not preset_id:
        return jsonify({"ok": False, "err": "Missing preset"}), 400
    try:
        state.apply_pan_preset(preset_id)
    except ValueError as exc:
        return jsonify({"ok": False, "err": str(exc)}), 400
    return jsonify(state.snapshot(include_options=False))


@asv_bp.route("/api/asv/fader", methods=["POST"])
def api_set_fader():
    payload = request.get_json(force=True, silent=True) or {}
    updates = payload.get("updates")
    response = {}
    try:
        if updates:
            for upd in updates:
                channel = upd.get("channel")
                if not channel:
                    continue
                if "fader" in upd:
                    state.update_fader(channel, float(upd["fader"]))
                if "pan" in upd:
                    state.set_pan(channel, float(upd["pan"]))
                if "adjust_db" in upd:
                    state.nudge_fader_db(channel, float(upd["adjust_db"]))
        else:
            channel = payload.get("channel")
            if not channel:
                return jsonify({"ok": False, "err": "Missing channel"}), 400
            if "fader" in payload:
                state.update_fader(channel, float(payload["fader"]))
            if "pan" in payload:
                state.set_pan(channel, float(payload["pan"]))
            if "adjust_db" in payload:
                state.nudge_fader_db(channel, float(payload["adjust_db"]))
    except ValueError as exc:
        return jsonify({"ok": False, "err": str(exc)}), 400
    response.update(state.snapshot(include_options=False))
    return jsonify(response)


@asv_bp.route("/api/asv/master", methods=["GET"])
def api_get_master():
    snap = state.snapshot(include_options=False)
    return jsonify({"ok": True, "master": snap["master"], "mode": snap["mode"], "telemetry": snap["telemetry"]})


@asv_bp.route("/api/asv/master", methods=["POST"])
def api_set_master():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        if "master_db" in payload:
            state.set_master_db(float(payload["master_db"]))
        if "mode" in payload:
            state.set_mode(payload["mode"])
    except ValueError as exc:
        return jsonify({"ok": False, "err": str(exc)}), 400
    snap = state.snapshot(include_options=False)
    return jsonify({"ok": True, "master": snap["master"], "mode": snap["mode"], "telemetry": snap["telemetry"]})


class ASVNamespace(Namespace):
    def __init__(self, namespace: str = "/ws/asv") -> None:
        super().__init__(namespace)

    def on_connect(self):
        emit("telemetry", state.snapshot(include_options=False))


class TelemetryStreamer:
    def __init__(self, socketio) -> None:
        self.socketio = socketio
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread.start()

    def _loop(self):
        while self.running:
            payload = state.tick()
            self.socketio.emit("telemetry", payload, namespace="/ws/asv")
            time.sleep(1.0)


telemetry_streamer: Optional[TelemetryStreamer] = None


def init_asv_socketio(socketio) -> None:
    global telemetry_streamer
    socketio.on_namespace(ASVNamespace("/ws/asv"))
    if telemetry_streamer is None:
        telemetry_streamer = TelemetryStreamer(socketio)
        telemetry_streamer.start()
