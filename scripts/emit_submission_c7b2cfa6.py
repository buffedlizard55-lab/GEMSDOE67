#!/usr/bin/env python3
"""Emit the lane-67 candidate submission: orientation+tip decoded network -> calibrated dots -> GeoTIFF.

Steps (each one writes evidence JSON):
  1. train the propensity model and the two heads on the FULL visible catalogue (nothing is held
     out here; the holdout experiment in ``scripts/run_lane67_c7b2cfa6.py`` is the gate, this is inference);
  2. geometry-aware decode (orientation-aware NMS + hysteresis + along-strike tip extension);
  3. node selection: 4.5 px minimum separation, then calibrated greedy marginal-DTI acceptance
     (accept while expected new kernel credit > alpha * DTI_target), reported at two prevalence
     assumptions;
  4. write float32 EPSG:32611 100 m GeoTIFF, NaN only outside the official footprint, plus an
     all-finite sibling that writes 0 outside (the portal rejects out-of-range values, never NaN
     placement, so both are shipped and the NaN one is the primary);
  5. validate against sample_submission.tif + the feature grid, then uniqueness vs the registry.

Usage: python scripts/emit_submission_c7b2cfa6.py [--prevalence 12691] [--dti-target 0.28] [--max-dots 200000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from scipy import ndimage  # noqa: E402

from gems import submission_writer  # noqa: E402
from lane_c7b2cfa6 import decode67, emit67, features67, heads67, uniqueness67  # noqa: E402
from run_lane67 import context_features, drop_cache, isotropic_nms, predict_full, ridge_full  # noqa: E402

EVID = ROOT / "evidence" / "c7b2cfa6"
OUT = ROOT / "docs/downloads"
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}] " + " ".join(str(x) for x in a), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prevalence", type=float, default=12691.0,
                    help="assumed hidden-truth cell count used ONLY to calibrate qhat")
    ap.add_argument("--prevalence-alt", type=float, default=60988.0)
    ap.add_argument("--dti-target", type=float, default=0.28)
    ap.add_argument("--min-sep", type=float, default=4.5)
    ap.add_argument("--exclude-catalogue-px", type=float, default=0.0,
                    help="drop candidates whose distance to a VISIBLE catalogue pixel is <= this. "
                         "The live exam scores faults ABSENT from the visible catalogue, so a dot "
                         "touching a mapped trace is almost pure false-positive mass; the "
                         "hide-and-recover holdout disagrees by construction (its truth IS a "
                         "catalogue trace). Registry meta-analysis: live score falls as "
                         "frac_within_3px rises (Spearman -0.72, n=20 owner-reported).")
    ap.add_argument("--max-dots", type=int, default=200_000)
    ap.add_argument("--n-neg", type=int, default=250_000)
    ap.add_argument("--max-iter", type=int, default=150)
    ap.add_argument("--max-len", type=int, default=0,
                    help="along-strike tip extension, cells. DEFAULT 0 = DISABLED: the arm that "
                         "extends past tips measured NEGATIVE against the preregistered gate "
                         "(evidence/c7b2cfa6/e2_holdout_arms.json, both folds), so the shipped decode is the "
                         "orientation-aware NMS + hysteresis arm that passed it. This is a disclosed "
                         "deviation from the lane text, not a silent one.")
    ap.add_argument("--tip-extension", choices=("gate_decided", "force_on"), default="gate_decided")
    args = ap.parse_args()
    EVID.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    cube, fp_feat, names = features67.load(ROOT / "cache")
    with rasterio.open(ROOT / "data/official/sample_submission.tif") as ds:
        fp = np.isfinite(ds.read(1))
    with rasterio.open(ROOT / "data/official/labels.tif") as ds:
        cat = ds.read(1) > 0
    log("footprint(official)", int(fp.sum()), "footprint(features)", int(fp_feat.sum()),
        "catalogue", int(cat.sum()))
    if not np.array_equal(fp, fp_feat):
        log(f"NOTE footprint differs by {int((fp & ~fp_feat).sum())} cells (official template is authoritative)")

    from sklearn.ensemble import HistGradientBoostingClassifier
    rng = np.random.default_rng(67)

    # ---- out-of-fold propensity -------------------------------------------------------------
    # Training one model with the FULL catalogue as its own context makes the model copy the
    # catalogue: measured in this checkout, the single-model propensity field was > 0 on exactly
    # 60,988 cells = the catalogue, leaving 0 off-catalogue candidates (evidence/c7b2cfa6/_run_emit.log).
    # The gate already avoids this (each fold derives context only from the visible faults), so the
    # final inference must too: the catalogue is split into K groups of whole 8-connected segments,
    # one model is trained per group with that group removed (plus a 3 px buffer, as the shared
    # holdout does), and every cell takes the prediction of the model whose visible set does NOT
    # contain the catalogue nearest to it.
    K = 4
    seg, nseg = ndimage.label(cat, structure=np.ones((3, 3), int))
    log("catalogue segments", nseg)
    props, best_d, best_k = [], None, np.zeros(cat.shape, np.int8)
    for k in range(K):
        held = cat & (seg % K == k)
        vis = cat & ~held
        if held.any():
            vis = vis & (ndimage.distance_transform_edt(~held) > 3)
        ctx_k, _ = context_features(cube, fp, vis, names)
        ys, xs = np.nonzero(fp)
        ispos = vis[ys, xs]
        pi = np.flatnonzero(ispos); ni = np.flatnonzero(~ispos)
        ni = rng.choice(ni, size=min(args.n_neg // 2, ni.size), replace=False)
        sel = np.sort(np.concatenate([pi, ni]))
        yy, xx = ys[sel], xs[sel]
        X = np.empty((len(sel), cube.shape[-1] + ctx_k.shape[-1]), np.float32)
        X[:, :cube.shape[-1]] = np.asarray(cube[yy, xx, :], np.float32)
        X[:, cube.shape[-1]:] = np.asarray(ctx_k[yy, xx, :], np.float32)
        lab = vis[yy, xx].astype(np.int8)
        clf = HistGradientBoostingClassifier(max_iter=args.max_iter, learning_rate=0.12,
                                             max_leaf_nodes=31, min_samples_leaf=40,
                                             l2_regularization=1.0, class_weight="balanced",
                                             random_state=67 + k, early_stopping=False)
        clf.fit(X, lab)
        log(f"oof fold {k}: visible={int(vis.sum())} held={int(held.sum())} train={X.shape}")
        del X, lab, yy, xx, ys, xs, pi, ni, sel, ispos
        pk = predict_full(clf, cube, ctx_k, fp)
        props.append(pk)
        dk = ndimage.distance_transform_edt(~vis).astype(np.float32)
        if best_d is None:
            best_d = dk
        else:
            better = dk > best_d
            best_k = np.where(better, np.int8(k), best_k)
            best_d = np.where(better, dk, best_d)
            del better
        del dk, ctx_k, clf
        import gc; gc.collect()
    prop = np.zeros(cat.shape, np.float32)
    for k in range(K):
        m = best_k == k
        prop[m] = props[k][m]
    del props, best_d, best_k
    import gc; gc.collect()
    log("out-of-fold propensity assembled; p99.9 =", float(np.percentile(prop[fp], 99.9)),
        "off-catalogue p99.9 =", float(np.percentile(prop[fp & ~cat], 99.9)))

    ot = heads67.trace_orientation_targets(cat)
    tt = heads67.tip_targets(cat)
    vy, vx = np.nonzero(ot["valid"] & fp)
    k = rng.choice(vy.size, min(300_000, vy.size), replace=False)
    Xo = np.asarray(cube[vy[k], vx[k], :], np.float32)
    oc = heads67.fit_head(Xo, ot["cos2t"][vy[k], vx[k]].astype(np.float32), alpha=10.0)
    osn = heads67.fit_head(Xo, ot["sin2t"][vy[k], vx[k]].astype(np.float32), alpha=10.0)
    del Xo
    tys, txs = np.nonzero(fp)
    k = rng.choice(tys.size, min(500_000, tys.size), replace=False)
    Xt = np.asarray(cube[tys[k], txs[k], :], np.float32)
    tipm = heads67.fit_head(Xt, tt["heat"][tys[k], txs[k]].astype(np.float32), alpha=10.0)
    del Xt
    c2 = np.clip(ridge_full(oc, cube, fp), -1, 1); del oc
    s2 = np.clip(ridge_full(osn, cube, fp), -1, 1); del osn
    tip_pred = np.clip(ridge_full(tipm, cube, fp), 0, None); del tipm
    import gc; gc.collect()
    nrm = max(float(np.percentile(tip_pred[fp], 99.9)), 1e-9)
    tip_pred /= nrm
    # head diagnostics (reported, not used as a score)
    band = ot["valid"]
    cos_err = float(np.mean(np.abs(c2[band] - ot["cos2t"][band])))
    sin_err = float(np.mean(np.abs(s2[band] - ot["sin2t"][band])))
    tip_auc = None
    from lane_c7b2cfa6.holdout67 import roc_auc
    tip_auc = roc_auc((tt["tips"] | tt["junctions"])[fp], tip_pred[fp])
    log(f"orientation head MAE(cos2t)={cos_err:.4f} MAE(sin2t)={sin_err:.4f} tip head AUC={tip_auc:.4f}")
    del ot, band
    import gc; gc.collect()

    t_hi = float(np.percentile(prop[fp], 99.5))
    t_lo = float(np.percentile(prop[fp], 99.0))
    walk_tips = tt["tips"] | ((tip_pred > 0.5) & (prop > t_hi))
    t_ext = float(np.percentile(prop[fp], 97.0))
    max_len = args.max_len if args.tip_extension == "force_on" else max(args.max_len, 0)
    dec = decode67.decode(prop, c2, s2, walk_tips, t_hi=t_hi, t_lo=t_lo, max_len=max_len,
                          t_ext=t_ext, blocked=cat, tip_weight=0.25)
    score = dec["score"]
    log("network cells", int(dec["network"].sum()), "extension cells", int(dec["extension"].sum()),
        "score>0", int((score > 0).sum()))
    n_net, n_ext = int(dec["network"].sum()), int(dec["extension"].sum())
    del prop, tt, dec
    import gc; gc.collect()

    # ---------------- node selection ----------------
    dcat = ndimage.distance_transform_edt(~cat)
    cand = (fp & (dcat > args.exclude_catalogue_px) & (score > 0)
            if args.exclude_catalogue_px > 0 else fp & ~cat & (score > 0))
    log("candidate cells (off-catalogue, score>0, excl>%g px)" % args.exclude_catalogue_px,
        int(cand.sum()))
    thin = emit67.min_separation_select(score, cand, min_sep_px=args.min_sep, max_dots=args.max_dots)
    log("after %g px thinning" % args.min_sep, int(thin.sum()))
    arms = {}
    for tag, prev in (("prevalence_low_inherited_12691", args.prevalence),
                      ("prevalence_catalogue_like_60988", args.prevalence_alt)):
        qh = emit67.calibrate(score, thin, prevalence_cells=prev)
        res = emit67.greedy_marginal_dti(qh, thin, dti_target=args.dti_target)
        arms[tag] = {"assumed_hidden_truth_cells": prev, "bar_alpha_dti": res["bar_alpha_dti"],
                     "accepted": res["n_accepted"],
                     "last_accepted_expected_credit": res["last_accepted_expected_credit"]}
        log(tag, "accepted", res["n_accepted"])
        if tag.startswith("prevalence_low"):
            dots = res["dots"]
    arms["thin_only"] = {"accepted": int(thin.sum()), "min_sep_px": args.min_sep}

    pred = np.zeros(score.shape, np.float32)
    pred[dots] = 1.0
    n_dots = int(dots.sum())
    log("SHIPPED dots", n_dots, "on catalogue:", int((dots & cat).sum()),
        "within3px of catalogue:", int((dots & (ndimage.distance_transform_edt(~cat) <= 3)).sum()))

    slug = "h67-oritip-relay"
    sha_tag = "pending"
    base = f"lane_c7b2cfa6-{slug}-{n_dots}dots-{STAMP}"
    nan_path = OUT / f"{base}-nan.tif"
    zero_path = OUT / f"{base}-zeros.tif"
    note = (f"GEMSDOE67 H67 orientation+tip geometry-aware decode; {n_dots} dots; "
            f"off-catalogue; local checks only; no organiser score claimed")
    assert len(note) <= 140, len(note)
    name = f"GEMSDOE67-H67-oritip-relay-{n_dots}"
    rec_nan = submission_writer.write_submission(nan_path, pred, fp,
                                                ROOT / "data/official/sample_submission.tif",
                                                overwrite=True, name=name, note=note)
    pred_z = np.where(fp, pred, 0.0)
    rec_z = submission_writer.write_submission(zero_path, pred_z, fp,
                                              ROOT / "data/official/sample_submission.tif",
                                              overwrite=True, name=name + "-zeros", note=note)
    log("wrote", nan_path.name, rec_nan["sha256"][:12], rec_nan["file"] and "")
    (EVID / "e3_emission.json").write_text(json.dumps({
        "generated_utc": STAMP, "evidence_class": "LOCAL MEASUREMENT (no organiser score)",
        "slug": slug, "stamp": STAMP, "name": name, "note": note, "note_chars": len(note),
        "dots": n_dots, "on_catalogue_pixels": int((dots & cat).sum()),
        "within_3px_of_catalogue": int((dots & (ndimage.distance_transform_edt(~cat) <= 3)).sum()),
        "min_sep_px": args.min_sep, "exclude_catalogue_px": args.exclude_catalogue_px,
        "max_len_tip_extension_px": args.max_len,
        "t_hi_pct": 99.5, "t_lo_pct": 99.0, "tip_extension_max_len_px": max_len,
        "tip_extension_disabled_reason": (
            "preregistered gate measured negative on both hide-and-recover folds; see "
            "evidence/c7b2cfa6/e2_holdout_arms.json paired A2_minus_A1 and A2_minus_A0"),
        "network_cells": n_net,
        "extension_cells": n_ext,
        "orientation_head_mae_cos2t": cos_err, "orientation_head_mae_sin2t": sin_err,
        "tip_head_auc_in_footprint": tip_auc,
        "selection_arms": arms,
        "files": {"nan": rec_nan, "zeros": rec_z},
        "out_of_fold_groups": K,
        "prevalence_assumption_disclosure":
            "qhat calibration uses an ASSUMED hidden-truth cell count; it is not a measurement.",
    }, indent=2))
    (OUT / "EMIT_INFO.json").write_text(json.dumps({
        "primary_file": nan_path.name, "sha256": rec_nan["sha256"], "bytes": nan_path.stat().st_size,
        "all_finite_file": zero_path.name, "sha256_zeros": rec_z["sha256"],
        "name": name, "note": note, "dots": n_dots, "generated_utc": STAMP,
    }, indent=2))
    print(json.dumps({"nan": nan_path.name, "sha256": rec_nan["sha256"], "dots": n_dots}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
