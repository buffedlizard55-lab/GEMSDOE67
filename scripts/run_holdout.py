#!/usr/bin/env python3
"""Hide-and-recover funnel: score emission arms against withheld catalogue segments.

Arms (all emissions are binary unless stated):
  A0_incumbent_dots   dots on the dilated *visible* catalogue (the family that scored
                      0.26-0.2778 live), swept over radius and spacing, best reported
  A1_ovtr             this lane: evidence -> axial NMS -> hysteresis -> tip relay ->
                      calibrated greedy marginal-DTI dot selection
  A1_soft             the same selected sites carrying the calibrated probability instead of 1
  A2_no_relay         A1 without the tip-relay step (ablation)
  A1_matched          A1 re-emitted at exactly the pixel count of the incumbent arm
  A3_random           random control on the same active domain

Everything is trained/scored per spatial block, then pooled over the four folds.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gems67 import decode, emit, features  # noqa: E402
from gems67.dataio import FEATURE_DIR, footprint_from, read_labels, write_json  # noqa: E402
from gems67.grid import ALPHA  # noqa: E402
from gems67.holdout import build_folds, iter_folds, visible_train_masks  # noqa: E402
from gems67.metric import dti_exact  # noqa: E402

from scipy.ndimage import distance_transform_edt  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402


def load_channel(name: str, rows=None, cols=None) -> np.ndarray:
    a = np.load(FEATURE_DIR / f"{name}.npy", mmap_mode="r")
    if rows is not None:
        return np.asarray(a[rows, cols])
    return np.asarray(a)


def auc_canary(score: np.ndarray, truth: np.ndarray, mask: np.ndarray) -> float:
    s = np.asarray(score, np.float64)[mask]
    y = np.asarray(truth, bool)[mask]
    if y.all() or not y.any():
        return float("nan")
    return float(roc_auc_score(y, s))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=0, help="smoke mode: crop rows")
    ap.add_argument("--cols", type=int, default=0, help="smoke mode: crop cols")
    ap.add_argument("--out", default="evidence/holdout.json")
    ap.add_argument("--bar", type=float, default=ALPHA * 0.28,
                    help="marginal-inclusion bar (alpha * DTI estimate)")
    ap.add_argument("--r-excl", type=float, default=2.0)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--tau", type=float, nargs="+", default=[0.1, 0.2, 0.3, 0.5, 0.7])
    ap.add_argument("--cover-tau-default", type=float, default=0.3)
    ap.add_argument("--cover-radius", type=float, default=3.0)
    ap.add_argument("--high-q", type=float, default=0.90)
    ap.add_argument("--low-q", type=float, default=0.70)
    args = ap.parse_args()

    rows = slice(0, args.rows) if args.rows else None
    cols = slice(0, args.cols) if args.cols else None

    ev = load_channel("ev", rows, cols)
    cos2t = load_channel("cos2t", rows, cols)
    sin2t = load_channel("sin2t", rows, cols)
    coh = load_channel("coh", rows, cols)

    def fold_stream():
        for f in iter_folds(buffer_px=2):
            if rows is not None or cols is not None:
                for attr in ("block", "active", "truth", "known", "visible", "buffer_zone"):
                    setattr(f, attr, getattr(f, attr)[rows, cols])
            yield f

    print(f"[holdout] arms on {ev.shape} grid, bar={args.bar:.4f}, r_excl={args.r_excl}")

    results: dict[str, list[dict]] = {}
    canary: dict[str, list[float]] = {}

    labels = read_labels()
    footprint_full = footprint_from(labels)
    footprint = footprint_full if (rows is None and cols is None) else footprint_full[rows, cols]

    t0 = time.time()
    for fold in fold_stream():
        pos, neg, dist_visible = visible_train_masks(fold, footprint, min_dist_px=5.0)
        if pos.sum() < 50 or neg.sum() < 50:
            print(f"[holdout] fold {fold.name}: too few training pixels, skipped")
            continue

        # ---- calibration ----
        # Two targets.  ``q3`` (P(pixel lies within 3 px of a fault)) is the field the
        # published lane description names; ``q1`` (P(pixel *is* a fault pixel)) is the field
        # whose kernel sum is an unbiased estimate of the expected marginal credit
        # delta T(x) = sum_d k(d) q1(x+d) that the marginal-DTI bar is stated in.
        within3 = dist_visible <= 3.0
        train_mask = (pos | neg) & ~fold.buffer_zone
        cal3 = emit.calibrate_q(ev, within3, train_mask)
        q3 = emit.apply_calibration(ev, cal3)
        cal1 = emit.calibrate_q(ev, fold.visible & ~fold.block, train_mask)
        q1 = emit.apply_calibration(ev, cal1)

        # ---- leakage canary on the scored block, before any emission decision ----
        for name in ("ev", "coh"):
            a = np.asarray(load_channel(name, rows, cols), np.float64)
            canary.setdefault(name, []).append(auc_canary(a, fold.truth, fold.active))
        canary.setdefault("order_R", []).append(
            auc_canary(load_channel("order_R", rows, cols), fold.truth, fold.active))

        # ---- decode (lane) ----
        dec = decode.decode(ev, cos2t, sin2t, high_q=args.high_q, low_q=args.low_q,
                            search=fold.active)
        ec = emit.expected_credit(np.where(np.isfinite(q), q, 0.0).astype(np.float32))
        cand = dec["candidates"] & fold.active
        lane_dots = emit.greedy_dots(ec, bar=args.bar, r_excl=args.r_excl, candidate_mask=cand)
        lane_dots_no_relay = emit.greedy_dots(ec, bar=args.bar, r_excl=args.r_excl,
                                              candidate_mask=dec["skel"] & fold.active)
        soft = np.where(lane_dots, np.clip(q3, 0.0, 1.0), 0.0).astype(np.float32)

        # ---- this session's rule: greedy kernel-cover of the estimated fault set ----
        cover_arms = {}
        for tau in args.tau:
            d_cov = emit.cover_greedy(q1, tau=tau, candidate_mask=dec["candidates"] & fold.active,
                                      radius=args.cover_radius)
            cover_arms[f"A5_cover_tau{tau:g}"] = d_cov
        # variant with no geometry gate at all (all in-domain pixels are legal dot sites)
        cover_arms[f"A6_cover_allpix_tau{args.cover_tau_default:g}"] = emit.cover_greedy(
            q1, tau=args.cover_tau_default, candidate_mask=fold.active, radius=args.cover_radius)

        # ---- incumbent sweep: dots along the dilated visible catalogue ----
        best_inc, best_inc_cfg = None, None
        for radius_px in (1, 2, 3):
            for spacing in (2, 3, 4):
                m = emit.catalogue_dilation_dots(fold.visible, radius_px, spacing) & fold.active
                s = dti_exact(m.astype(np.float32), fold.truth, valid=fold.active)["dti"]
                if best_inc is None or s > best_inc_cfg["dti"]:
                    best_inc, best_inc_cfg = m, dict(radius_px=radius_px, spacing=spacing, dti=s)
        # the lane re-emitted at exactly the incumbent arm's pixel count (matched mass)
        n_lane = int(lane_dots.sum())
        n_inc = int(best_inc.sum())
        matched = emit.greedy_dots(ec, bar=args.bar, r_excl=args.r_excl, candidate_mask=cand,
                                   max_dots=n_inc)

        arms = dict(cover_arms)
        arms.update({
            "A0_incumbent_dots": (best_inc, best_inc_cfg),
            "A1_ovtr": (lane_dots, None),
            "A1_soft": (soft, None),
            "A2_no_relay": (lane_dots_no_relay, None),
            "A1_matched": (matched, None),
            "A3_random": (emit.random_control(fold.active, max(n_lane, 1)), None),
        })
        for arm, (m, cfg) in arms.items():
            sc = dti_exact(np.asarray(m, np.float32), fold.truth, valid=fold.active)
            sc["n_px"] = int((np.asarray(m) > 0).sum())
            if cfg:
                sc["cfg"] = cfg
            results.setdefault(arm, []).append(sc)
            if not args.quiet:
                print(f"[holdout] {fold.name} {arm:20s} dti={sc['dti']:.4f} "
                      f"px={sc['n_px']:7d} tp={sc['tp']:.1f} k={sc['n_truth']}", flush=True)
        del dec, ec, cand, lane_dots, lane_dots_no_relay, soft, matched, best_inc
        del q1, q3, cover_arms

    pooled = {}
    for arm, rows_ in results.items():
        tp = sum(r["tp"] for r in rows_)
        fp = sum(r["fp"] for r in rows_)
        fn = sum(r["fn"] for r in rows_)
        k = sum(r["n_truth"] for r in rows_)
        pooled[arm] = dict(
            dti=float(tp / (tp + 0.2 * fp + 0.8 * fn + 1e-12)),
            tp=tp, fp=fp, fn=fn, n_truth=k,
            coverage=float(tp / k) if k else 0.0,
            mean_px=float(np.mean([r["n_px"] for r in rows_])),
            per_fold=[round(r["dti"], 5) for r in rows_],
            folds_above_incumbent=int(sum(
                1 for a, b in zip(rows_, results.get("A0_incumbent_dots", [])) if a["dti"] > b["dti"])),
        )

    canary_out = {k: [None if v != v else round(v, 4) for v in vs] for k, vs in canary.items()}
    out = dict(
        instrument="hide-and-recover, 4 quadrant folds, strict masking of visible catalogue",
        grid=list(ev.shape), bar=args.bar, r_excl=args.r_excl,
        pooled=pooled, leakage_canary_auc=canary_out,
        seconds=round(time.time() - t0, 1),
        note=("Truth of this instrument is the older catalogue, so it can never reward a "
              "genuinely new fault; it screens emission rules only."),
    )
    write_json(Path(args.out), out)
    print(json.dumps(pooled, indent=2))
    print(f"[holdout] wrote {args.out} in {out['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
