import sqlite3
conn = sqlite3.connect('italy_rail.db')
rows = conn.execute("SELECT station, COUNT(*) FROM stations GROUP BY station ORDER BY COUNT(*) DESC").fetchall()
print("Station subtypes:")
for r in rows:
    print(f"  {r[0]}: {r[1]}")