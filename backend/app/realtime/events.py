import uuid
from datetime import datetime, timezone
from typing import Any


def make_event(name: str, data: dict[str, Any], simulation: bool = True) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event": name,
        "version": 1,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "simulation": simulation,
        "data": data,
    }
