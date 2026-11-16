from typing import Any

from app.core.constants import RiskCategory
from app.risk import thresholds as T

CATEGORY_BANDS = [
    (0, 20, RiskCategory.normal),
    (20, 40, RiskCategory.low),
    (40, 65, RiskCategory.warning),
    (65, 85, RiskCategory.high),
    (85, 101, RiskCategory.critical),
]


def categorize(score: float) -> RiskCategory:
    for low, high, cat in CATEGORY_BANDS:
        if low <= score < high:
            return cat
    return RiskCategory.critical


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def evaluate_fire(values: dict[str, Any]) -> dict[str, Any]:
    smoke = float(values.get("smoke_level", 0) or 0)
    temp = float(values.get("temperature_c", 31.5) or 31.5)
    ppm = float(values.get("smoke_ppm", 0) or 0)
    if smoke == 0 and ppm:
        smoke = min(100.0, ppm / 10.0)
    smoke_norm = clamp01(smoke / T.FIRE_SMOKE_NORM_MAX)
    temp_norm = clamp01((temp - T.FIRE_TEMP_NORM_MIN) / (T.FIRE_TEMP_NORM_MAX - T.FIRE_TEMP_NORM_MIN))
    score = round(100 * (0.6 * smoke_norm + 0.4 * temp_norm))
    reasons: list[dict[str, Any]] = []
    if smoke >= T.FIRE_SMOKE_CRITICAL:
        reasons.append(
            {"rule": "FIRE-R2", "text": f"Smoke index {smoke:.0f} >= {T.FIRE_SMOKE_CRITICAL} (critical band)"}
        )
    elif smoke >= T.FIRE_SMOKE_HIGH:
        reasons.append(
            {"rule": "FIRE-R1", "text": f"Smoke index {smoke:.0f} >= {T.FIRE_SMOKE_HIGH} (high band)"}
        )
    if temp >= T.FIRE_TEMP_CRITICAL:
        reasons.append(
            {"rule": "FIRE-R4", "text": f"Temperature {temp:.1f} C >= {T.FIRE_TEMP_CRITICAL} (critical band)"}
        )
    elif temp >= T.FIRE_TEMP_HIGH:
        reasons.append(
            {"rule": "FIRE-R3", "text": f"Temperature {temp:.1f} C >= {T.FIRE_TEMP_HIGH} (high band)"}
        )
    if not reasons:
        reasons.append({"rule": "FIRE-R0", "text": "Below demo action thresholds"})
    return {"score": score, "category": categorize(score).value, "reasons": reasons}


def evaluate_flood(values: dict[str, Any]) -> dict[str, Any]:
    level = float(values.get("water_level_cm", 0) or 0)
    rain = float(values.get("rain_mmh", 0) or 0)
    level_norm = clamp01(level / T.FLOOD_LEVEL_NORM_MAX)
    rain_norm = clamp01(rain / T.FLOOD_RAIN_NORM_MAX)
    score = round(100 * (0.75 * level_norm + 0.25 * rain_norm))
    reasons: list[dict[str, Any]] = []
    if level >= T.FLOOD_LEVEL_CRITICAL:
        reasons.append(
            {"rule": "FLOOD-R2", "text": f"Water level {level:.0f} cm >= {T.FLOOD_LEVEL_CRITICAL} (critical band)"}
        )
    elif level >= T.FLOOD_LEVEL_HIGH:
        reasons.append(
            {"rule": "FLOOD-R1", "text": f"Water level {level:.0f} cm >= {T.FLOOD_LEVEL_HIGH} (high band)"}
        )
    if rain >= 30:
        reasons.append({"rule": "FLOOD-R3", "text": f"Rainfall {rain:.0f} mm/h sustained"})
    if not reasons:
        reasons.append({"rule": "FLOOD-R0", "text": "Below demo action thresholds"})
    return {"score": score, "category": categorize(score).value, "reasons": reasons}


def evaluate_structural(values: dict[str, Any]) -> dict[str, Any]:
    tilt = float(values.get("tilt_deg", 0) or 0)
    crack = float(values.get("crack_mm", 0) or 0)
    tilt_norm = clamp01(tilt / T.STRUCT_TILT_NORM_MAX)
    crack_norm = clamp01(crack / T.STRUCT_CRACK_NORM_MAX)
    score = round(100 * (0.55 * tilt_norm + 0.45 * crack_norm))
    reasons: list[dict[str, Any]] = []
    if tilt >= T.STRUCT_TILT_CRITICAL:
        reasons.append(
            {"rule": "STRUCT-R2", "text": f"Tilt {tilt:.2f} deg >= {T.STRUCT_TILT_CRITICAL} (critical band)"}
        )
    elif tilt >= T.STRUCT_TILT_HIGH:
        reasons.append(
            {"rule": "STRUCT-R1", "text": f"Tilt {tilt:.2f} deg >= {T.STRUCT_TILT_HIGH} (high band)"}
        )
    if crack >= T.STRUCT_CRACK_CRITICAL:
        reasons.append(
            {"rule": "STRUCT-R4", "text": f"Crack {crack:.2f} mm >= {T.STRUCT_CRACK_CRITICAL} (critical band)"}
        )
    elif crack >= T.STRUCT_CRACK_HIGH:
        reasons.append(
            {"rule": "STRUCT-R3", "text": f"Crack {crack:.2f} mm >= {T.STRUCT_CRACK_HIGH} (high band)"}
        )
    if not reasons:
        reasons.append({"rule": "STRUCT-R0", "text": "Below demo action thresholds"})
    return {"score": score, "category": categorize(score).value, "reasons": reasons}


EVALUATORS = {
    "fire": evaluate_fire,
    "flood": evaluate_flood,
    "structural": evaluate_structural,
}


def evaluate(hazard: str, values: dict[str, Any]) -> dict[str, Any]:
    fn = EVALUATORS.get(hazard)
    if fn is None:
        raise ValueError(f"Unknown hazard: {hazard}")
    return fn(values)
