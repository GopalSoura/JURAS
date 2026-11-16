from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class Origin(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    origin: Origin | None = None
    destination_building_id: str | None = None
    destination_node_code: str | None = None
    responder_type: str = "fire_vehicle"
    simulation_id: str | None = None
    hazard_building_id: str | None = None

    @model_validator(mode="after")
    def check_destination(self) -> "RouteRequest":
        if not self.destination_building_id and not self.destination_node_code:
            raise ValueError("destination_building_id or destination_node_code required")
        if self.responder_type not in ("fire_vehicle", "ambulance", "foot_responder"):
            raise ValueError("responder_type must be one of fire_vehicle, ambulance, foot_responder")
        return self


class RouteOut(BaseModel):
    route_id: str
    responder_type: str
    profile: str
    geometry: dict[str, Any]
    distance_m: int
    travel_s: int
    eta_s: int
    edge_ids: list[str]
    warnings: list[str]
    algorithm: str = "dijkstra"
    feasible: bool
    last_mile_m: int = 0
    note: str = ""


# ---------- OSM navigation (real road graph, not the demo grid) ----------


class NavigatePoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class NavigateRequest(BaseModel):
    origin: NavigatePoint
    destination: NavigatePoint
    profile: Literal["fire_truck", "responder_bike", "walking"] = "fire_truck"
    weighting: Literal["time", "distance"] = "time"


class NavigateGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(min_length=2)


class NavigateProperties(BaseModel):
    distance_m: int
    duration_s: int | None = None
    profile: str
    weighting: str = "time"
    algorithm: str = "astar_osm"
    duration_basis: str | None = None
    geometry_source: str = "openstreetmap"
    edge_count: int = 0
    edge_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    origin_snap_distance_m: float = 0
    destination_snap_distance_m: float = 0


class NavigateRouteFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: NavigateGeometry
    properties: NavigateProperties


class NavigateSnap(BaseModel):
    lat: float
    lng: float
    snapped: dict[str, float]
    snap_distance_m: float
    edge_id: str
    way_id: str
    road_name: str
    highway: str
    oneway: str


class NavigateResponse(BaseModel):
    route: NavigateRouteFeature
    origin: NavigateSnap
    destination: NavigateSnap
    warnings: list[str] = Field(default_factory=list)
