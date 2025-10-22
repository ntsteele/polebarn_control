#!/usr/bin/env python3
"""Beat and SPL tracking helpers for the Augmented Soundguy view."""

from __future__ import annotations

import collections
import math
import statistics
import time
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional


@dataclass
class BeatEstimate:
    bpm_short: float
    bpm_long: float
    confidence: float


class BeatTracker:
    """Track tempo from onset timestamps.

    The tracker keeps a history of onset timestamps (seconds) and derives a
    short-window BPM plus a longer EMA-style average. When the music stops the
    long average decays gently toward zero instead of dropping instantly.
    """

    def __init__(
        self,
        short_window: float = 8.0,
        long_half_life: float = 45.0,
        min_confidence: float = 0.1
    ) -> None:
        self.short_window = float(short_window)
        self.long_alpha = self._half_life_to_alpha(long_half_life)
        self.min_confidence = float(min_confidence)
        self._onsets: Deque[float] = collections.deque()
        self._bpm_long: float = 0.0
        self._last_update: float = time.time()

    @staticmethod
    def _half_life_to_alpha(half_life: float) -> float:
        if half_life <= 0:
            return 1.0
        # convert half-life in seconds to exponential smoothing alpha
        return 1.0 - math.exp(math.log(0.5) / max(half_life, 1e-6))

    def add_onset(self, timestamp: Optional[float] = None) -> BeatEstimate:
        """Register an onset at ``timestamp`` (defaults to ``time.time()``).

        Returns the updated :class:`BeatEstimate`.
        """

        ts = float(timestamp if timestamp is not None else time.time())
        self._onsets.append(ts)
        self._trim(ts)
        return self._compute(ts)

    def update(self, energy: float, threshold: float = 0.6) -> BeatEstimate:
        """Feed the tracker with an onset energy value.

        ``energy`` should be normalised to 0–1. When the value exceeds the
        threshold we treat it as an onset. This helper makes it easy to hook the
        tracker up to an RMS/onset detection front-end. The returned estimate is
        the most recent state regardless of whether a new onset fired.
        """

        now = time.time()
        if energy >= threshold:
            self._onsets.append(now)
            self._trim(now)
        return self._compute(now)

    def decay(self) -> BeatEstimate:
        """Advance the internal EMA without adding new onsets."""

        now = time.time()
        self._trim(now)
        return self._compute(now)

    def _trim(self, now: float) -> None:
        """Drop onsets older than the short_window."""

        cutoff = now - self.short_window
        while self._onsets and self._onsets[0] < cutoff:
            self._onsets.popleft()

    def _compute(self, now: float) -> BeatEstimate:
        bpm_short = 0.0
        confidence = 0.0

        if len(self._onsets) >= 2:
            intervals = [
                b - a
                for a, b in zip(self._onsets, list(self._onsets)[1:])
                if b > a
            ]
            if intervals:
                interval = statistics.median(intervals)
                if interval > 1e-3:
                    bpm_short = 60.0 / interval
                    spread = statistics.pstdev(intervals) if len(intervals) > 1 else 0.0
                    confidence = max(0.0, 1.0 - spread / max(interval, 1e-3))

        # Update long-term EMA; decay toward zero slowly when idle
        dt = max(1e-3, now - self._last_update)
        self._last_update = now

        if bpm_short > 0.0:
            alpha = self.long_alpha
            self._bpm_long = (1.0 - alpha) * self._bpm_long + alpha * bpm_short
        else:
            # exponential decay
            decay_factor = math.exp(-self.long_alpha * dt)
            self._bpm_long *= decay_factor
            if self._bpm_long < 0.1:
                self._bpm_long = 0.0

        # Ensure long never exceeds short when both valid
        if bpm_short > 0.0 and self._bpm_long > bpm_short * 1.2:
            self._bpm_long = bpm_short * 1.2

        return BeatEstimate(
            bpm_short=bpm_short,
            bpm_long=self._bpm_long,
            confidence=max(confidence, self.min_confidence if bpm_short else 0.0)
        )


@dataclass
class SPLSnapshot:
    spl_fast: float
    spl_slow: float
    weighting: str


class SPLTracker:
    """Two-pole RMS tracker with optional A-weighting."""

    def __init__(
        self,
        fast_tc: float = 0.125,
        slow_tc: float = 1.0,
        weighting: str = "Z"
    ) -> None:
        self.fast_alpha = self._tc_to_alpha(fast_tc)
        self.slow_alpha = self._tc_to_alpha(slow_tc)
        self.weighting = weighting.upper()
        self._fast = -90.0
        self._slow = -90.0
        self._last_update = time.time()

    @staticmethod
    def _tc_to_alpha(tc: float) -> float:
        tc = max(tc, 1e-3)
        return 1.0 - math.exp(-1.0 / tc)

    def set_weighting(self, weighting: str) -> None:
        self.weighting = weighting.upper()

    def update(self, level_dbfs: float, timestamp: Optional[float] = None) -> SPLSnapshot:
        now = float(timestamp if timestamp is not None else time.time())
        dt = max(now - self._last_update, 1e-3)
        self._last_update = now

        weighted = level_dbfs + self._weighting_offset(level_dbfs)

        self._fast = self._exp_smooth(self._fast, weighted, self.fast_alpha)
        self._slow = self._exp_smooth(self._slow, weighted, self.slow_alpha)
        return SPLSnapshot(self._fast, self._slow, self.weighting)

    def _exp_smooth(self, current: float, value: float, alpha: float) -> float:
        if math.isinf(current):
            return value
        return (1.0 - alpha) * current + alpha * value

    def _weighting_offset(self, level_dbfs: float) -> float:
        if self.weighting == "A":
            # Approximate ANSI A-weighting using a polynomial fit in the audible band
            # https://en.wikipedia.org/wiki/A-weighting#Implementations
            f = min(max(level_dbfs, -80.0), 0.0)
            return 0.0004 * f * f + 0.1 * f + 0.0
        return 0.0


@dataclass
class MasterAdjustment:
    master_db: float
    delta_db: float
    limited: bool
    message: str


class MasterCoach:
    """Compute FOH master adjustments to hold SPL within a safe window."""

    def __init__(self) -> None:
        self.mode: Optional[Dict[str, float]] = None
        self._integrator = 0.0
        self._last_time = time.time()
        self._last_master_db = 0.0
        self.log: List[Dict[str, float]] = []

    def set_mode(self, mode_cfg: Optional[Dict[str, float]]) -> None:
        self.mode = mode_cfg
        self._integrator = 0.0
        self.log.clear()

    def update(
        self,
        spl_fast: float,
        spl_slow: float,
        master_db: float,
        timestamp: Optional[float] = None
    ) -> MasterAdjustment:
        if not self.mode:
            return MasterAdjustment(master_db, 0.0, False, "Mode inactive")

        now = float(timestamp if timestamp is not None else time.time())
        dt = max(now - self._last_time, 1e-3)
        self._last_time = now

        cfg = self.mode
        target = cfg.get("preferred_spl", (cfg.get("safe_spl_min", 0.0) + cfg.get("safe_spl_max", 0.0)) / 2.0)
        deadband = cfg.get("deadband_db", 1.0)

        error = 0.0
        limited = False
        msg = ""

        if spl_slow < cfg.get("safe_spl_min", target) - deadband:
            error = target - spl_slow
            msg = "Below safe window"
        elif spl_slow > cfg.get("safe_spl_max", target) + deadband:
            error = target - spl_slow
            msg = "Above safe window"
            limited = True
            self.log.append({
                "timestamp": now,
                "excess_db": spl_slow - cfg.get("safe_spl_max", target),
                "spl": spl_slow
            })
        elif abs(spl_slow - target) > deadband:
            error = target - spl_slow
            msg = "Holding preferred SPL"
        else:
            error = 0.0
            msg = "Within target window"

        attack = cfg.get("attack_sec", 1.0)
        release = cfg.get("release_sec", 2.0)
        alpha = dt / max(attack if error > 0 else release, 1e-3)
        alpha = max(0.0, min(alpha, 1.0))

        proportional = error * 0.25  # gentle proportional gain
        self._integrator += error * dt * 0.05
        self._integrator = max(-6.0, min(6.0, self._integrator))

        raw_delta = (1.0 - alpha) * 0.0 + alpha * (proportional + self._integrator)

        max_rate = cfg.get("max_delta_db_per_sec", 0.5)
        max_delta = max_rate * dt
        delta_db = max(-max_delta, min(max_delta, raw_delta))

        new_master = master_db + delta_db
        self._last_master_db = new_master

        return MasterAdjustment(new_master, delta_db, limited, msg)

    def snapshot_log(self, limit: int = 20) -> List[Dict[str, float]]:
        return self.log[-limit:]
