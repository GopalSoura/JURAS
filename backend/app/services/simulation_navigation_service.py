"""Simulation route planner backed by the real OSM navigation graph.

Produces the legacy WebSocket ``Route`` payloads (fire/medical/evacuation) so the
dashboard can draw Google-Maps-style road-following routes during simulations.
There is no synthetic demo-grid fallback: when the OSM graph is missing or a
route is infeasible, the payload keeps the contract shape with an empty path so
the frontend draws nothing instead of a fabricated straight line.
"""

from __future__ import annotations

from typing import Any

from app.routing.osm_graph import (
    NavigationError,
    NavigationGraph,
    RouteResult,
    RouteStep,
    compute_navigation,
)


def _step_payload(step: RouteStep) -> dict[str, Any]:
    return {
        "maneuver": step.maneuver,
        "instruction": step.instruction,
        "road_name": step.road_name,
        "highway": step.highway,
        "mode": step.mode,
        "distance_m": round(float(step.distance_m), 1),
        "duration_s": round(float(step.duration_s), 1),
        "start": step.start,
        "end": step.end,
    }


def _infeasible(
    profile: str,
    *,
    origin: list[float],
    destination: list[float],
    from_label: str,
    to_label: str,
    note: str,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "path": [],
        "foot_path": [],
        "length_m": 0,
        "travel_s": 0,
        "eta_s": 0,
        "feasible": False,
        "last_mile_m": 0,
        "note": note,
        "from": from_label,
        "to": to_label,
        "steps": [],
    }


def _route_payload(
    result: RouteResult,
    *,
    profile: str,
    from_label: str,
    to_label: str,
) -> dict[str, Any]:
    note = f"OSM road route to {to_label}." if profile != "evacuation" else f"OSM walking route to {to_label}."
    gaps: list[str] = []
    if result.access_distance_m > 25.0:
        gaps.append(f"start {round(result.access_distance_m)} m off-road")
    if result.egress_distance_m > 25.0:
        gaps.append(f"end {round(result.egress_distance_m)} m off-road")
    if gaps:
        note = f"{note} Endpoint snap gaps: {' and '.join(gaps)}; connectors are not drawn."
    return {
        "profile": profile,
        "path": result.geometry,
        "foot_path": [],
        "length_m": int(round(result.distance_m)),
        "travel_s": int(round(result.duration_s or result.road_duration_s)),
        "eta_s": int(round(result.duration_s or result.road_duration_s)),
        "feasible": True,
        "last_mile_m": 0,
        "note": note,
        "from": from_label,
        "to": to_label,
        "steps": [_step_payload(step) for step in result.steps],
    }


def _compute(
    graph: NavigationGraph,
    origin: list[float],
    destination: list[float],
    profile: str,
    hazards: list[dict[str, Any]] | None,
    floods: list[dict[str, Any]] | None,
    closures: list[dict[str, Any]] | None = None,
) -> RouteResult:
    return compute_navigation(
        graph,
        float(origin[1]),
        float(origin[0]),
        float(destination[1]),
        float(destination[0]),
        profile,
        "time",
        hazards=hazards,
        floods=floods,
        closures=closures,
    )


def plan_osm_routes_for_building(
    graph: NavigationGraph | None,
    *,
    building_center: list[float],
    building_name: str,
    fire_post: list[float],
    medical_post: list[float],
    assemblies: list[list[float]],
    fire_label: str = "Fire post",
    medical_label: str = "Medical post",
    assembly_labels: list[str] | None = None,
    hazards: list[dict[str, Any]] | None = None,
    floods: list[dict[str, Any]] | None = None,
    closures: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return fire/medical/evacuation routes on OSM geometry.

    When no OSM graph is loaded, every profile is returned as infeasible with an
    empty ``path``. The caller must never fall back to the synthetic demo grid.
    """
    labels = assembly_labels or [f"Assembly {index + 1}" for index in range(len(assemblies))]
    if graph is None or not graph.edges or not graph.nodes:
        note = "No OSM road graph is loaded; no simulation route can be drawn."
        return [
            _infeasible(
                "fire_truck",
                origin=fire_post,
                destination=building_center,
                from_label=fire_label,
                to_label=building_name,
                note=note,
            ),
            _infeasible(
                "medical",
                origin=medical_post,
                destination=building_center,
                from_label=medical_label,
                to_label=building_name,
                note=note,
            ),
            _infeasible(
                "evacuation",
                origin=building_center,
                destination=assemblies[0] if assemblies else building_center,
                from_label=building_name,
                to_label=labels[0] if labels else "assembly",
                note=note,
            ),
        ]

    out: list[dict[str, Any]] = []

    for profile, origin, from_label, mode in (
        ("fire_truck", fire_post, fire_label, "fire_truck"),
        ("medical", medical_post, medical_label, "responder_bike"),
    ):
        try:
            result = _compute(
                graph, origin, building_center, mode, hazards, floods, closures
            )
        except NavigationError as exc:
            out.append(
                _infeasible(
                    profile,
                    origin=origin,
                    destination=building_center,
                    from_label=from_label,
                    to_label=building_name,
                    note=f"No OSM route for this profile: {exc.message}",
                )
            )
            continue
        out.append(
            _route_payload(
                result,
                profile=profile,
                from_label=from_label,
                to_label=building_name,
            )
        )

    best: dict[str, Any] | None = None
    best_duration = float("inf")
    last_error: NavigationError | None = None
    for assembly, label in zip(assemblies, labels):
        try:
            result = _compute(graph, building_center, assembly, "walking", hazards, floods)
        except NavigationError as exc:
            last_error = exc
            continue
        payload = _route_payload(
            result,
            profile="evacuation",
            from_label=building_name,
            to_label=label,
        )
        if result.duration_s is not None and result.duration_s < best_duration:
            best_duration = result.duration_s
            best = payload
    if best is not None:
        out.append(best)
    else:
        fallback = assemblies[0] if assemblies else building_center
        note = (
            f"No OSM evacuation route: {last_error.message}"
            if last_error is not None
            else "No assembly point configured."
        )
        out.append(
            _infeasible(
                "evacuation",
                origin=building_center,
                destination=fallback,
                from_label=building_name,
                to_label=labels[0] if labels else "assembly",
                note=note,
            )
        )
    return out
