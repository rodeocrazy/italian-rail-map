"""
build_italy_rail_db.py

Parses two Overpass API JSON files into a SQLite database:
  - stations JSON  -> stations table
  - routes JSON    -> edges table + lines table

Usage:
    python build_italy_rail_db.py \
        --stations Train_station_data.json \
        --routes   Train_routes_data.json \
        --db       italy_rail.db

If --routes is omitted the script builds only the stations table.
"""

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def tag(element, key, default=None):
    return element.get("tags", {}).get(key, default)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    osm_id          INTEGER PRIMARY KEY,
    name            TEXT,
    official_name   TEXT,
    short_name      TEXT,
    alt_name        TEXT,
    railway         TEXT,
    station         TEXT,
    station_category TEXT,
    rfi_ref         TEXT,
    uic_ref         TEXT,
    gtfs_id         TEXT,
    operator        TEXT,
    owner           TEXT,
    network         TEXT,
    platforms       INTEGER,
    wheelchair      TEXT,
    ele             REAL,
    start_date      TEXT,
    end_date        TEXT,
    active          INTEGER,
    addr_city       TEXT,
    addr_postcode   TEXT,
    wikidata        TEXT,
    wikipedia       TEXT,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS lines (
    osm_relation_id INTEGER PRIMARY KEY,
    name            TEXT,
    ref             TEXT,
    operator        TEXT,
    network         TEXT,
    route_type      TEXT,
    electrified     TEXT,
    gauge           TEXT,
    usage           TEXT,
    active          INTEGER
);

CREATE TABLE IF NOT EXISTS edges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id         INTEGER REFERENCES lines(osm_relation_id),
    station_a_id    INTEGER REFERENCES stations(osm_id),
    station_b_id    INTEGER REFERENCES stations(osm_id),
    sequence_a      INTEGER,
    sequence_b      INTEGER,
    distance_km     REAL
);

CREATE INDEX IF NOT EXISTS idx_edges_a    ON edges(station_a_id);
CREATE INDEX IF NOT EXISTS idx_edges_b    ON edges(station_b_id);
CREATE INDEX IF NOT EXISTS idx_edges_line ON edges(line_id);
CREATE INDEX IF NOT EXISTS idx_stations_name ON stations(name);
"""


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------

def is_active(element):
    tags = element.get("tags", {})
    inactive_signals = [
        tags.get("disused"),
        tags.get("abandoned"),
        tags.get("closed"),
        tags.get("end_date"),
        tags.get("disused:railway"),
        tags.get("abandoned:railway"),
    ]
    return 0 if any(v and v not in ("no",) for v in inactive_signals) else 1


def parse_stations(path: Path, conn: sqlite3.Connection):
    print(f"Parsing stations from {path.name} ...")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])
    rows = []
    for e in elements:
        if e.get("type") != "node":
            continue
        if not e.get("lat") or not e.get("lon"):
            continue

        platforms_raw = tag(e, "platforms")
        try:
            platforms = int(platforms_raw) if platforms_raw else None
        except ValueError:
            platforms = None

        ele_raw = tag(e, "ele")
        try:
            ele = float(ele_raw) if ele_raw else None
        except ValueError:
            ele = None

        rows.append((
            e["id"],
            tag(e, "name"),
            tag(e, "official_name"),
            tag(e, "short_name"),
            tag(e, "alt_name"),
            tag(e, "railway"),
            tag(e, "station"),
            tag(e, "railway:station_category") or tag(e, "RFI:Category"),
            tag(e, "ref:RFI") or tag(e, "name:rfi"),
            tag(e, "uic_ref"),
            tag(e, "gtfs_id"),
            tag(e, "operator"),
            tag(e, "owner"),
            tag(e, "network"),
            platforms,
            tag(e, "wheelchair"),
            ele,
            tag(e, "start_date"),
            tag(e, "end_date"),
            is_active(e),
            tag(e, "addr:city"),
            tag(e, "addr:postcode"),
            tag(e, "wikidata"),
            tag(e, "wikipedia"),
            e["lat"],
            e["lon"],
        ))

    conn.executemany("""
        INSERT OR REPLACE INTO stations VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """, rows)
    conn.commit()
    print(f"  Inserted {len(rows)} stations.")
    return {e["id"]: e for e in elements if e.get("type") == "node"}


# ---------------------------------------------------------------------------
# Routes / edges
# ---------------------------------------------------------------------------

def parse_routes(path: Path, conn: sqlite3.Connection, node_index: dict):
    print(f"Parsing routes from {path.name} ...")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])

    # Node lookup: routes file nodes + stations nodes
    route_nodes = {e["id"]: e for e in elements if e.get("type") == "node"}
    all_nodes   = {**route_nodes, **node_index}

    # Way lookup
    all_ways = {e["id"]: e for e in elements if e.get("type") == "way"}

    def way_centroid(way_id):
        way = all_ways.get(way_id)
        if not way:
            return None
        coords = [
            (all_nodes[n]["lat"], all_nodes[n]["lon"])
            for n in way.get("nodes", [])
            if n in all_nodes and "lat" in all_nodes[n]
        ]
        if not coords:
            return None
        return (
            sum(c[0] for c in coords) / len(coords),
            sum(c[1] for c in coords) / len(coords),
        )

    # Spatial index over known stations for snapping way centroids
    try:
        import numpy as np
        station_list   = [n for n in node_index.values() if "lat" in n and "lon" in n]
        station_coords = np.array([[s["lat"], s["lon"]] for s in station_list])

        def nearest_station(lat, lon, max_dist_km=0.3):
            diffs = station_coords - np.array([lat, lon])
            dists = np.sqrt((diffs[:, 0] * 111.0) ** 2 + (diffs[:, 1] * 85.0) ** 2)
            idx = int(np.argmin(dists))
            return station_list[idx] if dists[idx] <= max_dist_km else None

    except ImportError:
        print("  (numpy not found — way-member snapping disabled, install with: pip install numpy)")
        def nearest_station(lat, lon, max_dist_km=0.3):
            return None

    relations = [e for e in elements if e.get("type") == "relation"]
    print(f"  Found {len(relations)} route relations.")

    STOP_ROLES = {
        "stop", "stop_exit_only", "stop_entry_only",
        "platform", "platform_exit_only", "platform_entry_only",
    }

    line_rows  = []
    edge_rows  = []
    skipped_edges = 0

    for rel in relations:
        rid = rel["id"]
        t   = rel.get("tags", {})

        if t.get("type") != "route":
            continue

        route_type = t.get("route", "train")

        line_rows.append((
            rid,
            t.get("name"),
            t.get("ref"),
            t.get("operator"),
            t.get("network"),
            route_type,
            t.get("electrified"),
            t.get("gauge"),
            t.get("usage"),
            1 if not t.get("disused") else 0,
        ))

        stops = []
        for member in rel.get("members", []):
            role  = member.get("role", "")
            mtype = member.get("type")
            ref   = member["ref"]

            # Accept blank role too — some Italian routes omit it on stop nodes
            if role not in STOP_ROLES and role != "":
                continue

            if mtype == "node":
                if ref in all_nodes:
                    stops.append((ref, all_nodes[ref]))

            elif mtype == "way" and role in STOP_ROLES:
                centroid = way_centroid(ref)
                if centroid is None:
                    continue
                clat, clon = centroid
                snapped = nearest_station(clat, clon)
                if snapped:
                    stops.append((snapped["id"], snapped))
                else:
                    synthetic = {"id": ref, "lat": clat, "lon": clon}
                    stops.append((ref, synthetic))

        # Deduplicate consecutive identical stops
        deduped = []
        for stop in stops:
            if not deduped or deduped[-1][0] != stop[0]:
                deduped.append(stop)

        # Build sequential edges
        for i in range(len(deduped) - 1):
            id_a, node_a = deduped[i]
            id_b, node_b = deduped[i + 1]

            try:
                dist = haversine_km(
                    node_a["lat"], node_a["lon"],
                    node_b["lat"], node_b["lon"],
                )
            except KeyError:
                skipped_edges += 1
                continue

            edge_rows.append((
                rid, id_a, id_b, i, i + 1, round(dist, 4),
            ))

    conn.executemany("""
        INSERT OR REPLACE INTO lines VALUES (?,?,?,?,?,?,?,?,?,?)
    """, line_rows)

    conn.executemany("""
        INSERT INTO edges (line_id, station_a_id, station_b_id,
                           sequence_a, sequence_b, distance_km)
        VALUES (?,?,?,?,?,?)
    """, edge_rows)

    conn.commit()
    print(f"  Inserted {len(line_rows)} lines.")
    print(f"  Inserted {len(edge_rows)} edges.")
    if skipped_edges:
        print(f"  Skipped {skipped_edges} edges (missing geometry).")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(conn: sqlite3.Connection):
    print("\n--- Database summary ---")
    for table in ("stations", "lines", "edges"):
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<12} {count:>6} rows")
        except sqlite3.OperationalError:
            pass

    try:
        linked = conn.execute("""
            SELECT COUNT(DISTINCT s.osm_id)
            FROM stations s
            JOIN edges e ON s.osm_id = e.station_a_id OR s.osm_id = e.station_b_id
        """).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        print(f"\n  {linked}/{total} stations appear in at least one edge.")
    except sqlite3.OperationalError:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build Italy rail SQLite DB from Overpass JSON.")
    parser.add_argument("--stations", required=True)
    parser.add_argument("--routes",   default=None)
    parser.add_argument("--db",       default="italy_rail.db")
    args = parser.parse_args()

    stations_path = Path(args.stations)
    if not stations_path.exists():
        sys.exit(f"ERROR: stations file not found: {stations_path}")

    db_path = Path(args.db)
    print(f"Output database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    node_index = parse_stations(stations_path, conn)

    if args.routes:
        routes_path = Path(args.routes)
        if not routes_path.exists():
            sys.exit(f"ERROR: routes file not found: {routes_path}")
        parse_routes(routes_path, conn, node_index)
    else:
        print("No routes file provided — skipping edges table.")

    print_summary(conn)
    conn.close()
    print(f"\nDone. Database written to {db_path}")


if __name__ == "__main__":
    main()