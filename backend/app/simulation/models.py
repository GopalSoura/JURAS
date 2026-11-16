import random
from typing import Any

from app.simulation.base import SEVERITY_RATE


class FireModel:
    name = "fire"

    def initial_state(self, config: dict[str, Any]) -> dict[str, Any]:
        return {"rng": random.Random(config.get("seed", 42))}

    def next_reading(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> dict[str, Any]:
        rng: random.Random = state["rng"]
        rate = SEVERITY_RATE.get(config.get("severity", "warning"), 1.0)
        age = elapsed_sec * rate
        noise = rng.uniform(-0.5, 0.5)
        smoke_ppm = max(30.0, min(900.0, 35.0 + max(0.0, age) * 14.0 * (1.0 + noise * 0.01)))
        temp_c = 31.5 + min(110.0, max(0.0, age) * 1.1 * (1.0 + noise * 0.01))
        smoke_level = min(100.0, smoke_ppm / 10.0)
        return {
            "temperature_c": round(temp_c, 1),
            "smoke_ppm": round(smoke_ppm),
            "smoke_level": round(smoke_level, 1),
        }

    def is_finished(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> bool:
        return elapsed_sec >= float(config.get("duration_sec", 60))


class FloodModel:
    name = "flood"

    def initial_state(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "rng": random.Random(config.get("seed", 42)),
            "factor": float(config.get("flood_factor", 0.8)),
            "level_cm": 0.0,
        }

    def next_reading(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> dict[str, Any]:
        rng: random.Random = state["rng"]
        rate = SEVERITY_RATE.get(config.get("severity", "warning"), 1.0)
        age = elapsed_sec * rate
        rain = min(75.0, age * 2.0) + (rng.uniform(-1.5, 1.5) if rain_active(age) else 0.0)
        rain = max(0.0, rain)
        if rain > 18.0:
            state["level_cm"] += (rain - 18.0) * 0.012 * state["factor"] * 2.0
        else:
            state["level_cm"] = max(0.0, state["level_cm"] - 0.25)
        return {
            "rain_mmh": round(rain, 1),
            "water_level_cm": round(state["level_cm"], 1),
        }

    def is_finished(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> bool:
        return elapsed_sec >= float(config.get("duration_sec", 90))


def rain_active(age: float) -> bool:
    return age > 1.0


class StructuralModel:
    name = "structural"

    def initial_state(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "rng": random.Random(config.get("seed", 42)),
            "base_tilt": float(config.get("base_tilt_deg", 0.06)),
            "base_crack": float(config.get("base_crack_mm", 0.1)),
        }

    def next_reading(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> dict[str, Any]:
        rng: random.Random = state["rng"]
        rate = SEVERITY_RATE.get(config.get("severity", "warning"), 1.0)
        age = max(0.0, elapsed_sec) * rate
        tilt = state["base_tilt"] + min(1.1, age * 0.012) + rng.uniform(-0.01, 0.01)
        crack = state["base_crack"] + min(1.2, age * 0.02) + rng.uniform(-0.01, 0.01)
        vib = 0.02 + min(0.05, age * 0.0004) + rng.uniform(-0.004, 0.004)
        return {
            "tilt_deg": round(max(0.0, tilt), 2),
            "crack_mm": round(max(0.0, crack), 2),
            "vib_rms": round(max(0.0, vib), 2),
            "deviation_mm": round(max(0.0, crack) * 1.4, 2),
        }

    def is_finished(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> bool:
        return elapsed_sec >= float(config.get("duration_sec", 90))


MODELS: dict[str, type] = {"fire": FireModel, "flood": FloodModel, "structural": StructuralModel}


def get_model(scenario: str):
    model_cls = MODELS.get(scenario)
    if model_cls is None:
        raise ValueError(f"Unknown scenario: {scenario}")
    return model_cls()
