"""High level helpers for XR18 EQ interactions used by the calibration UI.

The real mixer can be driven through :mod:`core.osc_client`, but for the
web UI tests we provide a safe, file-backed state store that mimics the
XR18 responses.  Production deployments can swap the implementation for
one that forwards the commands over OSC.
"""
from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Union

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
SNAPSHOT_DIR = ROOT / "snapshots"
STATE_PATH = SNAPSHOT_DIR / "STATE.json"
LAST_SNAPSHOT = SNAPSHOT_DIR / "LAST.json"

_state_lock = threading.Lock()

_DEFAULT_STATE: Dict[str, Any] = {
    "eq": {
        "lr": {"bands": []},
        "bus_05": {"bands": []},
        "bus_06": {"bands": []},
    },
    "faders": {
        "lr": 0.75,
        "bus_05": 0.65,
        "bus_06": 0.65,
    },
    "meta": {
        "updated": None,
    },
}


def _ensure_dirs() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    _ensure_dirs()
    if STATE_PATH.exists():
        try:
            with STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = deepcopy(_DEFAULT_STATE)
    else:
        data = deepcopy(_DEFAULT_STATE)
    # ensure keys exist
    data.setdefault("eq", {})
    data.setdefault("faders", {})
    data.setdefault("meta", {})
    data["eq"].setdefault("lr", {"bands": []})
    data["eq"].setdefault("bus_05", {"bands": []})
    data["eq"].setdefault("bus_06", {"bands": []})
    data["faders"].setdefault("lr", 0.75)
    data["faders"].setdefault("bus_05", 0.65)
    data["faders"].setdefault("bus_06", 0.65)
    return data


def _save_state(state: Dict[str, Any]) -> None:
    _ensure_dirs()
    tmp_path = STATE_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp_path.replace(STATE_PATH)


def _format_bus(bus: Union[str, int]) -> str:
    if isinstance(bus, str):
        key = bus.lower()
        if key in {"lr", "main", "st"}:
            return "lr"
        if key.startswith("bus_"):
            return key
        if key.startswith("aux_"):
            return key.replace("aux_", "bus_")
        if key.isdigit():
            return f"bus_{int(key):02d}"
    return f"bus_{int(bus):02d}"


def _deepcopy(obj: Any) -> Any:
    return deepcopy(obj)


def get_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            try:
                return yaml.safe_load(f) or {}
            except yaml.YAMLError:
                return {}
    return {}


def get_calibration_config() -> Dict[str, Any]:
    cfg = get_config()
    return cfg.get("calibration", {})


def get_eq(bus: Union[str, int]) -> Dict[str, Any]:
    """Return the EQ bands for *bus* from the local state store."""
    key = _format_bus(bus)
    with _state_lock:
        state = _load_state()
        eq = state["eq"].get(key, {"bands": []})
        return _deepcopy(eq)


def set_eq(bus: Union[str, int], bands: Iterable[Dict[str, Any]]) -> None:
    key = _format_bus(bus)
    with _state_lock:
        state = _load_state()
        state["eq"][key] = {"bands": list(deepcopy(list(bands)))}
        state["meta"]["updated"] = time.time()
        _save_state(state)


def get_fader(bus: Union[str, int]) -> float:
    key = _format_bus(bus)
    with _state_lock:
        state = _load_state()
        return float(state["faders"].get(key, 0.0))


def set_fader(bus: Union[str, int], value: float) -> None:
    key = _format_bus(bus)
    with _state_lock:
        state = _load_state()
        state["faders"][key] = float(value)
        state["meta"]["updated"] = time.time()
        _save_state(state)


def get_all_eq() -> Dict[str, Any]:
    cfg = get_calibration_config()
    rear_bus = cfg.get("buses", {}).get("rear", 5)
    sub_bus = cfg.get("buses", {}).get("sub", 6)
    with _state_lock:
        state = _load_state()
        return {
            "lr": _deepcopy(state["eq"].get("lr", {"bands": []})),
            "rear": _deepcopy(state["eq"].get(f"bus_{int(rear_bus):02d}", {"bands": []})),
            "sub": _deepcopy(state["eq"].get(f"bus_{int(sub_bus):02d}", {"bands": []})),
        }


def snapshot_all_eq(write_file: bool = True) -> Dict[str, Any]:
    cfg = get_config()
    with _state_lock:
        state = _load_state()
        snapshot = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "xr18_ip": cfg.get("xair", {}).get("ip", "unknown"),
            "eq": _deepcopy(state["eq"]),
            "faders": _deepcopy(state["faders"]),
        }
        if write_file:
            _ensure_dirs()
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = SNAPSHOT_DIR / f"eq_{ts}.json"
            with path.open("w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            with LAST_SNAPSHOT.open("w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            snapshot["path"] = str(path)
        return snapshot


def restore_eq(snapshot: Dict[str, Any]) -> None:
    eq = snapshot.get("eq", {})
    faders = snapshot.get("faders", {})
    with _state_lock:
        state = _load_state()
        state["eq"] = _deepcopy(eq)
        state["faders"] = _deepcopy(faders)
        state["meta"]["updated"] = time.time()
        _save_state(state)


def restore_last_snapshot() -> Dict[str, Any]:
    if not LAST_SNAPSHOT.exists():
        raise FileNotFoundError("No EQ snapshot has been saved yet")
    with LAST_SNAPSHOT.open("r", encoding="utf-8") as f:
        snapshot = json.load(f)
    restore_eq(snapshot)
    return snapshot


def apply_filters(filters: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """Apply filters to the internal state.

    Parameters
    ----------
    filters:
        Mapping of bus identifier (``lr`` or ``bus_XX``) to a list of EQ
        band dictionaries.
    dry_run:
        When True, the state is not modified.  The resulting structure is
        still returned for UI preview purposes.
    """
    normalized: Dict[str, Any] = {}
    for bus, payload in (filters or {}).items():
        key = _format_bus(bus)
        bands = payload.get("bands") if isinstance(payload, dict) else payload
        if bands is None:
            bands = []
        normalized[key] = {"bands": list(deepcopy(bands))}

    with _state_lock:
        state = _load_state()
        preview = _deepcopy(state["eq"])
        preview.update(normalized)
        if not dry_run:
            state["eq"].update(normalized)
            state["meta"]["updated"] = time.time()
            _save_state(state)
    return normalized
