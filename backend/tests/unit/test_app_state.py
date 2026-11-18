from app.state import AppState


def test_closure_changes_notify_listeners():
    state = AppState()
    calls: list[str] = []
    state.on_closures_changed(lambda: calls.append("changed"))

    closure = state.add_closure(lat=32.7285, lng=74.8575, radius_m=18.0)
    assert calls == ["changed"]

    assert state.remove_closure(closure["id"]) is True
    assert calls == ["changed", "changed"]

    assert state.remove_closure(closure["id"]) is False
    state.clear_closures()
    assert calls == ["changed", "changed"]

    state.add_closure(lat=32.7285, lng=74.8575)
    state.clear_closures()
    assert calls == ["changed", "changed", "changed", "changed"]


def test_closure_listener_can_be_removed():
    state = AppState()
    calls: list[str] = []
    listener = lambda: calls.append("changed")

    state.on_closures_changed(listener)
    state.add_closure(lat=32.7285, lng=74.8575)
    state.remove_closure_listener(listener)
    state.clear_closures()

    assert calls == ["changed"]
