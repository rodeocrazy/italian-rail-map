"""
export_data.py

Exports stations and edges from italy_rail.db into JSON files
for the frontend to consume.

Usage:
    python export_data.py --db italy_rail.db --out public/data
"""

import argparse
import json
import sqlite3
from pathlib import Path


def export(db_path: Path, out_dir: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Stations
    stations = [dict(r) for r in conn.execute("""
        SELECT
            osm_id as id,
            name,
            official_name,
            railway,
            station,                                  
            station_category,
            operator,
            uic_ref,
            platforms,
            wheelchair,
            ele,
            active,
            addr_city,
            wikidata,
            wikipedia,
            lat,
            lon
        FROM stations
        WHERE name IS NOT NULL
    """).fetchall()]

    stations_path = out_dir / "stations.json"
    with stations_path.open("w", encoding="utf-8") as f:
        json.dump(stations, f, ensure_ascii=False)
    print(f"Exported {len(stations)} stations -> {stations_path}")

    # Edges - LEFT JOIN so physical topology edges are included
    edges = [dict(r) for r in conn.execute("""
        SELECT
            e.id,
            e.line_id,
            e.station_a_id,
            e.station_b_id,
            e.distance_km,
            COALESCE(l.name, 'Physical network') as line_name,
            COALESCE(l.route_type, 'rail')        as route_type,
            l.operator                             as line_operator,
            sa.lat as lat_a,
            sa.lon as lon_a,
            sb.lat as lat_b,
            sb.lon as lon_b
        FROM edges e
        LEFT JOIN lines l ON e.line_id = l.osm_relation_id
        JOIN stations sa ON e.station_a_id = sa.osm_id
        JOIN stations sb ON e.station_b_id = sb.osm_id
        WHERE l.usage IN ('wikidata', 'wikidata_p81')
          AND sa.lat IS NOT NULL
          AND sa.lon IS NOT NULL
          AND sb.lat IS NOT NULL
          AND sb.lon IS NOT NULL
    """).fetchall()]

    edges_path = out_dir / "edges.json"
    with edges_path.open("w", encoding="utf-8") as f:
        json.dump(edges, f, ensure_ascii=False)
    print(f"Exported {len(edges)} edges -> {edges_path}")

    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",  default="italy_rail.db")
    parser.add_argument("--out", default="public/data")
    args = parser.parse_args()

    db_path  = Path(args.db)
    out_dir  = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    export(db_path, out_dir)


if __name__ == "__main__":
    main()