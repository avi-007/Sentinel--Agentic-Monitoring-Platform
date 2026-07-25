"""Turns a raw metric snapshot into a small, explainable 12-dim feature vector:
4 raw values, 4 rolling z-scores, 4 tick-over-tick deltas. Deliberately kept
small rather than a large engineered feature set — easy to reason about (and
explain) for a portfolio project, and plenty for IsolationForest to work with
at this data volume.

Z-scores are computed against the rolling window *before* the current point is
appended to it, so a single extreme point doesn't dilute its own baseline.
"""

from __future__ import annotations

import numpy as np

from .host_state import HostModelState

METRIC_NAMES = ["cpu_pct", "mem_pct", "latency_ms", "error_rate_pct"]

FEATURE_NAMES = (
    METRIC_NAMES
    + [f"{m}_z" for m in METRIC_NAMES]
    + [f"{m}_delta" for m in METRIC_NAMES]
)


def compute_feature_vector(state: HostModelState, metrics: dict) -> np.ndarray:
    values = np.array([metrics[m] for m in METRIC_NAMES], dtype=float)

    if len(state.raw_buffer) >= 2:
        window = np.array([[b[m] for m in METRIC_NAMES] for b in state.raw_buffer], dtype=float)
        means = window.mean(axis=0)
        stds = window.std(axis=0)
    else:
        means = values
        stds = np.zeros(4)

    z_scores = np.where(stds > 1e-6, (values - means) / np.where(stds > 1e-6, stds, 1.0), 0.0)

    if state.last_raw is None:
        deltas = np.zeros(4)
    else:
        deltas = values - np.array([state.last_raw[m] for m in METRIC_NAMES], dtype=float)

    # Update rolling state for next call.
    state.raw_buffer.append(metrics)
    state.last_raw = metrics

    return np.concatenate([values, z_scores, deltas])
