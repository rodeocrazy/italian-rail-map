import subprocess
import re
from pathlib import Path

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

# Stage everything
run('git add .')
message = input('Commit message: ')
run(f'git commit -m "{message}"')
run('git push')

# Get the hash of the commit we just pushed
hash = subprocess.check_output('git rev-parse HEAD', shell=True).decode().strip()

# Update App.jsx with the new hash
app = Path('src/App.jsx')
content = app.read_text(encoding='utf-8')
updated = re.sub(r"const COMMIT_HASH = '[^']*'", f"const COMMIT_HASH = '{hash}'", content)
app.write_text(updated, encoding='utf-8')
print(f"Updated COMMIT_HASH to {hash}")

# Amend the previous commit to include the hash update
run('git add src/App.jsx')
run('git commit --amend --no-edit')
run('git push --force')

print('Done — Vercel will deploy once.')