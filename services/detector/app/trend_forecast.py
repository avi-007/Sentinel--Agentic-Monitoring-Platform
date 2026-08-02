"""Trend-based early-warning forecast — the actual "predict N minutes ahead"
mechanism in this project, separate from and complementary to
dynamic_threshold.py's reactive threshold.

dynamic_threshold.py only fires once a host's score has *already* crossed
its adaptive threshold — it never looks forward. This module instead looks
at a short recent window of a host's raw anomaly scores, fits a straight
line through them, and — if the trend is rising and the host hasn't crossed
its threshold yet — extrapolates how many minutes remain before the current
trajectory would cross it. It's a simple linear extrapolation, not a real
forecasting model: only trusted over a short horizon
(DET_TREND_HORIZON_MINUTES) and only while the score is still below
threshold, since a straight-line fit over a handful of points says nothing
reliable further out than that.

raw_score is noisy tick-to-tick (feature_engineering.py's z-scores/deltas
are computed against a rolling baseline that itself shifts during a real
ramp, which muddies the very trend we're trying to see), enough that fitting
the line directly against raw scores fails the R^2 gate even during a clean,
textbook ramp — confirmed empirically. So the line is fit against a trailing
moving average (DET_TREND_SMOOTHING_WINDOW) of recent scores instead, and
the "where are we now" anchor for the breach extrapolation is the latest
smoothed value too, not the single noisy raw_score, to stay consistent with
the trend the line actually describes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

from .config import DetectorSettings
from .host_state import HostModelState


def _trailing_moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """values[i:i+window] -> one output per full window, aligned to each
    window's last element (trailing MA, no lookahead)."""
    if window <= 1 or len(values) < window:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="valid")


def evaluate(
    state: HostModelState,
    raw_score: float,
    threshold: Optional[float],
    is_anomaly: bool,
    now: datetime,
    settings: DetectorSettings,
) -> Optional[float]:
    state.trend_window.append((now, raw_score))

    if threshold is None or is_anomaly or len(state.trend_window) < settings.det_trend_min_points:
        return None

    points = list(state.trend_window)
    first_ts = points[0][0]
    xs = np.array([(ts - first_ts).total_seconds() for ts, _ in points])
    ys = np.array([score for _, score in points])

    window = settings.det_trend_smoothing_window
    smoothed_ys = _trailing_moving_average(ys, window)
    smoothed_xs = xs[window - 1 :] if window > 1 and len(xs) >= window else xs

    if len(smoothed_ys) < 2:
        return None

    slope, intercept = np.polyfit(smoothed_xs, smoothed_ys, 1)
    if slope <= 0:
        return None

    # Fit-quality gate: R^2 of how well the line explains the smoothed
    # scores. Without this, ordinary noise can produce a small spurious
    # positive slope and a false "trending toward breach" prediction —
    # exactly what this feature exists to avoid causing.
    predicted = slope * smoothed_xs + intercept
    ss_res = np.sum((smoothed_ys - predicted) ** 2)
    ss_tot = np.sum((smoothed_ys - np.mean(smoothed_ys)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    if r_squared < settings.det_trend_min_r_squared:
        return None

    current_smoothed_score = float(smoothed_ys[-1])
    seconds_to_breach = (threshold - current_smoothed_score) / slope
    minutes_to_breach = seconds_to_breach / 60.0

    if 0 <= minutes_to_breach <= settings.det_trend_horizon_minutes:
        return round(minutes_to_breach, 1)
    return None