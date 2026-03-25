import subprocess
import re
from pathlib import Path

# Get latest commit hash
hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()

# Update App.jsx
app = Path('src/App.jsx')
content = app.read_text(encoding='utf-8')
updated = re.sub(r"const COMMIT_HASH = '[^']*'", f"const COMMIT_HASH = '{hash}'", content)
app.write_text(updated, encoding='utf-8')

print(f"Updated COMMIT_HASH to {hash}")