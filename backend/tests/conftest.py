import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base

TEST_URL = "postgresql+asyncpg://postgres:juras123@localhost:5432/juras_test"


@pytest.fixture(scope="session")
async def engine():
    e = create_async_engine(TEST_URL, pool_pre_ping=True)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await e.dispose()


@pytest.fixture
async def db(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))


@pytest.fixture
def test_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)

import pytest_asyncio
from sqlalchemy import func

from app.models import Building, Lane, LaneNode, Sensor


@pytest_asyncio.fixture
async def seeded_world(db):
    def wkt_point(pos):
        return f"POINT({pos[0]:.8f} {pos[1]:.8f})"

    def wkt_line(path):
        pts = ", ".join(f"{p[0]:.8f} {p[1]:.8f}" for p in path)
        return f"LINESTRING({pts})"

    node_a = LaneNode(code="A", label="Fire Post", kind="fire_post", pos=[74.8575, 32.7285], attributes={}, geom=wkt_point([74.8575, 32.7285]))
    node_b = LaneNode(code="B", label="Junction B", kind="junction", pos=[74.8585, 32.7285], attributes={}, geom=wkt_point([74.8585, 32.7285]))
    node_c = LaneNode(code="C", label="Junction C", kind="junction", pos=[74.8595, 32.7285], attributes={}, geom=wkt_point([74.8595, 32.7285]))
    db.add_all([node_a, node_b, node_c])
    await db.flush()

    lane_ab = Lane(
        code="A-B", name="Lane A-B", width_m=7.0, stairs=False, vehicle_access=True,
        blocked=False, surface="paved", length_m=93.6, node_a_code="A", node_b_code="B",
        path=[[74.8575, 32.7285], [74.8585, 32.7285]], attributes={},
        geom=wkt_line([[74.8575, 32.7285], [74.8585, 32.7285]]),
    )
    lane_bc = Lane(
        code="B-C", name="Lane B-C", width_m=7.0, stairs=False, vehicle_access=True,
        blocked=False, surface="paved", length_m=93.6, node_a_code="B", node_b_code="C",
        path=[[74.8585, 32.7285], [74.8595, 32.7285]], attributes={},
        geom=wkt_line([[74.8585, 32.7285], [74.8595, 32.7285]]),
    )
    db.add_all([lane_ab, lane_bc])
    await db.flush()

    center = [74.8580, 32.7286]
    footprint = [
        [74.8578, 32.7284], [74.8582, 32.7284], [74.8582, 32.7288], [74.8578, 32.7288], [74.8578, 32.7284],
    ]
    building = Building(
        code="B-T1", name="Test Building", floors=2, building_type="Storage",
        construction="Brick", occupancy=10, year_built=1950, height_m=6.6,
        priority=60, status="ok", center=center, footprint=footprint,
        access_node_code="B", attributes={"tilt_deg": 0.06, "crack_mm": 0.1},
        geom=f"POLYGON(({', '.join(f'{p[0]:.8f} {p[1]:.8f}' for p in footprint)}))",
        center_point=wkt_point(center),
    )
    db.add(building)
    await db.flush()

    sensor = Sensor(
        code="JM-T1", label="Smoke + temp, B-T1", kind="smoke_temp",
        building_id=building.id, node_code=None, status="active", source="simulation",
        pos=[center[0] + 0.00004, center[1]], attributes={},
        geom=wkt_point([center[0] + 0.00004, center[1]]),
    )
    db.add(sensor)
    await db.flush()
    await db.commit()
    return {"building": building, "sensor": sensor, "nodes": [node_a, node_b, node_c]}

