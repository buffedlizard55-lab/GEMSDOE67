#!/usr/bin/env python3
"""Smoke test: run the *identical* code path on a small window so bugs surface in seconds.

Usage: python scripts/smoke_test.py --window 0 600 0 600
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from gems67 import features  # noqa: E402
from gems67.dataio import FEATURE_DIR, read_labels  # noqa: E402
from gems67.grid import ALPHA  # noqa: E402
from gems67.holdout import build_folds  # noqa: E402
from gems67.metric import dti_exact  # noqa: E402
import run_holdout as rh  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, nargs=4, default=[0, 700, 0, 700])
    ap.add_argument("--out", default="/tmp/gems67_smoke_features")
    args = ap.parse_args()
    r0, r1, c0, c1 = args.window
    t0 = time.time()
    features.build(out_dir=Path(args.out), force=True, window=(r0, r1, c0, c1))
    print(f"[smoke] features built in {time.time() - t0:.1f}s -> {args.out}")

    labels = read_labels()[r0:r1, c0:c1]
    folds = build_folds(labels=labels, buffer_px=2)
    for f in folds:
        print(f"[smoke] fold {f.name}: truth={int(f.truth.sum()):6d} known={int(f.known.sum()):6d} "
              f"active={int(f.active.sum()):7d}")

    ev = np.load(Path(args.out) / "ev.npy")
    cos2t = np.load(Path(args.out) / "cos2t.npy")
    sin2t = np.load(Path(args.out) / "sin2t.npy")
    print(f"[smoke] ev stats finite={np.isfinite(ev).sum()} p50={np.median(ev):.4g} "
          f"p99={np.quantile(ev, 0.99):.4g}")

    from gems67 import decode, emit

    for f in folds:
        if f.truth.sum() == 0:
            continue
        print(f"[smoke] fold {f.name} expected_credit after calibration")
        from scipy.ndimage import distance_transform_edt
        d = distance_transform_edt(~f.visible)
        train = (f.visible | (d >= 5)) & ~f.block & (d < 1e9)
        cal = emit.calibrate_q(ev, d <= 3, train)
        q = emit.apply_calibration(ev, cal)
        dec = decode.decode(ev, cos2t, sin2t, 0.90, 0.70)
        ec = emit.expected_credit(np.where(np.isfinite(q), q, 0).astype(np.float32))
        cand = dec["relayed"] & f.active
        dots = emit.greedy_dots(ec, bar=ALPHA * 0.28, r_excl=2.0, candidate_mask=cand)
        if dots.any():
            sc = dti_exact(dots.astype(np.float32), f.truth, valid=f.active)
            print(f"[smoke] lane dots={int(dots.sum())} dti={sc['dti']:.4f} k={sc['n_truth']}")
        inc = emit.catalogue_dilation_dots(f.visible, 2, 3) & f.active
        if inc.any():
            sc = dti_exact(inc.astype(np.float32), f.truth, valid=f.active)
            print(f"[smoke] incumbent dots={int(inc.sum())} dti={sc['dti']:.4f}")
        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
