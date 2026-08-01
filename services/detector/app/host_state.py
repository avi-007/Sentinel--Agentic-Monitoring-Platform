"""Per-host in-memory state the detector maintains across the life of the
process: rolling raw-metric buffer (for feature engineering), the current
IsolationForest + its version, warm-up/training buffers, and score
history/cooldown state (for the dynamic threshold).

All of this is deliberately in-memory only (no persistence across detector
restarts) — a documented demo simplification; see README limitations.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest


@dataclass
class HostModelState:
    host_id: str
    rolling_window: int
    train_window_size: int
    score_history_size: int

    raw_buffer: deque = field(init=False)
    last_raw: Optional[dict] = field(default=None, init=False)

    is_warmed_up: bool = field(default=False, init=False)
    warmup_features: list = field(default_factory=list, init=False)
    train_window: deque = field(init=False)
    events_since_fit: int = field(default=0, init=False)

    model: Optional[IsolationForest] = field(default=None, init=False)
    model_version: int = field(default=0, init=False)

    score_history: deque = field(init=False)

    last_alert_time: Optional[datetime] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.raw_buffer = deque(maxlen=self.rolling_window)
        self.train_window = deque(maxlen=self.train_window_size)
        self.score_history = deque(maxlen=self.score_history_size)

    def recent_metric_snapshots(self) -> list[dict]:
        return list(self.raw_buffer)


class HostStateRegistry:
    """Lazily creates and holds one HostModelState per host_id seen so far."""

    def __init__(self, rolling_window: int, train_window_size: int, score_history_size: int):
        self._rolling_window = rolling_window
        self._train_window_size = train_window_size
        self._score_history_size = score_history_size
        self._states: dict[str, HostModelState] = {}

    def get(self, host_id: str) -> HostModelState:
        state = self._states.get(host_id)
        if state is None:
            state = HostModelState(
                host_id=host_id,
                rolling_window=self._rolling_window,
                train_window_size=self._train_window_size,
                score_history_size=self._score_history_size,
            )
            self._states[host_id] = state
        return state
