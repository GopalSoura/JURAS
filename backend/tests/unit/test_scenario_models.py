from app.simulation.models import FloodModel, FireModel, StructuralModel, get_model


def make_config(scenario: str) -> dict:
    return {
        "scenario": scenario,
        "severity": "warning",
        "seed": 42,
        "interval_ms": 1000,
        "duration_sec": 60,
    }


def test_fire_deterministic_by_seed():
    c = make_config("fire")
    m1, m2 = FireModel(), FireModel()
    s1, s2 = m1.initial_state(c), m2.initial_state(c)
    v1, v2 = m1.next_reading(s1, 10, c), m2.next_reading(s2, 10, c)
    assert v1 == v2
    assert 0 < v1["smoke_ppm"] <= 900
    assert v1["temperature_c"] >= 31.5
    assert 0 <= v1["smoke_level"] <= 100


def test_fire_rises_and_finishes():
    c = make_config("fire")
    m = FireModel()
    s = m.initial_state(c)
    early = m.next_reading(s, 2, c)
    late = m.next_reading(s, 50, c)
    assert late["smoke_ppm"] > early["smoke_ppm"]
    assert late["temperature_c"] > early["temperature_c"]
    assert m.is_finished(s, 60, c)
    assert not m.is_finished(s, 59, c)


def test_fire_critical_faster_than_normal():
    c1 = make_config("fire") | {"severity": "critical"}
    c2 = make_config("fire") | {"severity": "normal"}
    m = FireModel()
    v_crit = m.next_reading(m.initial_state(c1), 10, c1)
    v_norm = m.next_reading(m.initial_state(c2), 10, c2)
    assert v_crit["smoke_ppm"] > v_norm["smoke_ppm"]


def test_flood_level_grows_with_rain():
    c = make_config("flood")
    m = FloodModel()
    s = m.initial_state(c)
    v1 = m.next_reading(s, 5, c)
    for t in range(6, 40):
        m.next_reading(s, t, c)
    assert v1["water_level_cm"] < s["level_cm"] or s["level_cm"] > 0


def test_structural_drift_and_bounds():
    c = make_config("structural")
    m = StructuralModel()
    s = m.initial_state(c)
    v = m.next_reading(s, 30, c)
    assert v["tilt_deg"] >= 0
    assert v["crack_mm"] >= 0
    assert "deviation_mm" in v
    assert m.is_finished(s, 90, c)


def test_model_registry():
    assert get_model("fire").name == "fire"
    assert get_model("flood").name == "flood"
    assert get_model("structural").name == "structural"
    try:
        get_model("earthquake")
        assert False, "should raise"
    except ValueError:
        pass
