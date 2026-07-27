"""Test configuration: make the repo root and `scripts/` importable."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

for path in (REPO_ROOT, SCRIPTS_DIR):
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)
