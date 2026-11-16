from __future__ import annotations

import threading
from typing import Any


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.hazards: dict[str, dict[str, Any]] = {}
        self.flood_zones: list[dict[str, Any]] = []

    def set_hazard(self, hazard_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self.hazards[hazard_id] = data

    def deactivate_hazard(self, hazard_id: str) -> None:
        with self._lock:
            if hazard_id in self.hazards:
                self.hazards[hazard_id]["active"] = False

    def clear_hazards(self) -> None:
        with self._lock:
            self.hazards.clear()

    def set_flood_zones(self, zones: list[dict[str, Any]]) -> None:
        with self._lock:
            self.flood_zones = zones

    def routing_ctx(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            hazards = [
                {"pos": h["pos"], "radius_m": h["radius_m"]}
                for h in self.hazards.values()
                if h.get("active", True)
            ]
            floods = list(self.flood_zones)
        return {"hazards": hazards, "floods": floods}


app_state = AppState()
