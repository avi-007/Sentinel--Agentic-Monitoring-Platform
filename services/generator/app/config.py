from common.settings import BaseServiceSettings


class GeneratorSettings(BaseServiceSettings):
    gen_tick_interval_seconds: float = 3.0
    # Compresses simulated time so a full diurnal cycle plays out in minutes of
    # wall-clock time instead of 24 real hours — otherwise the "day/night load"
    # shape would never be visible in a live demo session.
    gen_time_scale_factor: float = 48.0
    gen_anomaly_injection_rate: float = 0.02
    gen_anomaly_cooldown_ticks: int = 100
