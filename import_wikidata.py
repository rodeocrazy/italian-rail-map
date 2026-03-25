"""
import_wikidata.py

Fetches Italian railway station adjacency data from Wikidata (P197 = adjacent station)
and imports it as edges into italy_rail.db.

Two-step process:
  1. Fetch adjacency data from Wikidata SPARQL endpoint
  2. Match Wikidata QIDs to OSM stations via the wikidata column, then by name/coords
  3. Insert clean edges into the database

Usage:
    python import_wikidata.py --db italy_rail.db

Optional: save the raw Wikidata response for reuse:
    python import_wikidata.py --db italy_rail.db --save-json wikidata_adjacency.json

Reuse a previously saved response (avoids re-querying):
    python import_wikidata.py --db italy_rail.db --load-json wikidata_adjacency.json
"""

import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("ERROR: requests not installed. Run: pip install requests")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Wikidata SPARQL query
# ---------------------------------------------------------------------------

SPARQL_QUERY = """
SELECT
  ?station ?stationLabel
  ?nextStation ?nextStationLabel
  ?osmId ?nextOsmId
  ?line ?lineLabel
  ?stationCoordLat ?stationCoordLon
  ?nextCoordLat ?nextCoordLon
WHERE {
  # Italian railway stations with an adjacent station declared
  ?station wdt:P17 wd:Q38 .
  ?station wdt:P31/wdt:P279* wd:Q55488 .
  ?station wdt:P197 ?nextStation .

  # OSM relation IDs for matching (P402 = OSM relation ID)
  OPTIONAL { ?station    wdt:P402 ?osmId }
  OPTIONAL { ?nextStation wdt:P402 ?nextOsmId }

  # Line (P81 = used by / on railway line)
  OPTIONAL { ?station wdt:P81 ?line }

  # Coordinates for fallback matching
  OPTIONAL {
    ?station wdt:P625 ?stationCoord .
    BIND(geof:latitude(?stationCoord)  AS ?stationCoordLat)
    BIND(geof:longitude(?stationCoord) AS ?stationCoordLon)
  }
  OPTIONAL {
    ?nextStation wdt:P625 ?nextCoord .
    BIND(geof:latitude(?nextCoord)  AS ?nextCoordLat)
    BIND(geof:longitude(?nextCoord) AS ?nextCoordLon)
  }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "it,en"
  }
}
"""

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "ItalyRailMapper/1.0 (https://github.com/rodeocrazy/italian-rail-map)",
    "Accept": "application/sparql-results+json",
}


def fetch_wikidata():
    print("Fetching adjacency data from Wikidata SPARQL ...")
    print("  (This may take 30-90 seconds for the full Italian network)")

    try:
        r = requests.get(
            SPARQL_ENDPOINT,
            params={"query": SPARQL_QUERY, "format": "json"},
            headers=HEADERS,
            timeout=120,
        )
        r.raise_for_status()
    except requests.exceptions.Timeout:
        sys.exit("ERROR: Wikidata query timed out. Try again or use --load-json with a saved file.")
    except requests.exceptions.RequestException as e:
        sys.exit(f"ERROR: Wikidata request failed: {e}")

    data = r.json()
    rows = data["results"]["bindings"]
    print(f"  Received {len(rows):,} adjacency pairs from Wikidata.")
    return rows


# ---------------------------------------------------------------------------
# Parse Wikidata rows
# ---------------------------------------------------------------------------

def qid(uri):
    """Extract Q12345 from http://www.wikidata.org/entity/Q12345"""
    if not uri:
        return None
    return uri.split("/")[-1]


def val(row, key):
    entry = row.get(key)
    return entry["value"] if entry else None


def parse_rows(rows):
    """
    Returns list of dicts:
      station_qid, station_name, station_osm_id,
      station_lat, station_lon,
      next_qid, next_name, next_osm_id,
      next_lat, next_lon,
      line_qid, line_name
    """
    parsed = []
    for row in rows:
        try:
            slat = val(row, "stationCoordLat")
            slon = val(row, "stationCoordLon")
            nlat = val(row, "nextCoordLat")
            nlon = val(row, "nextCoordLon")

            parsed.append({
                "station_qid":  qid(val(row, "station")),
                "station_name": val(row, "stationLabel"),
                "station_osm":  val(row, "osmId"),
                "station_lat":  float(slat) if slat else None,
                "station_lon":  float(slon) if slon else None,
                "next_qid":     qid(val(row, "nextStation")),
                "next_name":    val(row, "nextStationLabel"),
                "next_osm":     val(row, "nextOsmId"),
                "next_lat":     float(nlat) if nlat else None,
                "next_lon":     float(nlon) if nlon else None,
                "line_qid":     qid(val(row, "line")),
                "line_name":    val(row, "lineLabel"),
            })
        except (ValueError, KeyError):
            continue

    return parsed


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
# Build station matchers
# ---------------------------------------------------------------------------

def build_matchers(conn):
    """
    Returns three lookup functions:
      by_wikidata(qid)      -> osm_id or None
      by_osm_relation(id)   -> osm_id or None
      by_coords(lat, lon)   -> osm_id or None  (nearest within 300m)
    """
    rows = conn.execute(
        "SELECT osm_id, name, wikidata, lat, lon FROM stations WHERE osm_id > 0"
    ).fetchall()

    wikidata_map = {}
    for r in rows:
        if r[2]:
            # wikidata column stores e.g. "Q801185"
            wikidata_map[r[2].strip()] = r[0]

    def by_wikidata(qid_val):
        return wikidata_map.get(qid_val)

    def by_osm_relation(osm_id_str):
        # P402 is OSM *relation* ID, not the node ID we use as PK
        # Try a direct match first (unlikely but possible)
        try:
            oid = int(osm_id_str)
            row = conn.execute(
                "SELECT osm_id FROM stations WHERE osm_id = ?", (oid,)
            ).fetchone()
            return row[0] if row else None
        except (ValueError, TypeError):
            return None

    if HAS_NUMPY and rows:
        coords  = [[r[3], r[4]] for r in rows if r[3] and r[4]]
        ids     = [r[0] for r in rows if r[3] and r[4]]
        arr     = __import__("numpy").array(coords)

        def by_coords(lat, lon, max_km=0.3):
            if lat is None or lon is None:
                return None
            diffs = arr - [lat, lon]
            dists = __import__("numpy").sqrt(
                (diffs[:, 0] * 111.0) ** 2 + (diffs[:, 1] * 85.0) ** 2
            )
            idx = int(__import__("numpy").argmin(dists))
            return ids[idx] if dists[idx] <= max_km else None
    else:
        def by_coords(lat, lon, max_km=0.3):
            if lat is None or lon is None:
                return None
            best_id, best_dist = None, float("inf")
            for r in rows:
                if r[3] and r[4]:
                    d = haversine_km(lat, lon, r[3], r[4])
                    if d < best_dist:
                        best_dist, best_id = d, r[0]
            return best_id if best_dist <= max_km else None

    return by_wikidata, by_osm_relation, by_coords


# ---------------------------------------------------------------------------
# Match and insert
# ---------------------------------------------------------------------------

def resolve_station(entry, qid_key, name_key, osm_key, lat_key, lon_key,
                    by_wikidata, by_osm, by_coords):
    """Try three matching strategies in order of reliability."""
    # 1. Wikidata QID match (most reliable)
    osm_id = by_wikidata(entry.get(qid_key))
    if osm_id:
        return osm_id, "wikidata"

    # 2. OSM relation ID match
    osm_id = by_osm(entry.get(osm_key))
    if osm_id:
        return osm_id, "osm_relation"

    # 3. Coordinate snap
    osm_id = by_coords(entry.get(lat_key), entry.get(lon_key))
    if osm_id:
        return osm_id, "coords"

    return None, None


def insert_wikidata_edges(parsed, conn):
    by_wikidata, by_osm, by_coords = build_matchers(conn)

    # Ensure a wikidata line entry exists per line QID
    line_qid_to_id = {}
    for entry in parsed:
        lqid = entry.get("line_qid")
        if lqid and lqid not in line_qid_to_id:
            line_id = -abs(hash(f"wikidata_line_{lqid}")) % (10 ** 12)
            line_qid_to_id[lqid] = line_id
            conn.execute("""
                INSERT OR IGNORE INTO lines
                (osm_relation_id, name, ref, operator, network, route_type,
                 electrified, gauge, usage, active)
                VALUES (?, ?, NULL, NULL, NULL, 'train', NULL, NULL, 'wikidata', 1)
            """, (line_id, entry.get("line_name") or f"Wikidata line {lqid}"))

    # Synthetic line for entries with no line info
    unknown_line_id = -abs(hash("wikidata_unknown_line")) % (10 ** 12)
    conn.execute("""
        INSERT OR IGNORE INTO lines
        (osm_relation_id, name, ref, operator, network, route_type,
         electrified, gauge, usage, active)
        VALUES (?, 'Wikidata (line unknown)', NULL, NULL, NULL, 'train',
                NULL, NULL, 'wikidata', 1)
    """, (unknown_line_id,))
    conn.commit()

    edge_rows   = []
    seen_pairs  = set()
    stats = {"wikidata": 0, "osm_relation": 0, "coords": 0, "unmatched": 0}

    for entry in parsed:
        a_id, a_method = resolve_station(
            entry, "station_qid", "station_name", "station_osm",
            "station_lat", "station_lon",
            by_wikidata, by_osm, by_coords,
        )
        b_id, b_method = resolve_station(
            entry, "next_qid", "next_name", "next_osm",
            "next_lat", "next_lon",
            by_wikidata, by_osm, by_coords,
        )

        if not a_id:
            stats["unmatched"] += 1
            continue
        if not b_id:
            stats["unmatched"] += 1
            continue
        if a_id == b_id:
            continue

        pair = frozenset((a_id, b_id))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        stats[a_method] = stats.get(a_method, 0) + 1
        stats[b_method] = stats.get(b_method, 0) + 1

        # Distance
        row_a = conn.execute("SELECT lat, lon FROM stations WHERE osm_id=?", (a_id,)).fetchone()
        row_b = conn.execute("SELECT lat, lon FROM stations WHERE osm_id=?", (b_id,)).fetchone()
        if not row_a or not row_b:
            continue
        dist = haversine_km(row_a[0], row_a[1], row_b[0], row_b[1])

        line_id = line_qid_to_id.get(entry.get("line_qid"), unknown_line_id)
        edge_rows.append((line_id, a_id, b_id, 0, 1, round(dist, 4)))

    conn.executemany("""
        INSERT INTO edges
        (line_id, station_a_id, station_b_id, sequence_a, sequence_b, distance_km)
        VALUES (?,?,?,?,?,?)
    """, edge_rows)
    conn.commit()

    print(f"  Inserted {len(edge_rows):,} edges from Wikidata.")
    print(f"  Match methods: wikidata QID={stats['wikidata']}, "
          f"osm_relation={stats['osm_relation']}, "
          f"coords={stats['coords']}, "
          f"unmatched={stats['unmatched']}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(conn):
    print("\n--- Database summary ---")
    for table in ("stations", "lines", "edges"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<12} {count:>6,} rows")

    linked = conn.execute("""
        SELECT COUNT(DISTINCT s.osm_id)
        FROM stations s
        JOIN edges e ON s.osm_id = e.station_a_id OR s.osm_id = e.station_b_id
    """).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    print(f"\n  {linked:,}/{total:,} stations appear in at least one edge.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",        default="italy_rail.db")
    parser.add_argument("--save-json", default=None,
                        help="Save raw Wikidata response to this JSON file")
    parser.add_argument("--load-json", default=None,
                        help="Load previously saved Wikidata JSON instead of querying")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"ERROR: database not found: {db_path}")

    # Fetch or load raw data
    if args.load_json:
        load_path = Path(args.load_json)
        if not load_path.exists():
            sys.exit(f"ERROR: JSON file not found: {load_path}")
        print(f"Loading Wikidata response from {load_path} ...")
        with load_path.open(encoding="utf-8") as f:
            rows = json.load(f)
        print(f"  Loaded {len(rows):,} rows.")
    else:
        rows = fetch_wikidata()
        if args.save_json:
            save_path = Path(args.save_json)
            with save_path.open("w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            print(f"  Saved raw response to {save_path}")

    # Parse
    print("Parsing adjacency pairs ...")
    parsed = parse_rows(rows)
    print(f"  {len(parsed):,} valid pairs parsed.")

    # Import
    conn = sqlite3.connect(db_path)
    print("Matching stations and inserting edges ...")
    insert_wikidata_edges(parsed, conn)
    print_summary(conn)
    conn.close()
    print(f"\nDone. Database updated: {db_path}")


if __name__ == "__main__":
    main()