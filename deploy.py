import subprocess
import re
from pathlib import Path

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

# Push current changes
run('git add .')
message = input('Commit message: ')
run(f'git commit -m "{message}"')
run('git push')

# Get the new hash and update App.jsx
hash = subprocess.check_output('git rev-parse HEAD', shell=True).decode().strip()
app = Path('src/App.jsx')
content = app.read_text(encoding='utf-8')
updated = re.sub(r"const COMMIT_HASH = '[^']*'", f"const COMMIT_HASH = '{hash}'", content)
app.write_text(updated, encoding='utf-8')
print(f"Updated COMMIT_HASH to {hash}")

# Commit the hash update
run('git add src/App.jsx')
run('git commit -m "update commit hash"')
run('git push')

print('Done — Vercel will deploy shortly.')