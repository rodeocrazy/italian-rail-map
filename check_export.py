import json

with open('public/data/stations.json', encoding='utf-8') as f:
    data = json.load(f)

from collections import Counter
subtypes = Counter(s.get('station') for s in data)
print("Station subtypes in export:")
for k, v in subtypes.most_common():
    print(f"  {k}: {v}")