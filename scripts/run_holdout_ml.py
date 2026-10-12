#!/usr/bin/env python3
"""Experiment E3: supervised multi-channel head, scored in the same hide-and-recover folds.

The head is a gradient-boosted tree classifier trained *only* on the visible catalogue inside
the three folds that are not being scored, on 16 channels (12 evidence/geometry channels plus
4 multi-scale context channels).  Its calibrated output ``q_ml`` is then (a) scored as a
ranking by AUC on the withheld block and (b) converted to a submission by the same greedy
kernel-cover rule as the analytic lane, over a sweep of the exposure threshold tau.

Nothing here is trained on the block it is scored on, and the visible catalogue is masked
pixel-exactly when scoring, so the numbers are directly comparable with run_holdout.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems67 import decode, emit  # noqa: E402
from gems67.dataio import FEATURE_DIR, footprint_from, read_labels, write_json  # noqa: E402
from gems67.holdout import iter_folds  # noqa: E402
from gems67.metric import dti_exact  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

CHANNELS = ("ev", "ev_mag", "ev_grav", "ev_topo", "ev_subsurf", "ev_strain", "ev_seis",
            "coh", "order_R", "tpi5", "curv", "rough", "ev_s3", "ev_s8", "ev_mag_s3",
            "ev_topo_s3",
            # public USGS-derived layers outside the 19-band stack (see
            # scripts/add_external_channels.py and data/registry.json)
            "ev_lidar", "ev_lidar_s3", "ev_rad", "ev_rad_s3", "ev_ext_all", "ev_ext_all_s3",
            "lidar_valid")


def gather(channels: tuple[str, ...], rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Design matrix for the given pixel indices, one channel at a time (low memory)."""
    out = np.empty((rows.size, len(channels)), np.float32)
    for j, name in enumerate(channels):
        a = np.load(FEATURE_DIR / f"{name}.npy", mmap_mode="r")
        out[:, j] = a[rows, cols]
        del a
    return out


def band_block(shape, rows: np.ndarray, cols: np.ndarray, cfgs: list[tuple[str, float]]):
    """Design matrix on every pixel of a sub-window, built in row bands (low memory)."""
    h, w = shape
    r0, r1 = int(rows.min()), int(rows.max()) + 1
    c0, c1 = int(cols.min()), int(cols.max()) + 1
    n = rows.size
    out = np.empty((n, len(cfgs)), np.float32)
    step = max(1, int(2e6 // max(1, (c1 - c0))))
    pos = 0
    for rb in range(r0, r1, step):
        re_ = min(r1, rb + step)
        sel = (rows >= rb) & (rows < re_)
        k = int(sel.sum())
        if k == 0:
            continue
        rr = rows[sel] - rb
        cc = cols[sel]
        for j, (name, _) in enumerate(cfgs):
            a = np.load(FEATURE_DIR / f"{name}.npy", mmap_mode="r")
            out[pos:pos + k, j] = a[rb:re_, :][rr, cc]
            del a
        pos += k
    return out[:pos]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evidence/holdout_ml.json")
    ap.add_argument("--tau", type=float, nargs="+", default=[0.05, 0.1, 0.2, 0.3, 0.5])
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--neg-per-pos", type=float, default=2.0)
    ap.add_argument("--max-pos", type=int, default=60000)
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    labels = read_labels()
    footprint = footprint_from(labels)
    catalogue = labels == 1
    rng = np.random.default_rng(args.seed)

    pooled: dict[str, list[dict]] = {}
    auc_rows: dict[str, list[float]] = {}
    t0 = time.time()

    for fold in iter_folds(buffer_px=2):
        pos_mask = fold.visible & ~fold.block
        d = None
        from scipy.ndimage import distance_transform_edt
        d = distance_transform_edt(~fold.visible)
        neg_mask = footprint & ~fold.block & (d >= 5.0)
        pr, pc = np.nonzero(pos_mask)
        if pr.size > args.max_pos:
            sel = rng.choice(pr.size, args.max_pos, replace=False)
            pr, pc = pr[sel], pc[sel]
        nr, nc = np.nonzero(neg_mask)
        n_take = min(nr.size, int(pr.size * args.neg_per_pos))
        sel = rng.choice(nr.size, n_take, replace=False)
        nr, nc = nr[sel], nc[sel]
        tr_rows = np.concatenate([pr, nr])
        tr_cols = np.concatenate([pc, nc])
        y = np.concatenate([np.ones(pr.size, np.int8), np.zeros(nr.size, np.int8)])
        X = gather(CHANNELS, tr_rows, tr_cols)
        print(f"[ml] fold {fold.name}: train {X.shape} pos={pr.size} neg={nr.size}", flush=True)
        clf = HistGradientBoostingClassifier(max_iter=args.iters, learning_rate=0.08,
                                             max_leaf_nodes=31, l2_regularization=1.0,
                                             random_state=args.seed)
        clf.fit(X, y)
        del X, tr_rows, tr_cols, y

        # predict on the fold's active domain
        ar, ac = np.nonzero(fold.active)
        if ar.size == 0:
            continue
        q_ml = np.zeros(labels.shape, np.float32)
        step = int(1.5e6)
        for i in range(0, ar.size, step):
            rr = ar[i:i + step]
            cc = ac[i:i + step]
            Xi = gather(CHANNELS, rr, cc)
            q_ml[rr, cc] = clf.predict_proba(Xi)[:, 1]
            del Xi
        del ar, ac

        auc = roc_auc_score(fold.truth[fold.active], q_ml[fold.active])
        auc_rows.setdefault("q_ml", []).append(float(auc))
        auc_rows.setdefault("ev", []).append(float(roc_auc_score(
            fold.truth[fold.active], np.asarray(np.load(FEATURE_DIR / "ev.npy", mmap_mode="r"))[fold.active])))
        print(f"[ml] fold {fold.name}: AUC(q_ml)={auc:.4f}", flush=True)

        # geometry gate from the analytic lane (orientation NMS + hysteresis + tip relay)
        ev = np.asarray(np.load(FEATURE_DIR / "ev.npy", mmap_mode="r"))
        cos2t = np.asarray(np.load(FEATURE_DIR / "cos2t.npy", mmap_mode="r"))
        sin2t = np.asarray(np.load(FEATURE_DIR / "sin2t.npy", mmap_mode="r"))
        dec = decode.decode(ev, cos2t, sin2t, high_q=0.90, low_q=0.70, search=fold.active)
        cand = dec["candidates"] & fold.active
        del ev, cos2t, sin2t

        arms = {}
        for tau in args.tau:
            arms[f"ML_cover_geom_tau{tau:g}"] = emit.cover_greedy(
                q_ml, tau=tau, candidate_mask=cand, radius=args.radius)
            arms[f"ML_cover_allpix_tau{tau:g}"] = emit.cover_greedy(
                q_ml, tau=tau, candidate_mask=fold.active, radius=args.radius)
        for arm, m in arms.items():
            sc = dti_exact(np.asarray(m, np.float32), fold.truth, valid=fold.active)
            sc["n_px"] = int(m.sum())
            pooled.setdefault(arm, []).append(sc)
            print(f"[ml] {fold.name} {arm:26s} dti={sc['dti']:.4f} px={sc['n_px']:7d} "
                  f"cov={sc['tp'] / max(sc['n_truth'], 1):.4f}", flush=True)
        del q_ml, dec, cand, arms, d

    out = {}
    for arm, rows in pooled.items():
        tp = sum(r["tp"] for r in rows)
        fp = sum(r["fp"] for r in rows)
        fn = sum(r["fn"] for r in rows)
        k = sum(r["n_truth"] for r in rows)
        out[arm] = dict(dti=float(tp / (tp + 0.2 * fp + 0.8 * fn + 1e-12)), tp=tp, fp=fp, fn=fn,
                        n_truth=k, coverage=float(tp / k) if k else 0.0,
                        mean_px=float(np.mean([r["n_px"] for r in rows])),
                        per_fold=[round(r["dti"], 5) for r in rows])
    write_json(ROOT / args.out, dict(
        channels=list(CHANNELS), tau=args.tau, radius=args.radius,
        auc=auc_rows, pooled=out, seconds=round(time.time() - t0, 1),
        note="supervised head trained outside the scored block; visible catalogue masked when scoring"))
    print(json.dumps(out, indent=2))
    print(f"[ml] wrote {args.out} in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
