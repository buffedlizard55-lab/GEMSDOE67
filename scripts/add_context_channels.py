#!/usr/bin/env python3
"""Add multi-scale context channels derived from the cached evidence channels.

Context is what a per-pixel threshold cannot see: a lineament that is only locally weak but
sits inside a region where lineaments are abundant is far more likely to be a real structure.
Four channels are added (all derived from the evidence stack, no catalogue input):

  ev_s3, ev_s8        Gaussian smoothed aggregate evidence (sigma 3 and 8 px)
  ev_mag_s3           smoothed magnetic-family evidence
  ev_topo_s3          smoothed topographic-family evidence
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gems67.dataio import FEATURE_DIR  # noqa: E402

PLAN = {
    "ev_s3": ("ev", 3.0),
    "ev_s8": ("ev", 8.0),
    "ev_mag_s3": ("ev_mag", 3.0),
    "ev_topo_s3": ("ev_topo", 3.0),
}


def main() -> int:
    for out, (src, sigma) in PLAN.items():
        dst = FEATURE_DIR / f"{out}.npy"
        if dst.exists():
            print(f"[context] {out} cached")
            continue
        a = np.asarray(np.load(FEATURE_DIR / f"{src}.npy", mmap_mode="r"), dtype=np.float32)
        s = gaussian_filter(a, sigma, mode="nearest").astype(np.float32)
        np.save(dst, s)
        print(f"[context] {out} = gaussian({src}, sigma={sigma}) written")
        del a, s
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
