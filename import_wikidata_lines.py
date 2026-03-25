"""
import_wikidata_lines.py

Supplements existing Wikidata P197 edges by using P81 (on railway line)
to infer adjacency for stations that have no P197 data.

Strategy:
  1. Fetch all Italian stations with their P81 lines from Wikidata
  2. For each line, collect all stations on it
  3. Sort those stations geographically along the line direction
  4. Connect each station to its nearest neighbours in that sorted order
  5. Only create edges for stations that currently have no edges

Usage:
    python import_wikidata_lines.py --db italy_rail.db
    python import_wikidata_lines.py --db italy_rail.db --save-json wikidata_lines.json
    python import_wikidata_lines.py --db italy_rail.db --load-json wikidata_lines.json
"""

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("ERROR: pip install requests")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# SPARQL
# ---------------------------------------------------------------------------

SPARQL_QUERY = """
SELECT
  ?station ?stationLabel
  ?line ?lineLabel
  ?osmId
  ?lat ?lon
WHERE {
  ?station wdt:P17 wd:Q38 .
  ?station wdt:P31/wdt:P279* wd:Q55488 .
  ?station wdt:P81 ?line .
  OPTIONAL { ?station wdt:P402 ?osmId }
  OPTIONAL {
    ?station wdt:P625 ?coord .
    BIND(geof:latitude(?coord)  AS ?lat)
    BIND(geof:longitude(?coord) AS ?lon)
  }
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "it,en"
  }
}
"""

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "ItalyRailMapper/1.0 (https://github.com/rodeocrazy/italian-rail-map)",
    "Accept":     "application/sparql-results+json",
}


def fetch_wikidata():
    print("Fetching P81 line data from Wikidata ...")
    print("  (This may take 30-90 seconds)")
    try:
        r = requests.get(
            SPARQL_ENDPOINT,
            params={"query": SPARQL_QUERY, "format": "json"},
            headers=HEADERS,
            timeout=120,
        )
        r.raise_for_status()
    except requests.exceptions.Timeout:
        sys.exit("ERROR: Wikidata query timed out. Try --load-json with a saved file.")
    except requests.exceptions.RequestException as e:
        sys.exit(f"ERROR: {e}")

    rows = r.json()["results"]["bindings"]
    print(f"  Received {len(rows):,} rows.")
    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def qid(uri):
    return uri.split("/")[-1] if uri else None

def val(row, key):
    e = row.get(key)
    return e["value"] if e else None

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ---------------------------------------------------------------------------
# Parse rows into line -> [stations] mapping
# ---------------------------------------------------------------------------

def parse_rows(rows):
    """
    Returns:
      lines: dict of line_qid -> { name, stations: [{ qid, name, osm_id, lat, lon }] }
    """
    lines = {}
    for row in rows:
        line_qid  = qid(val(row, "line"))
        line_name = val(row, "lineLabel")
        sta_qid   = qid(val(row, "station"))
        sta_name  = val(row, "stationLabel")
        osm_id    = val(row, "osmId")

        try:
            lat = float(val(row, "lat")) if val(row, "lat") else None
            lon = float(val(row, "lon")) if val(row, "lon") else None
        except ValueError:
            lat = lon = None

        if not line_qid or not sta_qid:
            continue

        if line_qid not in lines:
            lines[line_qid] = {"name": line_name, "stations": []}

        lines[line_qid]["stations"].append({
            "qid":    sta_qid,
            "name":   sta_name,
            "osm_id": osm_id,
            "lat":    lat,
            "lon":    lon,
        })

    print(f"  Parsed {len(lines):,} lines with station lists.")
    return lines


# ---------------------------------------------------------------------------
# Match Wikidata stations to OSM stations in DB
# ---------------------------------------------------------------------------

def build_matcher(conn):
    rows = conn.execute(
        "SELECT osm_id, wikidata, lat, lon FROM stations WHERE osm_id > 0"
    ).fetchall()

    wikidata_map = {r[1].strip(): r[0] for r in rows if r[1]}

    def by_wikidata(q):
        return wikidata_map.get(q)

    if HAS_NUMPY and rows:
        valid = [(r[0], r[2], r[3]) for r in rows if r[2] and r[3]]
        ids   = [v[0] for v in valid]
        arr   = np.array([[v[1], v[2]] for v in valid])

        def by_coords(lat, lon, max_km=0.3):
            if lat is None or lon is None:
                return None
            diffs = arr - [lat, lon]
            dists = np.sqrt((diffs[:,0]*111)**2 + (diffs[:,1]*85)**2)
            idx = int(np.argmin(dists))
            return ids[idx] if dists[idx] <= max_km else None
    else:
        def by_coords(lat, lon, max_km=0.3):
            return None

    return by_wikidata, by_coords


def resolve(station, by_wikidata, by_coords):
    osm_id = by_wikidata(station["qid"])
    if osm_id:
        return osm_id
    return by_coords(station["lat"], station["lon"])


# ---------------------------------------------------------------------------
# Sort stations along a line using PCA / projection
# ---------------------------------------------------------------------------

def sort_stations_along_line(stations_with_coords):
    """
    Project stations onto the principal axis of their coordinate cloud
    and return them sorted along that axis.
    Uses simple PCA — works well for lines that run in a consistent direction.
    """
    if len(stations_with_coords) < 2:
        return stations_with_coords

    coords = [(s["lat"], s["lon"]) for s in stations_with_coords]
    lats   = [c[0] for c in coords]
    lons   = [c[1] for c in coords]

    mean_lat = sum(lats) / len(lats)
    mean_lon = sum(lons) / len(lons)

    # Covariance-based principal axis
    cov_ll = sum((la - mean_lat) * (lo - mean_lon) for la, lo in coords) / len(coords)
    var_la = sum((la - mean_lat)**2 for la in lats) / len(lats)
    var_lo = sum((lo - mean_lon)**2 for lo in lons) / len(lons)

    # Principal axis direction
    if abs(cov_ll) < 1e-10:
        axis = (1.0, 0.0) if var_la >= var_lo else (0.0, 1.0)
    else:
        # Eigenvector of 2x2 covariance matrix
        diff = var_la - var_lo
        hyp  = math.sqrt(diff**2 + 4 * cov_ll**2)
        axis = (diff + hyp, 2 * cov_ll)
        norm = math.sqrt(axis[0]**2 + axis[1]**2)
        axis = (axis[0]/norm, axis[1]/norm)

    # Project each station onto axis
    def project(s):
        return (s["lat"] - mean_lat) * axis[0] + (s["lon"] - mean_lon) * axis[1]

    return sorted(stations_with_coords, key=project)


# ---------------------------------------------------------------------------
# Find stations with no existing edges
# ---------------------------------------------------------------------------

def get_unconnected_station_ids(conn, max_edges=1):
    rows = conn.execute("""
        SELECT s.osm_id, COUNT(e.id) as cnt
        FROM stations s
        LEFT JOIN edges e ON s.osm_id = e.station_a_id OR s.osm_id = e.station_b_id
        WHERE s.osm_id > 0
        GROUP BY s.osm_id
        HAVING cnt <= ?
    """, (max_edges,)).fetchall()
    return set(r[0] for r in rows)


# ---------------------------------------------------------------------------
# Build and insert edges
# ---------------------------------------------------------------------------

def insert_line_edges(lines, conn):
    by_wikidata, by_coords = build_matcher(conn)
    unconnected = get_unconnected_station_ids(conn)
    print(f"  {len(unconnected):,} stations currently have fewer than 2 edges.")

    # Create synthetic line entries for P81 lines
    line_qid_to_id = {}
    for line_qid, line_data in lines.items():
        line_id = -abs(hash(f"p81_line_{line_qid}")) % (10**12)
        line_qid_to_id[line_qid] = line_id
        conn.execute("""
            INSERT OR IGNORE INTO lines
            (osm_relation_id, name, ref, operator, network, route_type,
             electrified, gauge, usage, active)
            VALUES (?, ?, NULL, NULL, NULL, 'train', NULL, NULL, 'wikidata_p81', 1)
        """, (line_id, line_data["name"] or f"Line {line_qid}"))
    conn.commit()

    edge_rows  = []
    seen_pairs = set()
    stats = {"edges_added": 0, "lines_processed": 0, "skipped_lines": 0}

    for line_qid, line_data in lines.items():
        stations = line_data["stations"]

        # Resolve each station to an OSM id
        resolved = []
        for s in stations:
            osm_id = resolve(s, by_wikidata, by_coords)
            if osm_id and s["lat"] and s["lon"]:
                resolved.append({**s, "osm_id_resolved": osm_id})

        if len(resolved) < 2:
            stats["skipped_lines"] += 1
            continue

        # Only process lines that have at least one unconnected station
        line_osm_ids = {s["osm_id_resolved"] for s in resolved}
        if not line_osm_ids & unconnected:
            stats["skipped_lines"] += 1
            continue

        stats["lines_processed"] += 1

        # Sort stations along the line
        sorted_stations = sort_stations_along_line(resolved)

        line_id = line_qid_to_id[line_qid]

        # Connect consecutive stations
        for i in range(len(sorted_stations) - 1):
            a = sorted_stations[i]
            b = sorted_stations[i + 1]
            id_a = a["osm_id_resolved"]
            id_b = b["osm_id_resolved"]

            if id_a == id_b:
                continue

            pair = frozenset((id_a, id_b))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])

            # Skip implausibly long edges
            if dist > 100:
                continue

            edge_rows.append((line_id, id_a, id_b, i, i+1, round(dist, 4)))
            stats["edges_added"] += 1

    conn.executemany("""
        INSERT INTO edges
        (line_id, station_a_id, station_b_id, sequence_a, sequence_b, distance_km)
        VALUES (?,?,?,?,?,?)
    """, edge_rows)
    conn.commit()

    print(f"  Processed {stats['lines_processed']:,} lines, "
          f"skipped {stats['skipped_lines']:,} (no unconnected stations).")
    print(f"  Inserted {stats['edges_added']:,} new edges.")


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
    parser.add_argument("--save-json", default=None)
    parser.add_argument("--load-json", default=None)
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"ERROR: database not found: {db_path}")

    if args.load_json:
        load_path = Path(args.load_json)
        if not load_path.exists():
            sys.exit(f"ERROR: {load_path} not found")
        print(f"Loading from {load_path} ...")
        with load_path.open(encoding="utf-8") as f:
            rows = json.load(f)
        print(f"  Loaded {len(rows):,} rows.")
    else:
        rows = fetch_wikidata()
        if args.save_json:
            save_path = Path(args.save_json)
            with save_path.open("w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            print(f"  Saved to {save_path}")

    print("Parsing line data ...")
    lines = parse_rows(rows)

    conn = sqlite3.connect(db_path)
    print("Building edges from P81 line membership ...")
    insert_line_edges(lines, conn)
    print_summary(conn)
    conn.close()
    print(f"\nDone. Database updated: {db_path}")


if __name__ == "__main__":
    main()