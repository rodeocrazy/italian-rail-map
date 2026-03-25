import json

data = json.load(open('public/data/edges.json', encoding='utf-8'))
forli_edges = [e for e in data if e['station_a_id'] == 252793817 or e['station_b_id'] == 252793817]
print('Forli edges in export:', len(forli_edges))
for e in forli_edges:
    print(' ', e['line_name'], e['route_type'])