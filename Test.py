import sqlite3
conn = sqlite3.connect('italy_rail.db')

for stype in ['monorail', 'miniature']:
    rows = conn.execute(
        "SELECT osm_id, name, lat, lon FROM stations WHERE station = ?", (stype,)
    ).fetchall()
    print(f"\n{stype}:")
    for r in rows:
        print(f"  {r[1]} ({r[0]}) - {r[2]}, {r[3]}")