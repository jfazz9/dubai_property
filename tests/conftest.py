import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"

for path in [ROOT_DIR, SCRIPTS_DIR]:
    path_text = str(path)

    if path_text not in sys.path:
        sys.path.insert(0, path_text)
