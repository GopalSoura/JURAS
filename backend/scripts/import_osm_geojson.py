"""CLI: import the cleaned OSM GeoJSON datasets into the existing PostGIS tables.

Usage (from backend/):
    .\\.venv\\Scripts\\python.exe scripts\\import_osm_geojson.py
    .\\.venv\\Scripts\\python.exe scripts\\import_osm_geojson.py --buildings PATH --lanes PATH

Idempotent: re-running refreshes OSM rows (codes OSM-*) in place; demo rows
(B-0xx, lanes A-B, nodes A..Q), sensors, incidents and readings are untouched.
Re-running seed_demo_data.py wipes all tables — re-run this import afterwards.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionFactory
from app.services.osm_import_service import import_osm

DEFAULT_BUILDINGS = Path(__file__).resolve().parents[1] / "buildings.geojson"
DEFAULT_LANES = Path(__file__).resolve().parents[1] / "roads_lanes.geojson"


async def run(buildings: Path, lanes: Path) -> None:
    for p in (buildings, lanes):
        if not p.is_file():
            print(f"ERROR: dataset not found: {p}")
            sys.exit(2)
    async with SessionFactory() as session:
        stats = await import_osm(session, buildings, lanes)
        await session.commit()
    print("OSM import complete:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Import OSM GeoJSON into PostGIS (idempotent).")
    ap.add_argument("--buildings", default=str(DEFAULT_BUILDINGS))
    ap.add_argument("--lanes", default=str(DEFAULT_LANES))
    args = ap.parse_args()
    asyncio.run(run(Path(args.buildings), Path(args.lanes)))


if __name__ == "__main__":
    main()
