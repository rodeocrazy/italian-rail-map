import gzip, pathlib

for name in ['stations', 'edges']:
    data = pathlib.Path(f'public/data/{name}.json').read_bytes()
    pathlib.Path(f'public/data/{name}.json.gz').write_bytes(gzip.compress(data, compresslevel=9))
    print(f'{name}.json compressed')