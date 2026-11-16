"""initial JURAS schema with PostGIS geometry

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "buildings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("floors", sa.Integer, nullable=False, server_default="1"),
        sa.Column("building_type", sa.String(64), nullable=False, server_default="residential"),
        sa.Column("construction", sa.String(64), nullable=False, server_default=""),
        sa.Column("occupancy", sa.Integer, nullable=False, server_default="0"),
        sa.Column("year_built", sa.Integer, nullable=False, server_default="1970"),
        sa.Column("height_m", sa.Float, nullable=False, server_default="3.3"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("center", JSONB, nullable=False),
        sa.Column("footprint", JSONB, nullable=False),
        sa.Column("access_node_code", sa.String(32), nullable=False, server_default=""),
        sa.Column("attributes", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POLYGON", srid=4326), nullable=False),
        sa.Column("center_point", Geometry(geometry_type="POINT", srid=4326), nullable=False),
    )
    op.create_index("ix_buildings_geom", "buildings", ["geom"], postgresql_using="gist")

    op.create_table(
        "lane_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="junction"),
        sa.Column("pos", JSONB, nullable=False),
        sa.Column("attributes", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=False),
    )
    op.create_index("ix_lane_nodes_geom", "lane_nodes", ["geom"], postgresql_using="gist")

    op.create_table(
        "lanes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("width_m", sa.Float, nullable=False),
        sa.Column("stairs", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("slope_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("vehicle_access", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("blocked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("surface", sa.String(32), nullable=False, server_default="paved"),
        sa.Column("length_m", sa.Float, nullable=False, server_default="0"),
        sa.Column("node_a_code", sa.String(32), sa.ForeignKey("lane_nodes.code"), nullable=False),
        sa.Column("node_b_code", sa.String(32), sa.ForeignKey("lane_nodes.code"), nullable=False),
        sa.Column("path", JSONB, nullable=False),
        sa.Column("attributes", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geom", Geometry(geometry_type="LINESTRING", srid=4326), nullable=False),
    )
    op.create_index("ix_lanes_geom", "lanes", ["geom"], postgresql_using="gist")

    op.create_table(
        "graph_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("from_node", sa.String(32), nullable=False),
        sa.Column("to_node", sa.String(32), nullable=False),
        sa.Column("lane_code", sa.String(64), nullable=False),
        sa.Column("length_m", sa.Float, nullable=False, server_default="0"),
        sa.Column("cost", sa.Float, nullable=False, server_default="0"),
        sa.Column("width_m", sa.Float, nullable=False, server_default="0"),
        sa.Column("stairs", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("slope_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("vehicle_access", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("blocked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_graph_edges_from_node", "graph_edges", ["from_node"])
    op.create_index("ix_graph_edges_to_node", "graph_edges", ["to_node"])

    op.create_table(
        "sensors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "building_id", UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True
        ),
        sa.Column("node_code", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(16), nullable=False, server_default="simulation"),
        sa.Column("pos", JSONB, nullable=False),
        sa.Column("attributes", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=False),
    )
    op.create_index("ix_sensors_kind", "sensors", ["kind"])
    op.create_index("ix_sensors_geom", "sensors", ["geom"], postgresql_using="gist")

    op.create_table(
        "simulations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario", sa.String(32), nullable=False),
        sa.Column(
            "target_building_id", UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True
        ),
        sa.Column("target_node_code", sa.String(32), nullable=True),
        sa.Column("target_sensor_id", UUID(as_uuid=True), sa.ForeignKey("sensors.id"), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="warning"),
        sa.Column("seed", sa.Integer, nullable=False, server_default="42"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("interval_ms", sa.Integer, nullable=False, server_default="2000"),
        sa.Column("duration_sec", sa.Integer, nullable=False, server_default="60"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor", sa.String(64), nullable=False, server_default="dashboard"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("attributes", JSONB),
    )
    op.create_index("ix_simulations_scenario", "simulations", ["scenario"])
    op.create_index("ix_simulations_status", "simulations", ["status"])
    op.create_index("ix_simulations_target_building", "simulations", ["target_building_id"])

    op.create_table(
        "readings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("sensor_id", UUID(as_uuid=True), sa.ForeignKey("sensors.id"), nullable=True),
        sa.Column("building_id", UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
        sa.Column(
            "simulation_id", UUID(as_uuid=True), sa.ForeignKey("simulations.id"), nullable=True
        ),
        sa.Column("hazard", sa.String(32), nullable=False),
        sa.Column("values", JSONB, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="simulation"),
        sa.Column("simulation", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_readings_sensor_observed", "readings", ["sensor_id", "observed_at"])
    op.create_index("ix_readings_building_observed", "readings", ["building_id", "observed_at"])

    op.create_table(
        "risk_assessments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_code", sa.String(64), nullable=False),
        sa.Column("hazard", sa.String(32), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("reasons", JSONB),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulation_id", UUID(as_uuid=True), sa.ForeignKey("simulations.id"), nullable=True),
        sa.Column("rule_version", sa.String(16), nullable=False, server_default="demo-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_risk_score_range"),
    )
    op.create_index(
        "ix_risk_entity_time",
        "risk_assessments",
        ["entity_type", "entity_id", "assessed_at"],
    )

    op.create_table(
        "incidents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("hazard", sa.String(32), nullable=False),
        sa.Column("building_id", UUID(as_uuid=True), sa.ForeignKey("buildings.id"), nullable=True),
        sa.Column("node_code", sa.String(32), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=False, server_default=""),
        sa.Column("source", sa.String(16), nullable=False, server_default="simulation"),
        sa.Column("simulation_id", UUID(as_uuid=True), sa.ForeignKey("simulations.id"), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pos", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=False),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_hazard", "incidents", ["hazard"])
    op.create_index("ix_incidents_building", "incidents", ["building_id"])
    op.create_index("ix_incidents_geom", "incidents", ["geom"], postgresql_using="gist")

    op.create_table(
        "incident_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("incident_id", UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("old_status", sa.String(16), nullable=True),
        sa.Column("new_status", sa.String(16), nullable=True),
        sa.Column("actor", sa.String(64), nullable=False, server_default="system"),
        sa.Column("note", sa.String(1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incident_events_incident", "incident_events", ["incident_id"])


def downgrade() -> None:
    op.drop_table("incident_events")
    op.drop_table("incidents")
    op.drop_table("risk_assessments")
    op.drop_table("readings")
    op.drop_table("simulations")
    op.drop_table("sensors")
    op.drop_table("graph_edges")
    op.drop_table("lanes")
    op.drop_table("lane_nodes")
    op.drop_table("buildings")
