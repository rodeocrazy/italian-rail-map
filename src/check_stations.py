import json
with open('public/data/stations.json', encoding='utf-8') as f:
    data = json.load(f)
print(list(data[0].keys()))