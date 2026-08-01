"""Loads the fake fleet definition from host_profiles.json.

Kept as a JSON fixture (not hardcoded Python) so the "infrastructure" being
simulated is plain data — easy to read, edit, or regenerate without touching
code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class HostProfile:
    host_id: str
    service_name: str
    seed: int
    phase_offset: float  # radians, staggers hosts so they don't all peak at once
    baseline: dict = field(default_factory=dict)
    diurnal_amplitude: dict = field(default_factory=dict)


def _load_profiles() -> list[HostProfile]:
    path = Path(__file__).parent / "host_profiles.json"
    entries = json.loads(path.read_text())
    return [HostProfile(**entry) for entry in entries]


HOST_PROFILES: list[HostProfile] = _load_profiles()

METRIC_NAMES = ["cpu_pct", "mem_pct", "latency_ms", "error_rate_pct"]

# (min, max) sane clamp ranges per metric — keeps noise + injected anomalies
# from producing physically nonsensical values (negative latency etc).
METRIC_BOUNDS = {
    "cpu_pct": (0.5, 100.0),
    "mem_pct": (1.0, 100.0),
    "latency_ms": (1.0, 5000.0),
    "error_rate_pct": (0.0, 100.0),
}
