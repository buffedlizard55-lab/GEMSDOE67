#!/usr/bin/env python3
"""Build the lane-67 label-free channel cube into cache/ (gitignored).

Usage: python scripts/build_features_c7b2cfa6.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402

from lane_c7b2cfa6.features67 import build  # noqa: E402

FEATURES = ROOT / "data/cache/numeric_features.tif"
RAD = ROOT / "data/external/geodawn_rad_u8.tif"
TOPO = ROOT / "data/external/topo_10m_derived_100m_u8.tif"
SAMPLE = ROOT / "data/official/sample_submission.tif"
CACHE = ROOT / "cache"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    t0 = time.time()
    for p in (FEATURES, RAD, TOPO, SAMPLE):
        if not p.exists():
            print(f"MISSING {p}", file=sys.stderr)
            return 2
    # the official footprint is the organiser's own template: finite cells of sample_submission.tif
    with rasterio.open(SAMPLE) as ds:
        ss = ds.read(1)
        fp = np.isfinite(ss)
        grid = {"crs": ds.crs.to_string(), "transform": list(ds.transform)[:6],
                "height": ds.height, "width": ds.width}
        del ss
    print(f"footprint from sample_submission.tif: {int(fp.sum())} cells; grid={grid}", flush=True)
    meta = build(FEATURES, RAD, TOPO, CACHE, footprint=fp)
    meta["generated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta["seconds"] = round(time.time() - t0, 1)
    meta["official_grid"] = grid
    meta["input_sha256"] = {p.name: sha256(p) for p in (FEATURES, RAD, TOPO, SAMPLE)}
    (CACHE / "channels_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: meta[k] for k in ("n_channels", "footprint_cells", "seconds")}, indent=1))
    print(f"OK in {meta['seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
