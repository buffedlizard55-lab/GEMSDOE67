#!/usr/bin/env python3
"""Build the cached geometry-aware feature stack (19 provided bands → evidence + orientation).

Usage:  python scripts/build_features.py [--force]
Outputs the channels listed in src/gems67/features.CHANNELS under $GEMS67_DATA/features/.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gems67 import features  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild even if cached")
    args = ap.parse_args()
    t0 = time.time()
    out = features.build(force=args.force)
    print(f"[features] {len(features.CHANNELS)} channels in {out} ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
