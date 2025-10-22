"""Simple XR18 EQ preset definitions used by the calibration UI.

Each preset returns a conservative set of parametric bands for the
main L/R bus and the two auxiliary buses used for the rear and sub
speakers.  Values are intentionally gentle so the Phase 1 UI can be
smoke-tested without risking extreme EQ swings on the hardware.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

Band = Dict[str, float]
PresetMap = Dict[str, Dict[str, List[Band]]]

_PRESETS: PresetMap = {
    "house": {
        "lr": [
            {"type": "peaking", "freq": 80.0, "gain": -1.5, "q": 1.4},
            {"type": "peaking", "freq": 320.0, "gain": 1.0, "q": 1.0},
            {"type": "peaking", "freq": 6400.0, "gain": 1.5, "q": 2.2},
        ],
        "bus_05": [
            {"type": "peaking", "freq": 100.0, "gain": -0.5, "q": 1.2},
            {"type": "peaking", "freq": 2500.0, "gain": 1.0, "q": 1.8},
        ],
        "bus_06": [
            {"type": "peaking", "freq": 60.0, "gain": 2.5, "q": 1.3},
            {"type": "peaking", "freq": 120.0, "gain": -1.5, "q": 1.1},
        ],
    },
    "flat": {
        "lr": [],
        "bus_05": [],
        "bus_06": [],
    },
    "speech": {
        "lr": [
            {"type": "highpass", "freq": 110.0, "gain": 0.0, "q": 0.7},
            {"type": "peaking", "freq": 2200.0, "gain": 2.0, "q": 1.2},
            {"type": "peaking", "freq": 6800.0, "gain": 1.8, "q": 2.0},
        ],
        "bus_05": [
            {"type": "highpass", "freq": 100.0, "gain": 0.0, "q": 0.7},
            {"type": "peaking", "freq": 1800.0, "gain": 1.5, "q": 1.5},
        ],
        "bus_06": [
            {"type": "lowpass", "freq": 120.0, "gain": 0.0, "q": 0.7},
        ],
    },
    "dj": {
        "lr": [
            {"type": "low_shelf", "freq": 80.0, "gain": 2.5, "q": 0.8},
            {"type": "high_shelf", "freq": 12000.0, "gain": 2.0, "q": 0.8},
        ],
        "bus_05": [
            {"type": "peaking", "freq": 160.0, "gain": 1.0, "q": 1.2},
            {"type": "peaking", "freq": 4000.0, "gain": 1.5, "q": 1.4},
        ],
        "bus_06": [
            {"type": "peaking", "freq": 60.0, "gain": 3.0, "q": 1.0},
            {"type": "peaking", "freq": 90.0, "gain": -1.5, "q": 1.5},
        ],
    },
}


def available_presets() -> List[str]:
    """Return the available preset identifiers."""
    return sorted(_PRESETS.keys())


def get_preset(mode: str) -> Dict[str, List[Band]]:
    """Return a deep copy of the preset bands for *mode*.

    Raises
    ------
    KeyError
        If the preset is unknown.
    """
    key = mode.lower()
    if key not in _PRESETS:
        raise KeyError(f"Unknown preset: {mode}")
    return deepcopy(_PRESETS[key])


def merge_with_current(current: Dict[str, List[Band]], preset: Dict[str, List[Band]]) -> Dict[str, List[Band]]:
    """Merge *preset* bands into *current* EQ data.

    Phase 1 keeps the logic simple: when a preset supplies bands for a
    bus, they fully replace that bus' bands.  Buses missing from the
    preset retain their current settings unchanged.  The helper returns a
    fresh dictionary without mutating the inputs.
    """
    merged: Dict[str, List[Band]] = deepcopy(current)
    for bus, bands in preset.items():
        merged[bus] = deepcopy(bands)
    return merged
