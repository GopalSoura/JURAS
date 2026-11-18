import math
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# Bounds are intentionally generous: they catch wiring faults, negative
# distances and NaN/Inf without pretending to be a certified sensor spec.
VALUE_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_c": (-40.0, 125.0),
    "temp_c": (-40.0, 125.0),
    "humidity_pct": (0.0, 100.0),
    "smoke_level": (0.0, 100.0),
    "smoke_ppm": (0.0, 20000.0),
    "smoke_raw": (0.0, 4095.0),
    "gas_baseline": (0.0, 4095.0),
    "flame": (0.0, 1.0),
    "dht_ok": (0.0, 1.0),
    "mq2_ok": (0.0, 1.0),
    "rssi": (-150.0, 0.0),
    "seq": (0.0, 2_147_483_647.0),
    "tilt_deg": (0.0, 90.0),
    "crack_mm": (0.0, 100.0),
    "crack_raw": (0.0, 4095.0),
    "vib_rms": (0.0, 100.0),
    "deviation_mm": (0.0, 10000.0),
    "mpu_ok": (0.0, 1.0),
    "crack_ok": (0.0, 1.0),
    "water_level_cm": (0.0, 1000.0),
    "level_cm": (0.0, 1000.0),
    "rain_mmh": (0.0, 500.0),
    "rain_raw": (0.0, 4095.0),
    "distance_cm": (0.0, 1000.0),
}

HAZARD_REQUIRED_METRICS: dict[str, set[str]] = {
    "fire": {"smoke_level", "smoke_ppm", "temperature_c", "temp_c"},
    "structural": {"tilt_deg", "crack_mm", "vib_rms", "deviation_mm"},
    "flood": {"water_level_cm", "level_cm", "rain_mmh"},
}


class ReadingCreate(BaseModel):
    sensor_id: str | None = None
    device_id: str | None = None
    building_id: str | None = None
    node_code: str | None = None
    simulation_id: str | None = None
    hazard: str = Field(default="fire")
    values: dict[str, float] = Field(default_factory=dict)
    observed_at: datetime | None = None
    source: str = "simulation"
    simulation: bool = True

    @field_validator("hazard")
    @classmethod
    def check_hazard(cls, v: str) -> str:
        if v not in ("fire", "flood", "structural"):
            raise ValueError("hazard must be one of fire, flood, structural")
        return v

    @field_validator("source")
    @classmethod
    def check_source(cls, v: str) -> str:
        if v not in ("simulation", "field", "imported"):
            raise ValueError("source must be one of simulation, field, imported")
        return v

    @field_validator("values")
    @classmethod
    def check_values(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("values must not be empty")
        cleaned: dict[str, float] = {}
        for key, raw in v.items():
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"value {key!r} is not numeric") from exc
            if not math.isfinite(value):
                raise ValueError(f"value {key!r} must be finite (NaN/Inf is invalid)")
            low_high = VALUE_BOUNDS.get(key)
            if low_high is not None and not (low_high[0] <= value <= low_high[1]):
                raise ValueError(
                    f"value {key!r}={value:g} outside allowed range "
                    f"[{low_high[0]:g}, {low_high[1]:g}]"
                )
            cleaned[key] = value
        return cleaned

    @field_validator("observed_at")
    @classmethod
    def check_observed_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def check_hazard_metrics(self) -> "ReadingCreate":
        required = HAZARD_REQUIRED_METRICS[self.hazard]
        if not required.intersection(self.values):
            names = ", ".join(sorted(required))
            raise ValueError(
                f"hazard {self.hazard!r} requires at least one of: {names}"
            )
        return self


class ReadingOut(BaseModel):
    id: str
    sensor_id: str | None
    building_id: str | None
    simulation_id: str | None
    hazard: str
    values: dict[str, Any]
    observed_at: str
    received_at: str
    source: str
    simulation: bool

    class Config:
        extra = "allow"


class ReadingIngestResult(BaseModel):
    id: str
    accepted: bool
    risk: dict[str, Any] | None = None
    incident_id: str | None = None
    incident_created: bool = False
