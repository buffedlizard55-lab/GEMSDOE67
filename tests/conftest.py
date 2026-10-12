"""Make the vendored template and the lane package importable from the repo root."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for rel in ("vendor/template66", "src"):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)
