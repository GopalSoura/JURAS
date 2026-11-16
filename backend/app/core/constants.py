from enum import Enum

RULE_VERSION = "demo-v1"
DATA_LABEL = "Illustrative demo data, not real observation"


class Scenario(str, Enum):
    fire = "fire"
    flood = "flood"
    structural = "structural"


class SimulationSeverity(str, Enum):
    normal = "normal"
    warning = "warning"
    critical = "critical"


class SimulationStatus(str, Enum):
    queued = "queued"
    running = "running"
    paused = "paused"
    completed = "completed"
    stopped = "stopped"
    failed = "failed"


class RiskCategory(str, Enum):
    normal = "normal"
    low = "low"
    warning = "warning"
    high = "high"
    critical = "critical"


class Hazard(str, Enum):
    fire = "fire"
    flood = "flood"
    structural = "structural"


class IncidentStatus(str, Enum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    false_alarm = "false_alarm"


class IncidentSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReadingSource(str, Enum):
    simulation = "simulation"
    field = "field"
    imported = "imported"


class ResponderType(str, Enum):
    fire_vehicle = "fire_vehicle"
    ambulance = "ambulance"
    foot_responder = "foot_responder"


class SensorKind(str, Enum):
    smoke_temp = "smoke_temp"
    structure = "structure"
    rain_level = "rain_level"


class LaneNodeKind(str, Enum):
    junction = "junction"
    fire_post = "fire_post"
    medical_post = "medical_post"
    assembly = "assembly"


class BuildingStatus(str, Enum):
    ok = "ok"
    watch = "watch"
    inspect = "inspect"
    fire = "fire"


class Profile(str, Enum):
    fire_truck = "fire_truck"
    medical = "medical"
    evacuation = "evacuation"


RESPONDER_PROFILE = {
    ResponderType.fire_vehicle: Profile.fire_truck,
    ResponderType.ambulance: Profile.medical,
    ResponderType.foot_responder: Profile.evacuation,
}

CATEGORY_TO_SEVERITY = {
    RiskCategory.normal: IncidentSeverity.low,
    RiskCategory.low: IncidentSeverity.low,
    RiskCategory.warning: IncidentSeverity.medium,
    RiskCategory.high: IncidentSeverity.high,
    RiskCategory.critical: IncidentSeverity.critical,
}

CATEGORY_TO_FRONTEND_SEVERITY = {
    RiskCategory.normal: "low",
    RiskCategory.low: "low",
    RiskCategory.warning: "medium",
    RiskCategory.high: "high",
    RiskCategory.critical: "critical",
}

HAZARD_SENSOR_KIND = {
    Hazard.fire: SensorKind.smoke_temp,
    Hazard.flood: SensorKind.rain_level,
    Hazard.structural: SensorKind.structure,
}
