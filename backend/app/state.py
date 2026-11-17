from __future__ import annotations

import threading
from typing import Any


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.hazards: dict[str, dict[str, Any]] = {}
        self.flood_zones: list[dict[str, Any]] = []
        self.closures: dict[str, dict[str, Any]] = {}
        self._closure_seq = 0

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

    def add_closure(
        self,
        *,
        lat: float,
        lng: float,
        radius_m: float = 15.0,
        reason: str = "Road closed",
        source: str = "manual",
    ) -> dict[str, Any]:
        with self._lock:
            self._closure_seq += 1
            closure_id = f"closure-{self._closure_seq}"
            data = {
                "id": closure_id,
                "lat": float(lat),
                "lng": float(lng),
                "pos": [float(lng), float(lat)],
                "radius_m": float(radius_m),
                "reason": reason,
                "source": source,
                "active": True,
            }
            self.closures[closure_id] = data
            return dict(data)

    def remove_closure(self, closure_id: str) -> bool:
        with self._lock:
            return self.closures.pop(closure_id, None) is not None

    def clear_closures(self) -> None:
        with self._lock:
            self.closures.clear()

    def closures_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self.closures.values()]

    def routing_ctx(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            hazards = [
                {"pos": h["pos"], "radius_m": h["radius_m"]}
                for h in self.hazards.values()
                if h.get("active", True)
            ]
            floods = list(self.flood_zones)
            closures = [
                {"pos": c["pos"], "radius_m": c["radius_m"]}
                for c in self.closures.values()
                if c.get("active", True)
            ]
        return {"hazards": hazards, "floods": floods, "closures": closures}


app_state = AppState()
