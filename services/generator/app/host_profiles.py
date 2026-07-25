"""Static fixture: a small fake fleet. Kept as code (not env-driven) so the
"infrastructure" being simulated is easy to read in one place.

Each host has its own baseline (steady-state metric values), a diurnal
amplitude per metric (how much load swings over the simulated day), and a
`stress_loading` per metric that determines how much a shared latent "stress"
factor (see signal_model.py) pushes that metric around — this is what makes
latency and error_rate rise together without hard-coding a latency->error rule.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HostProfile:
    host_id: str
    service_name: str
    seed: int
    phase_offset: float  # radians, staggers hosts so they don't all peak at once
    baseline: dict = field(default_factory=dict)
    diurnal_amplitude: dict = field(default_factory=dict)
    stress_loading: dict = field(default_factory=dict)


HOST_PROFILES: list[HostProfile] = [
    HostProfile(
        host_id="web-01",
        service_name="web",
        seed=1,
        phase_offset=0.0,
        baseline={"cpu_pct": 35.0, "mem_pct": 55.0, "latency_ms": 90.0, "error_rate_pct": 0.5},
        diurnal_amplitude={"cpu_pct": 20.0, "mem_pct": 8.0, "latency_ms": 25.0, "error_rate_pct": 0.3},
        stress_loading={"cpu_pct": 0.6, "mem_pct": 0.2, "latency_ms": 1.0, "error_rate_pct": 0.8},
    ),
    HostProfile(
        host_id="web-02",
        service_name="web",
        seed=2,
        phase_offset=0.3,
        baseline={"cpu_pct": 32.0, "mem_pct": 52.0, "latency_ms": 85.0, "error_rate_pct": 0.4},
        diurnal_amplitude={"cpu_pct": 18.0, "mem_pct": 7.0, "latency_ms": 22.0, "error_rate_pct": 0.25},
        stress_loading={"cpu_pct": 0.6, "mem_pct": 0.2, "latency_ms": 1.0, "error_rate_pct": 0.8},
    ),
    HostProfile(
        host_id="api-01",
        service_name="api",
        seed=3,
        phase_offset=0.6,
        baseline={"cpu_pct": 45.0, "mem_pct": 60.0, "latency_ms": 120.0, "error_rate_pct": 0.8},
        diurnal_amplitude={"cpu_pct": 25.0, "mem_pct": 10.0, "latency_ms": 35.0, "error_rate_pct": 0.5},
        stress_loading={"cpu_pct": 0.7, "mem_pct": 0.3, "latency_ms": 1.2, "error_rate_pct": 1.0},
    ),
    HostProfile(
        host_id="api-02",
        service_name="api",
        seed=4,
        phase_offset=0.9,
        baseline={"cpu_pct": 42.0, "mem_pct": 58.0, "latency_ms": 115.0, "error_rate_pct": 0.7},
        diurnal_amplitude={"cpu_pct": 24.0, "mem_pct": 9.0, "latency_ms": 32.0, "error_rate_pct": 0.45},
        stress_loading={"cpu_pct": 0.7, "mem_pct": 0.3, "latency_ms": 1.2, "error_rate_pct": 1.0},
    ),
    HostProfile(
        host_id="db-01",
        service_name="db",
        seed=5,
        phase_offset=1.2,
        baseline={"cpu_pct": 50.0, "mem_pct": 70.0, "latency_ms": 15.0, "error_rate_pct": 0.1},
        diurnal_amplitude={"cpu_pct": 15.0, "mem_pct": 5.0, "latency_ms": 6.0, "error_rate_pct": 0.08},
        stress_loading={"cpu_pct": 0.5, "mem_pct": 0.6, "latency_ms": 0.8, "error_rate_pct": 0.4},
    ),
    HostProfile(
        host_id="cache-01",
        service_name="cache",
        seed=6,
        phase_offset=1.5,
        baseline={"cpu_pct": 20.0, "mem_pct": 65.0, "latency_ms": 3.0, "error_rate_pct": 0.05},
        diurnal_amplitude={"cpu_pct": 10.0, "mem_pct": 6.0, "latency_ms": 1.5, "error_rate_pct": 0.04},
        stress_loading={"cpu_pct": 0.4, "mem_pct": 0.5, "latency_ms": 0.6, "error_rate_pct": 0.3},
    ),
]

METRIC_NAMES = ["cpu_pct", "mem_pct", "latency_ms", "error_rate_pct"]

# (min, max) sane clamp ranges per metric — keeps AR(1) noise + injected
# anomalies from producing physically nonsensical values (negative latency etc).
METRIC_BOUNDS = {
    "cpu_pct": (0.5, 100.0),
    "mem_pct": (1.0, 100.0),
    "latency_ms": (1.0, 5000.0),
    "error_rate_pct": (0.0, 100.0),
}
