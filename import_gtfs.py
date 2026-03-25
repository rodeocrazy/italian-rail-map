"""
import_gtfs.py

Imports Trenitalia GTFS data into an existing italy_rail.db, adding:
  - New stations from stops.txt that don't exist yet
  - New edges from stop_times.txt sequential stop pairs
  - New lines from routes.txt

Usage:
    python import_gtfs.py \
        --gtfs  path/to/gtfs/folder \
        --db    italy_rail.db

The --gtfs argument should point to the folder containing
stops.txt, stop_times.txt, trips.txt, routes.txt.
"""

import argparse
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import numpy as np


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


# ---------------------------------------------------------------------------
# Load GTFS files
# ---------------------------------------------------------------------------

def load_gtfs(gtfs_dir: Path):
    required = ["stops.txt", "stop_times.txt", "trips.txt", "routes.txt"]
    for f in required:
        if not (gtfs_dir / f).exists():
            sys.exit(f"ERROR: missing {f} in {gtfs_dir}")

    stops      = pd.read_csv(gtfs_dir / "stops.txt")
    stop_times = pd.read_csv(gtfs_dir / "stop_times.txt")
    trips      = pd.read_csv(gtfs_dir / "trips.txt")
    routes     = pd.read_csv(gtfs_dir / "routes.txt")

    print(f"  stops:      {len(stops)}")
    print(f"  trips:      {len(trips)}")
    print(f"  stop_times: {len(stop_times)}")
    print(f"  routes:     {len(routes)}")

    return stops, stop_times, trips, routes


# ---------------------------------------------------------------------------
# Match GTFS stops to existing OSM stations
# ---------------------------------------------------------------------------

def build_station_matcher(conn: sqlite3.Connection):
    """
    Returns a function that, given (lat, lon), returns the osm_id of the
    nearest existing station within 500m, or None.
    """
    rows = conn.execute("SELECT osm_id, lat, lon FROM stations").fetchall()
    if not rows:
        return lambda lat, lon: None

    osm_ids = [r[0] for r in rows]
    coords  = np.array([[r[1], r[2]] for r in rows])

    def match(lat, lon, max_dist_km=0.5):
        diffs = coords - np.array([lat, lon])
        dists = np.sqrt((diffs[:, 0] * 111.0) ** 2 + (diffs[:, 1] * 85.0) ** 2)
        idx = int(np.argmin(dists))
        return osm_ids[idx] if dists[idx] <= max_dist_km else None

    return match


# ---------------------------------------------------------------------------
# Insert new stations for unmatched GTFS stops
# ---------------------------------------------------------------------------

def insert_gtfs_stations(stops: pd.DataFrame, match_fn, conn: sqlite3.Connection):
    """
    For GTFS stops that don't snap to an existing OSM station,
    insert them as new station rows using a synthetic negative osm_id
    (negative to avoid clashing with real OSM ids).
    """
    gtfs_id_to_osm = {}   # gtfs stop_id -> osm_id we'll use for edges
    new_rows = []

    for _, row in stops.iterrows():
        lat = float(row["stop_lat"])
        lon = float(row["stop_lon"])
        matched = match_fn(lat, lon)

        if matched is not None:
            gtfs_id_to_osm[row["stop_id"]] = matched
        else:
            # Synthetic id: use a large negative number based on stop_code hash
            synthetic_id = -abs(hash(row["stop_id"])) % (10 ** 12)
            gtfs_id_to_osm[row["stop_id"]] = synthetic_id
            new_rows.append((
                synthetic_id,
                row["stop_name"],
                None, None, None,        # official_name, short_name, alt_name
                "station",               # railway
                None, None,              # station_category, rfi_ref
                str(row.get("stop_code", "")),  # uic_ref
                str(row["stop_id"]),     # gtfs_id
                None, None, None,        # operator, owner, network
                None, None,              # platforms, wheelchair
                None,                    # ele
                None, None,              # start_date, end_date
                1,                       # active
                None, None,              # addr_city, addr_postcode
                None, None,              # wikidata, wikipedia
                lat, lon,
            ))

    if new_rows:
        conn.executemany("""
            INSERT OR IGNORE INTO stations VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, new_rows)
        conn.commit()
        print(f"  Inserted {len(new_rows)} new stations from GTFS stops.")
    else:
        print("  All GTFS stops matched to existing OSM stations.")

    matched_count = sum(1 for v in gtfs_id_to_osm.values() if v > 0)
    print(f"  {matched_count}/{len(stops)} stops matched to existing OSM stations.")

    return gtfs_id_to_osm


# ---------------------------------------------------------------------------
# Insert lines from GTFS routes
# ---------------------------------------------------------------------------

def insert_gtfs_lines(routes: pd.DataFrame, conn: sqlite3.Connection):
    """
    Insert GTFS routes as lines using negative IDs to avoid OSM id clash.
    """
    ROUTE_TYPE_MAP = {
        0: "tram", 1: "subway", 2: "train",
        3: "bus",  4: "ferry",  5: "cable_car",
        6: "gondola", 7: "funicular",
    }

    rows = []
    for _, r in routes.iterrows():
        synthetic_line_id = -abs(hash(str(r["route_id"]))) % (10 ** 12)
        route_type = ROUTE_TYPE_MAP.get(int(r.get("route_type", 2)), "train")
        rows.append((
            synthetic_line_id,
            str(r.get("route_long_name", "") or r.get("route_short_name", "")),
            str(r.get("route_short_name", "") or ""),
            None,           # operator
            None,           # network
            route_type,
            None, None,     # electrified, gauge
            None,           # usage
            1,              # active
        ))

    conn.executemany("""
        INSERT OR IGNORE INTO lines VALUES (?,?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()
    print(f"  Inserted {len(rows)} lines from GTFS routes.")

    # Return route_id -> synthetic_line_id mapping
    return {
        str(r["route_id"]): -abs(hash(str(r["route_id"]))) % (10 ** 12)
        for _, r in routes.iterrows()
    }


# ---------------------------------------------------------------------------
# Build edges from stop_times
# ---------------------------------------------------------------------------

def insert_gtfs_edges(
    stop_times: pd.DataFrame,
    trips: pd.DataFrame,
    gtfs_id_to_osm: dict,
    route_id_to_line: dict,
    conn: sqlite3.Connection,
):
    # Join trips to get route_id per trip
    trip_to_route = dict(zip(trips["trip_id"].astype(str), trips["route_id"].astype(str)))

    # Sort stop_times by trip then sequence
    st = stop_times.sort_values(["trip_id", "stop_sequence"]).copy()
    st["trip_id"] = st["trip_id"].astype(str)
    st["stop_id"] = st["stop_id"].astype(str)

    edge_rows   = []
    skipped     = 0
    seen_edges  = set()  # deduplicate (line_id, a, b) pairs

    for trip_id, group in st.groupby("trip_id"):
        route_id  = trip_to_route.get(trip_id)
        line_id   = route_id_to_line.get(route_id)
        if line_id is None:
            skipped += 1
            continue

        stop_ids = group["stop_id"].tolist()
        seqs     = group["stop_sequence"].tolist()

        for i in range(len(stop_ids) - 1):
            sid_a = stop_ids[i]
            sid_b = stop_ids[i + 1]

            osm_a = gtfs_id_to_osm.get(sid_a)
            osm_b = gtfs_id_to_osm.get(sid_b)

            if osm_a is None or osm_b is None or osm_a == osm_b:
                skipped += 1
                continue

            # Deduplicate: same line, same station pair
            key = (line_id, min(osm_a, osm_b), max(osm_a, osm_b))
            if key in seen_edges:
                continue
            seen_edges.add(key)

            # Get coords for distance
            row_a = conn.execute(
                "SELECT lat, lon FROM stations WHERE osm_id = ?", (osm_a,)
            ).fetchone()
            row_b = conn.execute(
                "SELECT lat, lon FROM stations WHERE osm_id = ?", (osm_b,)
            ).fetchone()

            if not row_a or not row_b:
                skipped += 1
                continue

            dist = haversine_km(row_a[0], row_a[1], row_b[0], row_b[1])

            edge_rows.append((
                line_id, osm_a, osm_b,
                seqs[i], seqs[i + 1],
                round(dist, 4),
            ))

    conn.executemany("""
        INSERT INTO edges (line_id, station_a_id, station_b_id,
                           sequence_a, sequence_b, distance_km)
        VALUES (?,?,?,?,?,?)
    """, edge_rows)
    conn.commit()

    print(f"  Inserted {len(edge_rows)} edges from GTFS.")
    if skipped:
        print(f"  Skipped {skipped} stop pairs (unresolvable or duplicate).")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(conn: sqlite3.Connection):
    print("\n--- Database summary ---")
    for table in ("stations", "lines", "edges"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<12} {count:>6} rows")

    linked = conn.execute("""
        SELECT COUNT(DISTINCT s.osm_id)
        FROM stations s
        JOIN edges e ON s.osm_id = e.station_a_id OR s.osm_id = e.station_b_id
    """).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    print(f"\n  {linked}/{total} stations appear in at least one edge.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs", required=True, help="Folder containing GTFS .txt files")
    parser.add_argument("--db",   default="italy_rail.db")
    args = parser.parse_args()

    gtfs_dir = Path(args.gtfs)
    if not gtfs_dir.is_dir():
        sys.exit(f"ERROR: {gtfs_dir} is not a directory")

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"ERROR: database not found: {db_path}. Run build_italy_rail_db.py first.")

    print(f"Loading GTFS from {gtfs_dir} ...")
    stops, stop_times, trips, routes = load_gtfs(gtfs_dir)

    conn = sqlite3.connect(db_path)

    print("\nMatching GTFS stops to OSM stations ...")
    match_fn        = build_station_matcher(conn)
    gtfs_id_to_osm  = insert_gtfs_stations(stops, match_fn, conn)

    print("\nInserting GTFS lines ...")
    route_id_to_line = insert_gtfs_lines(routes, conn)

    print("\nBuilding edges from stop sequences ...")
    insert_gtfs_edges(stop_times, trips, gtfs_id_to_osm, route_id_to_line, conn)

    print_summary(conn)
    conn.close()
    print(f"\nDone. Database updated: {db_path}")


if __name__ == "__main__":
    main()