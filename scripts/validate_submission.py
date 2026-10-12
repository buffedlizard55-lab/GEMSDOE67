#!/usr/bin/env python3
"""``validate_submission.py`` — the format gate the competition will apply, run locally.

Usage:
    python3 scripts/validate_submission.py [path/to/submission.tif]

With no argument it validates the newest raster in ``submissions/``.  Exit code 0 means
every check passed; anything else means do not upload.  The checks are the vendored
``gems57.validate`` checks (single band, float32, 3730x3292, EPSG:32611, the sample
submission's transform, finite everywhere, no sentinel values, values inside [0, 1],
nothing positive outside the footprint, no dots on the mapped catalogue).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for rel in ("vendor/template66", "src"):
    if str(ROOT / rel) not in sys.path:
        sys.path.insert(0, str(ROOT / rel))

import numpy as np                                            # noqa: E402
from gems57 import grid as G                                  # noqa: E402
from gems57 import validate as V                              # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        path = Path(argv[1])
    else:
        subs = sorted((ROOT / "submissions").glob("*.tif"))
        if not subs:
            print("no submission found; pass a path explicitly")
            return 2
        path = subs[-1]
    g = G.load_grid()
    out = V.validate(path, g.footprint, g.catalogue)
    print(f"file      : {out['file']}")
    print(f"sha256    : {out['sha256']}")
    print(f"bytes     : {out['bytes']}")
    print(f"crs/shape : {out['meta']['crs']} {tuple(out['meta']['shape'])} {out['meta']['dtype']}")
    print(f"range     : min {out['min']} max {out['max']} "
          f"(positive pixels {out['emitted_positive_pixels']})")
    for name, ok in out["checks"].items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"all checks passed: {out['all_checks_passed']}")
    if not out["all_checks_passed"]:
        return 1
    V.assert_submittable(out)
    print("submittable: yes (format only — see the lane gate in evidence/run_card.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
