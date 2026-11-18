from app.ws.frontend_adapter import FrontendWorld


async def test_live_alert_can_be_resolved_without_db_incident():
    world = object.__new__(FrontendWorld)
    world.alerts = {
        "AL-FIRE-B-095": {
            "id": "AL-FIRE-B-095",
            "module": "fire",
            "status": "new",
            "building_id": "B-095",
        }
    }
    broadcasts: list[dict] = []
    resolved: list[str] = []

    async def broadcast(message: dict) -> None:
        broadcasts.append(message)

    async def on_resolved(alert: dict) -> None:
        resolved.append(alert["id"])

    world.broadcast = broadcast
    world._on_resolved = on_resolved

    await world._apply_live_alert_action("AL-FIRE-B-095", "resolve")

    alert = world.alerts["AL-FIRE-B-095"]
    assert alert["status"] == "resolved"
    assert alert["updated_at"] > 0
    assert broadcasts == [{"t": "alert", "alert": alert}]
    assert resolved == ["AL-FIRE-B-095"]
