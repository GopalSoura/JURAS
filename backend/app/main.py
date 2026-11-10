from datetime import datetime, timezone
from random import randint, uniform
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="JURAS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Demo-only seed records. Replace with PostGIS-backed repositories.
buildings = [
    {"id": "PM-B001", "name": "Demo Building 01", "risk_level": "medium", "lat": 32.7350, "lng": 74.8620, "verified": False},
    {"id": "PM-B002", "name": "Demo Building 02", "risk_level": "high", "lat": 32.7355, "lng": 74.8630, "verified": False},
    {"id": "PM-B003", "name": "Demo Building 03", "risk_level": "low", "lat": 32.7344, "lng": 74.8612, "verified": False},
]
lanes = [
    {"id":"PM-L001","name":"Demo lane A","width_m":2.2,"accessible":False,"stairs":True,
     "coordinates":[[74.8614,32.7346],[74.8621,32.7350],[74.8630,32.7354]]},
    {"id":"PM-L002","name":"Demo lane B","width_m":4.0,"accessible":True,"stairs":False,
     "coordinates":[[74.8610,32.7342],[74.8620,32.7347],[74.8632,32.7350]]},
]
sensors = [
    {"id":"SIM-FIRE-01","type":"fire","building_id":"PM-B002","lat":32.7355,"lng":74.8630,"mode":"simulation"},
    {"id":"SIM-WATER-01","type":"water","building_id":None,"lat":32.7347,"lng":74.8621,"mode":"simulation"},
    {"id":"SIM-TILT-01","type":"tilt","building_id":"PM-B001","lat":32.7350,"lng":74.8620,"mode":"simulation"},
]
readings = []
incidents = []

class ReadingIn(BaseModel):
    sensor_id: str
    metric: str
    value: float
    unit: str
    mode: Literal["simulation","hardware"] = "simulation"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class IncidentIn(BaseModel):
    incident_type: str
    severity: Literal["low","medium","high"]
    title: str
    lat: float
    lng: float
    source: str = "manual"

class IncidentStatusIn(BaseModel):
    status: Literal["active","acknowledged","resolved"]

@app.get("/")
def root():
    return {"project":"JURAS","pilot":"Purani Mandi","status":"running"}

@app.get("/health")
def health():
    return {"status":"healthy"}

@app.get("/api/buildings")
def get_buildings():
    return buildings

@app.get("/api/lanes")
def get_lanes():
    return lanes

@app.get("/api/sensors")
def get_sensors():
    return sensors

@app.get("/api/readings")
def get_readings():
    return readings[-100:]

@app.get("/api/incidents")
def get_incidents():
    return incidents

@app.post("/api/readings")
def add_reading(payload: ReadingIn):
    item = payload.model_dump()
    item["recorded_at"] = item["recorded_at"].isoformat()
    readings.append(item)
    severity = None
    if payload.metric == "smoke" and payload.value >= 700: severity = "high"
    elif payload.metric == "temperature" and payload.value >= 50: severity = "high"
    elif payload.metric == "water_level_cm" and payload.value >= 80: severity = "high"
    elif payload.metric == "tilt_change_deg" and payload.value >= 5: severity = "high"
    if severity:
        sensor = next((s for s in sensors if s["id"] == payload.sensor_id), None)
        incidents.append({
            "id":f"INC-{len(incidents)+1:03d}","incident_type":payload.metric,
            "severity":severity,"title":f"{payload.metric} threshold exceeded",
            "lat":sensor["lat"] if sensor else 32.7350,
            "lng":sensor["lng"] if sensor else 74.8620,"status":"active",
            "created_at":item["recorded_at"],"source":payload.mode
        })
    return {"accepted":True,"reading":item,"alert_created":bool(severity)}

@app.post("/api/incidents")
def create_incident(payload: IncidentIn):
    item=payload.model_dump()
    item.update({"id":f"INC-{len(incidents)+1:03d}","status":"active",
                 "created_at":datetime.now(timezone.utc).isoformat()})
    incidents.append(item)
    return item

@app.patch("/api/incidents/{incident_id}")
def update_incident(incident_id: str, payload: IncidentStatusIn):
    for item in incidents:
        if item["id"] == incident_id:
            item["status"] = payload.status
            return item
    raise HTTPException(status_code=404, detail="incident not found")

@app.post("/api/simulation/tick")
def simulation_tick():
    # Demo-only random data; never represent this as field measurement.
    samples = [
        {"sensor_id":"SIM-FIRE-01","metric":"smoke","value":randint(80,850),"unit":"raw"},
        {"sensor_id":"SIM-FIRE-01","metric":"temperature","value":round(uniform(28,62),1),"unit":"degC"},
        {"sensor_id":"SIM-WATER-01","metric":"water_level_cm","value":round(uniform(10,95),1),"unit":"cm"},
        {"sensor_id":"SIM-TILT-01","metric":"tilt_change_deg","value":round(uniform(0,6),2),"unit":"deg"},
    ]
    result=[]
    for s in samples:
        result.append(add_reading(ReadingIn(**s,mode="simulation")))
    return {"mode":"simulation","samples":result}
