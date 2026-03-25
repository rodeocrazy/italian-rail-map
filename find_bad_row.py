import json

with open('Train_station_data.json', encoding='utf-8') as f:
    data = json.load(f)

elements = data.get('elements', [])
bad = 0
for e in elements:
    if e.get('type') != 'node':
        continue
    if not e.get('lat') or not e.get('lon'):
        bad += 1
        print(f"Bad node: id={e.get('id')} lat={e.get('lat')} lon={e.get('lon')}")

print(f"Total bad nodes: {bad}")