#!/usr/bin/env python3
"""Lane-67 experiments: leakage canary, propensity+heads, geometry-aware decoding, gate.

Arms (all emitted as 4.5 px min-separation unit dots, scored with the shared DTI evaluator):

  A0 control   per-pixel propensity, isotropic maximum-filter NMS, single threshold
               (the "per-pixel classification ignores connectivity" baseline the lane criticises)
  A1 orient    + orientation-aware (across-strike) NMS and hysteresis
  A2 full      + along-strike extension past mapped tips (the lane mechanism)

Usage: python scripts/run_lane67_c7b2cfa6.py [--folds 3] [--quick]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import os  # noqa: E402

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from scipy import ndimage  # noqa: E402

from lane_c7b2cfa6 import decode67, emit67, features67, heads67, holdout67  # noqa: E402

CACHE = ROOT / "cache"
EVID = ROOT / "evidence" / "c7b2cfa6"
CHUNK_ROWS = 200  # ROWS of the 3730-row grid, not cells: 200 rows ~ 660k cells ~ 160 MB of float32


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}] " + " ".join(str(x) for x in a), flush=True)


def context_features(cube, fp, visible, names):
    """Catalogue-derived channels, computed ONLY from the supplied visible mask."""
    h, w = fp.shape
    out = []
    if visible.any():
        d = ndimage.distance_transform_edt(~visible).astype(np.float32)
        out.append(np.clip(d / 20.0, 0, 1))
        out.append((d <= 1).astype(np.float32))
        out.append((d <= 3).astype(np.float32))
        del d
        # nearest-visible index -> propagate the visible trace's own axial orientation
        _dd, (iy, ix) = ndimage.distance_transform_edt(~visible, return_indices=True); del _dd
        ot = heads67.trace_orientation_targets(visible)
        ocos = ot["cos2t"][iy, ix]
        osin = ot["sin2t"][iy, ix]
        gi = names.index
        # agreement between the local geophysical strike and the nearest visible trace strike
        for band, sig in (("det_elev", "15"), ("tmi", "15"), ("iso_grav_anom", "15")):
            c2 = cube[:, :, gi(f"cos2t_{band}_s{sig}")].astype(np.float32)
            s2 = cube[:, :, gi(f"sin2t_{band}_s{sig}")].astype(np.float32)
            out.append(np.clip(c2 * ocos + s2 * osin, -1, 1))
        # distance to the nearest visible trace END (tip prior from the catalogue geometry)
        nc = ndimage.convolve(visible.astype(np.uint8), np.ones((3, 3), np.uint8),
                              mode="constant") - visible.astype(np.uint8)
        ends = visible & (nc <= 3)
        dt = ndimage.distance_transform_edt(~ends).astype(np.float32) if ends.any() else np.full(visible.shape, 99.0, np.float32)
        out.append(np.clip(dt / 30.0, 0, 1)); del dt, nc, ends
    else:
        out = [np.zeros((h, w), np.float32) for _ in range(8)]
    return np.stack(out, axis=-1).astype(np.float16), [
        "d_visible_norm", "vis_le1px", "vis_le3px", "agree_det_elev", "agree_tmi",
        "agree_iso_grav", "d_tip_norm", "unused_pad"][:len(out)]


def build_xy(cube, ctx, fp, positives, n_neg, rng):
    """Assemble a training matrix from the memmap cube in footprint cells."""
    ys, xs = np.nonzero(fp)
    is_pos = positives[ys, xs]
    pos_idx = np.flatnonzero(is_pos)
    neg_idx = np.flatnonzero(~is_pos)
    if neg_idx.size > n_neg:
        neg_idx = rng.choice(neg_idx, size=n_neg, replace=False)
    sel = np.concatenate([pos_idx, neg_idx])
    sel.sort()
    y, x = ys[sel], xs[sel]
    n = len(sel)
    nb = cube.shape[-1] + ctx.shape[-1]
    X = np.empty((n, nb), np.float32)
    step = 400_000
    for i0 in range(0, n, step):
        i1 = min(n, i0 + step)
        yy, xx = y[i0:i1], x[i0:i1]
        X[i0:i1, :cube.shape[-1]] = np.asarray(cube[yy, xx, :], np.float32)
        X[i0:i1, cube.shape[-1]:] = np.asarray(ctx[yy, xx, :], np.float32)
        drop_cache(cube)
    lab = positives[y, x].astype(np.int8)
    return X, lab, (y, x)


def drop_cache(cube):
    """Release the memmap's clean page cache: this sandbox has a hard memory ceiling."""
    try:
        f = os.open(str(cube.filename), os.O_RDONLY)
        os.posix_fadvise(f, 0, 0, os.POSIX_FADV_DONTNEED)
        os.close(f)
    except Exception:
        pass


def predict_full(model, cube, ctx, fp, chunk=CHUNK_ROWS, region=None):
    h, w = fp.shape
    out = np.zeros((h, w), np.float32)
    nb = cube.shape[-1] + ctx.shape[-1]
    for r0 in range(0, h, chunk):
        r1 = min(h, r0 + chunk)
        rows = np.arange(r0, r1)
        m = fp[rows] if region is None else (fp[rows] & region[rows])
        if not m.any():
            continue
        yy, xx = np.nonzero(m)
        yy = yy + r0
        X = np.empty((len(yy), nb), np.float32)
        X[:, :cube.shape[-1]] = np.asarray(cube[yy, xx, :], np.float32)
        X[:, cube.shape[-1]:] = np.asarray(ctx[yy, xx, :], np.float32)
        out[yy, xx] = model.predict_proba(X)[:, 1].astype(np.float32)
        del X
        drop_cache(cube)
    return out


def ridge_full(model, cube, fp, chunk=CHUNK_ROWS, region=None):
    h, w = fp.shape
    out = np.zeros((h, w), np.float32)
    nb = cube.shape[-1]
    for r0 in range(0, h, chunk):
        r1 = min(h, r0 + chunk)
        rows = np.arange(r0, r1)
        m = fp[rows] if region is None else (fp[rows] & region[rows])
        if not m.any():
            continue
        yy, xx = np.nonzero(m)
        yy = yy + r0
        X = np.asarray(cube[yy, xx, :nb], np.float32)
        out[yy, xx] = model.predict(X).astype(np.float32)
        del X
        drop_cache(cube)
    return out


def isotropic_nms(p, size=3):
    return np.where(p >= ndimage.maximum_filter(p, size=size, mode="nearest"), p, 0.0).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--block-px", type=int, default=64)
    ap.add_argument("--frac", type=float, default=0.25)
    ap.add_argument("--buffer-px", type=int, default=3)
    ap.add_argument("--n-neg", type=int, default=200_000)
    ap.add_argument("--max-iter", type=int, default=150)
    ap.add_argument("--min-sep", type=float, default=4.5)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    EVID.mkdir(parents=True, exist_ok=True)

    cube, fp, names = features67.load(CACHE)
    with rasterio.open(ROOT / "data/official/labels.tif") as ds:
        labels = ds.read(1)
    faults = labels > 0
    log("cube", cube.shape, "footprint", int(fp.sum()), "catalogue", int(faults.sum()))

    folds = holdout67.make_folds(faults, fp, n_folds=args.folds, block_px=args.block_px,
                                 holdout_fraction=args.frac, buffer_px=args.buffer_px)
    for sp in folds:
        log(f"fold {sp['fold']}: blocks={len(sp['held_block_ids'])} withheld_pos="
            f"{sp['holdout_fault_cells']} visible={int(sp['visible'].sum())} "
            f"buffer_dropped={sp['buffer_dropped_cells']}")

    # ---------------- E0: leakage canary, one channel at a time ----------------
    canary = []
    sp = folds[0]
    y = sp["holdout"] & sp["held_block"]
    inside = sp["held_block"] & fp
    for j, nm in enumerate(names):
        s = np.zeros(cube.shape[:2], np.float32)
        for r0 in range(0, cube.shape[0], CHUNK_ROWS):
            r1 = min(cube.shape[0], r0 + CHUNK_ROWS)
            s[r0:r1] = np.asarray(cube[r0:r1, :, j], np.float32)
        auc = holdout67.roc_auc(y[inside], s[inside])
        canary.append({"channel": nm, "auc_fold0": round(float(auc), 4),
                       "flag": "LEAKAGE-SUSPECT" if auc > 0.90 else ""})
    canary.sort(key=lambda d: -d["auc_fold0"])
    log("canary top:", canary[:3])
    (EVID / "e1_canary.json").write_text(json.dumps(
        {"evidence_class": "HOLDOUT-DTI instrument (AUC), evaluator lane_c7b2cfa6.holdout67.roc_auc",
         "fold": 0, "withheld_positives": int(y.sum()), "scored_cells": int(inside.sum()),
         "threshold_rule": "AUC > 0.90 is leakage until proven otherwise",
         "channels": canary}, indent=2))

    # ---------------- per-fold model + arms ----------------
    from sklearn.ensemble import HistGradientBoostingClassifier

    results = {a: [] for a in ("A0_isotropic", "A1_orient_nms_hyst", "A2_full_tip_extension")}
    tipres = {a: [] for a in results}
    for sp in folds:
        visible = sp["visible"]
        ctx, ctx_names = context_features(cube, fp, visible, names)
        rng = np.random.default_rng(67 + sp["fold"])
        X, lab, _yx = build_xy(cube, ctx, fp, visible, args.n_neg, rng)
        log(f"fold {sp['fold']}: train matrix {X.shape} positives {int(lab.sum())}")
        clf = HistGradientBoostingClassifier(
            max_iter=args.max_iter if not args.quick else 40, learning_rate=0.12,
            max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0,
            class_weight="balanced", random_state=67, early_stopping=False)
        t0 = time.time()
        clf.fit(X, lab)
        log(f"fold {sp['fold']}: fit {time.time()-t0:.1f}s")
        del X, lab
        # the fold score only depends on emissions inside the withheld block (+4 px kernel margin),
        # so prediction is restricted to that region: 4x less memory and time, same measurement.
        region = ndimage.binary_dilation(sp["held_block"], iterations=4) & fp
        prop = predict_full(clf, cube, ctx, fp, region=region)

        # ---- orientation head (cos2t, sin2t) supervised within 3 px of visible traces ----
        ot = heads67.trace_orientation_targets(visible)
        tt = heads67.tip_targets(visible)
        vsel = ot["valid"] & region
        vy, vx = np.nonzero(vsel)
        if vy.size > 250_000:
            k = rng.choice(vy.size, 250_000, replace=False)
            vy, vx = vy[k], vx[k]
        Xo = np.asarray(cube[vy, vx, :], np.float32); drop_cache(cube)
        ori_cos = heads67.fit_head(Xo, ot["cos2t"][vy, vx].astype(np.float32), alpha=10.0)
        ori_sin = heads67.fit_head(Xo, ot["sin2t"][vy, vx].astype(np.float32), alpha=10.0)
        del Xo
        # ---- tip head ----
        tys, txs = np.nonzero(region)
        k = rng.choice(tys.size, min(400_000, tys.size), replace=False)
        tys, txs = tys[k], txs[k]
        Xt = np.asarray(cube[tys, txs, :], np.float32); drop_cache(cube)
        tipm = heads67.fit_head(Xt, tt["heat"][tys, txs].astype(np.float32), alpha=10.0)
        del Xt

        c2 = np.clip(ridge_full(ori_cos, cube, fp, region=region), -1, 1)
        s2 = np.clip(ridge_full(ori_sin, cube, fp, region=region), -1, 1)
        tip_pred = np.clip(ridge_full(tipm, cube, fp, region=region), 0, None)
        nrm = max(float(np.percentile(tip_pred[region], 99.9)), 1e-6)
        tip_pred = np.clip(tip_pred / nrm, 0, 1)
        t_hi = float(np.percentile(prop[region], 99.5))
        t_lo = float(np.percentile(prop[region], 99.0))
        # the tip head *is* the decoding tip source: a predicted tip is where a trace should stop
        # and from where the walk starts; catalogue tips are used as the walk seeds.
        walk_tips = tt["tips"] | ((tip_pred > 0.5) & (prop > t_lo))
        log(f"fold {sp['fold']}: catalogue tips {int(tt['tips'].sum())} walk seeds {int(walk_tips.sum())}")
        # ---- arms ----
        p0 = isotropic_nms(prop, size=3)
        net0 = p0 >= t_hi
        armscore0 = np.where(net0, p0, 0.0)

        d1 = decode67.decode(prop, c2, s2, np.zeros_like(walk_tips), t_hi=t_hi, t_lo=t_lo,
                             max_len=1, blocked=visible)
        armscore1 = d1["score"]

        t_ext = float(np.percentile(prop[region], 97.0))
        d2 = decode67.decode(prop, c2, s2, walk_tips, t_hi=t_hi, t_lo=t_lo, max_len=8,
                             t_ext=t_ext, blocked=visible, tip_weight=0.25)
        armscore2 = d2["score"]

        for arm, sc in (("A0_isotropic", armscore0), ("A1_orient_nms_hyst", armscore1),
                        ("A2_full_tip_extension", armscore2)):
            cand = region & ~visible & (sc > 0)
            dots = emit67.min_separation_select(sc, cand, min_sep_px=args.min_sep)
            pred = dots.astype(np.float32)
            r = holdout67.pooled_dti(pred, [sp])
            tr = holdout67.tip_adjacent_recovery(pred, [sp])
            r.update(tr)
            r["dots"] = int(dots.sum())
            r["on_visible"] = int((dots & visible).sum())
            results[arm].append(r)
            log(f"fold {sp['fold']} {arm}: dots={r['dots']} dti={r['dti_pooled']:.4f} "
                f"tip_dti={r['dti_tip_adjacent']:.4f}")
        del prop, c2, s2, tip_pred, d1, d2

    # ---------------- pooled summary over folds ----------------
    summary = {}
    for arm, rs in results.items():
        dtis = np.array([r["dti_pooled"] for r in rs], float)
        tdtis = np.array([r["dti_tip_adjacent"] for r in rs], float)
        n = len(dtis)
        se = float(dtis.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
        tp = sum(r["tp_w"] for r in rs); fpp = sum(r["fp_w"] for r in rs); fnn = sum(r["fn_w"] for r in rs)
        from gems.metric import dti_from_terms
        summary[arm] = {
            "dti_pooled_all_folds": float(dti_from_terms(tp, fpp, fnn)),
            "fold_mean_dti": float(dtis.mean()), "ci95": [float(dtis.mean() - 1.96 * se), float(dtis.mean() + 1.96 * se)],
            "fold_dtis": [float(x) for x in dtis],
            "tip_adjacent_fold_mean": float(tdtis.mean()), "tip_adjacent_fold_dtis": [float(x) for x in tdtis],
            "withheld_positives_total": int(sum(r["withheld_positives_total"] for r in rs)),
            "mean_dots_per_fold": float(np.mean([r["dots"] for r in rs])),
            "on_visible_dots_total": int(sum(r["on_visible"] for r in rs)),
            "per_fold": rs,
        }
    # paired differences
    pairs = {}
    for a, b in (("A2_full_tip_extension", "A0_isotropic"), ("A2_full_tip_extension", "A1_orient_nms_hyst"),
                 ("A1_orient_nms_hyst", "A0_isotropic")):
        d = np.array(summary[a]["fold_dtis"]) - np.array(summary[b]["fold_dtis"])
        dt = np.array(summary[a]["tip_adjacent_fold_dtis"]) - np.array(summary[b]["tip_adjacent_fold_dtis"])
        pairs[f"{a}_minus_{b}"] = {
            "dti_delta_mean": float(d.mean()), "dti_delta_folds": [float(x) for x in d],
            "dti_folds_positive": int((d > 0).sum()), "n_folds": int(len(d)),
            "tip_dti_delta_mean": float(dt.mean()), "tip_dti_folds_positive": int((dt > 0).sum()),
        }
    out = {"evidence_class": "HOLDOUT-DTI (hide-and-recover, evaluator gems.metric via holdout67.pooled_dti)",
           "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "protocol": {"n_folds": args.folds, "block_px": args.block_px, "holdout_fraction": args.frac,
                        "buffer_px": args.buffer_px, "segment_ids": "8-connected components (proxy, disclosed)",
                        "visible_masked_pixel_exact": True, "min_sep_px": args.min_sep,
                        "model": "HistGradientBoostingClassifier", "max_iter": args.max_iter},
           "arms": summary, "paired": pairs,
           "caveat": "The hidden exam is expert-labelled NEW faults and is not available; these are "
                     "proxy measurements against withheld catalogue segments."}
    (EVID / "e2_holdout_arms.json").write_text(json.dumps(out, indent=2))
    log(json.dumps({k: {"dti": v["dti_pooled_all_folds"], "tip": v["tip_adjacent_fold_mean"],
                        "dots": v["mean_dots_per_fold"]} for k, v in summary.items()}, indent=1))
    log(json.dumps(pairs, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
