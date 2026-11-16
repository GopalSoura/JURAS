from app.risk.rules import categorize, evaluate_fire, evaluate_flood, evaluate_structural


def test_fire_critical():
    out = evaluate_fire({"smoke_level": 88, "temperature_c": 95})
    assert out["category"] == "critical"
    assert out["score"] == 90
    assert any(r["rule"] == "FIRE-R2" for r in out["reasons"])
    assert any(r["rule"] == "FIRE-R4" for r in out["reasons"])


def test_fire_normal():
    out = evaluate_fire({"smoke_level": 3.5, "temperature_c": 31.5})
    assert out["category"] == "normal"
    assert out["score"] < 20


def test_fire_high_band():
    out = evaluate_fire({"smoke_level": 70, "temperature_c": 75})
    assert out["category"] == "high"
    assert any(r["rule"] == "FIRE-R1" for r in out["reasons"])


def test_fire_smoke_ppm_derivation():
    out = evaluate_fire({"smoke_ppm": 880, "temperature_c": 95})
    assert out["category"] == "critical"


def test_flood_bands():
    assert evaluate_flood({"water_level_cm": 60, "rain_mmh": 40})["category"] == "critical"
    assert evaluate_flood({"water_level_cm": 45, "rain_mmh": 40})["category"] == "high"
    assert evaluate_flood({"water_level_cm": 2, "rain_mmh": 0})["category"] == "normal"


def test_flood_rules():
    out = evaluate_flood({"water_level_cm": 45, "rain_mmh": 40})
    assert any(r["rule"] == "FLOOD-R2" for r in out["reasons"])
    assert any(r["rule"] == "FLOOD-R3" for r in out["reasons"])


def test_structural_bands():
    assert evaluate_structural({"tilt_deg": 1.2, "crack_mm": 1.5})["category"] == "critical"
    assert evaluate_structural({"tilt_deg": 0.95, "crack_mm": 1.05})["category"] == "high"
    assert evaluate_structural({"tilt_deg": 0.9, "crack_mm": 0.5})["category"] == "warning"
    assert evaluate_structural({"tilt_deg": 0.5, "crack_mm": 0.3})["category"] == "low"
    assert evaluate_structural({"tilt_deg": 0.06, "crack_mm": 0.1})["category"] == "normal"


def test_structural_rules():
    out = evaluate_structural({"tilt_deg": 0.95, "crack_mm": 1.05})
    assert any(r["rule"] == "STRUCT-R1" for r in out["reasons"])
    assert any(r["rule"] == "STRUCT-R3" for r in out["reasons"])


def test_score_bounds():
    for hazard, values in [
        (evaluate_fire, {"smoke_level": 100, "temperature_c": 120}),
        (evaluate_flood, {"water_level_cm": 100, "rain_mmh": 100}),
        (evaluate_structural, {"tilt_deg": 5, "crack_mm": 5}),
    ]:
        out = hazard(values)
        assert 0 <= out["score"] <= 100


def test_category_bands_canonical():
    assert categorize(10).value == "normal"
    assert categorize(30).value == "low"
    assert categorize(50).value == "warning"
    assert categorize(70).value == "high"
    assert categorize(95).value == "critical"
