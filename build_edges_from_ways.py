"""
build_edges_from_ways.py

Builds station edges by analysing physical railway way topology from Overpass.

Instead of relying on route relations (which have incomplete stop members),
this script:
  1. Loads all railway ways and their node sequences
  2. Builds a graph of which OSM nodes connect to which via shared way membership
  3. For each station node, walks the graph until it reaches another station
  4. Creates an edge between those two stations

Max distance cap of 100km prevents runaway BFS walks creating false long-distance edges.

Usage:
    python build_edges_from_ways.py \
        --ways   Train_ways_data.json \
        --db     italy_rail.db

Run AFTER build_italy_rail_db.py has already populated the stations table.
This script only adds to the edges table — it does not replace existing edges.
"""

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# Maximum straight-line distance in km between two adjacent stations.
# Anything above this is almost certainly a runaway BFS walk, not a real connection.
MAX_EDGE_KM = 100.0


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
# Parse ways file
# ---------------------------------------------------------------------------

def parse_ways_file(path: Path):
    print(f"Loading {path.name} ...")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])

    nodes = {}
    ways  = []

    for e in elements:
        t = e.get("type")
        if t == "node" and "lat" in e:
            nodes[e["id"]] = {
                "id":   e["id"],
                "lat":  e["lat"],
                "lon":  e["lon"],
                "tags": e.get("tags", {}),
            }
        elif t == "way":
            ways.append({
                "id":    e["id"],
                "nodes": e.get("nodes", []),
                "tags":  e.get("tags", {}),
            })

    print(f"  {len(nodes):,} nodes, {len(ways):,} ways")
    return nodes, ways


# ---------------------------------------------------------------------------
# Build adjacency graph from way topology
# ---------------------------------------------------------------------------

def build_graph(ways, nodes):
    print("Building track graph from way topology ...")

    adjacency = defaultdict(set)
    edge_type  = {}

    for way in ways:
        node_refs = way["nodes"]
        rtype     = way["tags"].get("railway", "rail")

        for i in range(len(node_refs) - 1):
            a = node_refs[i]
            b = node_refs[i + 1]
            adjacency[a].add(b)
            adjacency[b].add(a)
            edge_type[frozenset((a, b))] = rtype

    total_edges = sum(len(v) for v in adjacency.values()) // 2
    print(f"  {len(adjacency):,} connected nodes, {total_edges:,} track segments")
    return adjacency, edge_type


# ---------------------------------------------------------------------------
# Walk graph to find station-to-station connections
# ---------------------------------------------------------------------------

def find_station_edges(station_node_ids: set, adjacency: dict, edge_type: dict, nodes: dict):
    """
    BFS from each station along the track graph.
    Stops a branch when it hits another station.
    Discards any edge longer than MAX_EDGE_KM (runaway walks).
    """
    print(f"Walking graph for {len(station_node_ids):,} stations ...")

    seen_pairs = set()
    edges      = []
    filtered   = 0

    for start_id in station_node_ids:
        if start_id not in adjacency:
            continue

        visited  = {start_id}
        queue    = list(adjacency[start_id])
        via_type = {n: edge_type.get(frozenset((start_id, n)), "rail") for n in queue}

        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)

            if current in station_node_ids:
                pair = frozenset((start_id, current))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    node_a = nodes.get(start_id)
                    node_b = nodes.get(current)
                    if node_a and node_b:
                        dist = haversine_km(
                            node_a["lat"], node_a["lon"],
                            node_b["lat"], node_b["lon"],
                        )
                        # Discard edges that are implausibly long
                        if dist > MAX_EDGE_KM:
                            filtered += 1
                        else:
                            rtype = via_type.get(current, "rail")
                            edges.append((start_id, current, dist, rtype))
                # Don't walk past another station
                continue

            for neighbour in adjacency[current]:
                if neighbour not in visited:
                    queue.append(neighbour)
                    if neighbour not in via_type:
                        via_type[neighbour] = via_type.get(
                            current,
                            edge_type.get(frozenset((current, neighbour)), "rail")
                        )

    print(f"  Found {len(edges):,} station-to-station connections")
    if filtered:
        print(f"  Filtered {filtered:,} edges exceeding {MAX_EDGE_KM}km distance cap")
    return edges


# ---------------------------------------------------------------------------
# Insert into DB
# ---------------------------------------------------------------------------

def insert_edges(edges, conn: sqlite3.Connection):
    # Create a synthetic line entry per railway type
    type_to_line_id = {}
    for rtype in set(r for _, _, _, r in edges):
        line_id = -abs(hash(f"physical_{rtype}")) % (10 ** 12)
        type_to_line_id[rtype] = line_id
        conn.execute("""
            INSERT OR IGNORE INTO lines
            (osm_relation_id, name, ref, operator, network, route_type,
             electrified, gauge, usage, active)
            VALUES (?, ?, NULL, NULL, NULL, ?, NULL, NULL, 'physical', 1)
        """, (line_id, f"Physical network ({rtype})", rtype))

    conn.commit()

    rows = [
        (type_to_line_id[rtype], a, b, 0, 1, round(dist, 4))
        for a, b, dist, rtype in edges
    ]

    conn.executemany("""
        INSERT INTO edges
        (line_id, station_a_id, station_b_id, sequence_a, sequence_b, distance_km)
        VALUES (?,?,?,?,?,?)
    """, rows)
    conn.commit()
    print(f"  Inserted {len(rows):,} edges into database.")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(conn: sqlite3.Connection):
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
    parser.add_argument("--ways", required=True, help="Overpass JSON with railway ways + nodes")
    parser.add_argument("--db",   default="italy_rail.db")
    args = parser.parse_args()

    ways_path = Path(args.ways)
    if not ways_path.exists():
        sys.exit(f"ERROR: file not found: {ways_path}")

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"ERROR: database not found: {db_path}. Run build_italy_rail_db.py first.")

    nodes, ways = parse_ways_file(ways_path)

    conn = sqlite3.connect(db_path)
    db_station_ids = set(
        r[0] for r in conn.execute("SELECT osm_id FROM stations WHERE osm_id > 0").fetchall()
    )
    print(f"Loaded {len(db_station_ids):,} station IDs from database.")

    station_node_ids = db_station_ids & set(nodes.keys())
    print(f"  {len(station_node_ids):,} stations found in ways file.")

    adjacency, edge_type = build_graph(ways, nodes)
    edges = find_station_edges(station_node_ids, adjacency, edge_type, nodes)
    insert_edges(edges, conn)
    print_summary(conn)

    conn.close()
    print(f"\nDone. Database updated: {db_path}")


if __name__ == "__main__":
    main()