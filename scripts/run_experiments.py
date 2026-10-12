"""Run the lane's hide-and-recover experiments (E1 ablation, E2 lane, E3 blur).

Everything is scored by the vendored shared evaluator
(``gems57.evaluate_holdout``: pooled exact DTI, alpha 0.2, beta 0.8, 300 m
triangular kernel, paired physical-block bootstrap CI).  Labels are
HOLDOUT-DTI by construction.  No number produced here is an organiser score.

Usage::

    PYTHONPATH=src python scripts/run_experiments.py --features data/raw/gems-geodawn-numerical-features.tif
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gems57 import evaluate_holdout, holdout as holdout_mod, metric, grid as gridmod  # noqa: E402
from gems67 import decode as dec, features as featmod, heads as headsmod, lane as lanemod  # noqa: E402

EVAL_VERSION = evaluate_holdout.VERSION
ARMS = ("iso", "lane", "lane_blur")
CANDIDATE = "lane"


def _crop_fold(fold: dict, bbox: tuple[slice, slice]) -> dict:
    return {k: (v[bbox] if isinstance(v, np.ndarray) and v.ndim == 2 else v)
            for k, v in fold.items()}


def _canary(cache, visible, truth, region, rng, max_samples=400_000):
    """Feature-alone AUC for withheld truth vs far background (leakage canary)."""
    from sklearn.metrics import roc_auc_score
    dist_vis = ndi.distance_transform_edt(~np.asarray(visible, bool))
    layers = dict((n, cache.layer(n)) for n in cache.layers)
    layers["dist_to_visible"] = (-dist_vis).astype(np.float32)
    pos = truth & region
    neg = region & ~truth & (dist_vis >= 10)
    py, px = np.nonzero(pos)
    ny, nx = np.nonzero(neg)
    if ny.size > max_samples:
        sel = rng.choice(ny.size, size=max_samples, replace=False)
        ny, nx = ny[sel], nx[sel]
    ys = np.concatenate([py, ny])
    xs = np.concatenate([px, nx])
    y = np.concatenate([np.ones(py.size), np.zeros(ny.size)]).astype(np.int32)
    out = {}
    for name, arr in layers.items():
        vals = np.concatenate([arr[py, px], arr[ny, nx]]).astype(np.float64)
        ok = np.isfinite(vals)
        if y[ok].sum() == 0 or (~y[ok]).sum() == 0:
            out[name] = None
            continue
        try:
            auc = float(roc_auc_score(y[ok], vals[ok]))
        except ValueError:
            auc = None
        out[name] = auc
    return dict(feature_alone_auc=out, n_pos=int(py.size), n_neg=int(ny.size),
                truth="buffered-hidden catalogue pixels",
                threshold=0.90,
                verdict_rule="AUC > 0.90 => leakage until proven otherwise")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/raw/gems-geodawn-numerical-features.tif")
    ap.add_argument("--out", default="evidence")
    ap.add_argument("--overwrite-cache", action="store_true")
    ap.add_argument("--seeds", default="20,21")
    ap.add_argument("--emission", default="greedy", choices=["greedy", "spacing"])
    args = ap.parse_args()

    t0 = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]

    g = gridmod.load_grid(repo / "data" / "bridge")
    print(f"grid: {g.height}x{g.width} footprint={int(g.footprint.sum())} "
          f"catalogue={int(g.catalogue.sum())}", flush=True)

    cache = featmod.build_cache(Path(args.features), repo / "data" / "cache" / "features67.f32",
                                g.footprint, overwrite=args.overwrite_cache)
    print(f"feature cache: {len(cache.layers)} layers {cache.layers}", flush=True)

    seeds = tuple(int(s) for s in args.seeds.split(","))
    folds, quad = holdout_mod.buffered_component_draw(g, seed=seeds[0], hide_frac=0.20,
                                                      buffer_px=3, boundary_px=12)
    fold_sets = {seeds[0]: folds}
    if len(seeds) > 1:
        for s in seeds[1:]:
            fold_sets[s], _ = holdout_mod.buffered_component_draw(g, seed=s, hide_frac=0.20,
                                                                  buffer_px=3, boundary_px=12)
    n_withheld = int(folds[0]["hidden_all"].sum())
    print(f"buffered draw seed{seeds[0]}: withheld {n_withheld} px "
          f"visible {int(folds[0]['visible'].sum())} px", flush=True)

    terms_by_arm = {a: np.zeros((0, 4)) for a in ARMS}
    all_terms = {a: [] for a in ARMS}
    fold_reports = []
    canaries = {}

    for seed, flist in fold_sets.items():
        visible = np.asarray(flist[0]["visible"], bool)
        hidden_all = np.asarray(flist[0]["hidden_all"], bool)
        rng = np.random.default_rng(9000 + seed)
        canaries[str(seed)] = _canary(cache, visible, hidden_all, g.footprint, rng)

        print(f"[seed {seed}] fitting heads on {int(visible.sum())} visible px ...", flush=True)
        heads = headsmod.fit_heads(cache, visible)
        print(f"[seed {seed}] heads fitted: {heads.fit_receipt}", flush=True)
        preds = headsmod.predict_full(cache, heads)
        print(f"[seed {seed}] predicted: p mean={preds.p.mean():.4f} "
              f"p@visible={preds.p[visible].mean():.4f}", flush=True)

        arm_runs = {}
        for arm in ARMS:
            res = lanemod.run_arm(arm, cache, visible, g.footprint, heads=heads,
                                  preds=preds, emission=args.emission)
            arm_runs[arm] = res
            print(f"[seed {seed}] arm {arm}: {res.n_dots} dots "
                  f"support={int(res.support.sum())} ext={int(res.extended.sum())}", flush=True)

        for f in flist:
            region = np.asarray(f["region"], bool)
            rows = np.flatnonzero(region.any(axis=1))
            cols = np.flatnonzero(region.any(axis=0))
            bbox = (slice(max(0, rows[0] - 6), min(g.height, rows[-1] + 7)),
                    slice(max(0, cols[0] - 6), min(g.width, cols[-1] + 7)))
            fold_c = _crop_fold(f, bbox)
            valid_c = g.footprint[bbox]
            truth_full = np.asarray(f["truth"], bool)
            tip_adj = lanemod.tip_adjacent_truth(truth_full, radius_px=3.0)
            rep = dict(seed=seed, fold=f["name"], bbox=[bbox[0].start, bbox[0].stop,
                                                        bbox[1].start, bbox[1].stop],
                       n_truth=int(truth_full.sum()), n_tip_adjacent=int(tip_adj.sum()))
            for arm in ARMS:
                em = arm_runs[arm].emitted[bbox].astype(np.float64)
                result, terms = evaluate_holdout.evaluate(
                    em, fold_c, valid_c, block_side=200,
                    origin=(bbox[0].start, bbox[1].start),
                    global_shape=g.shape)
                all_terms[arm].append(terms)
                # tip-adjacent subset coverage (gate criterion 2): mean kernel
                # credit over withheld truth pixels within 3 px of a withheld tip
                p_full = arm_runs[arm].emitted.astype(np.float64)
                cov_t, _q_t, _ = metric.max_cover(p_full, np.asarray(f["truth"], bool))
                gy, gx = np.nonzero(truth_full)
                tip_sel = tip_adj[gy, gx]
                tip_cov = float(cov_t[tip_sel].mean()) if tip_sel.any() else 0.0
                rep[arm] = dict(dti=float(result["dti"]),
                                n_emitted_in_fold=int(result["n_emitted"]),
                                tpw=float(result["tp"]), fpw=float(result["fp"]),
                                fnw=float(result["fn"]),
                                tip_adjacent_coverage=tip_cov)
            fold_reports.append(rep)
            print(f"  fold {f['name']} seed {seed}: " +
                  " ".join(f"{a}={rep[a]['dti']:.4f}" for a in ARMS), flush=True)

    # pooled summaries with paired CI
    pooled_terms = {}
    for arm in ARMS:
        pooled_terms[arm] = np.sum(np.stack(all_terms[arm], axis=0), axis=0)
    summary = evaluate_holdout.pooled_summary(pooled_terms, draws=1000, seed=520810,
                                              candidate=CANDIDATE)
    print(json.dumps(summary["scores"], indent=1), flush=True)
    print(json.dumps(summary["paired_differences"], indent=1), flush=True)

    # tip-adjacent gate: pooled tip-adjacent coverage per arm
    tip_gate = {}
    for arm in ARMS:
        # pooled tip-adjacent coverage = sum(TP on tip-adj)/sum(tip-adj truth)
        num = den = 0.0
        for rep in fold_reports:
            den += rep["n_tip_adjacent"]
            num += rep[arm]["tip_adjacent_coverage"] * rep["n_tip_adjacent"]
        tip_gate[arm] = dict(pooled_tip_adjacent_coverage=float(num / den) if den else 0.0,
                             n_tip_adjacent_pixels=int(den))
    print("tip-adjacent gate:", json.dumps(tip_gate, indent=1), flush=True)

    cand = summary["scores"][CANDIDATE]
    # Gate control is the PREREGISTERED ABLATION (iso = per-pixel decoding),
    # not the best arm: lane_blur is a variant OF this lane, not a control.
    best_ctrl = summary["best_comparable_control"]
    delta = summary["paired_differences"]["iso"]
    variant = summary["paired_differences"].get("lane_blur")
    gate_dti = delta["ci95"][0] > 0.0
    gate_tip = (tip_gate[CANDIDATE]["pooled_tip_adjacent_coverage"] >
                tip_gate["iso"]["pooled_tip_adjacent_coverage"])
    gate = dict(dti_gain_positive_ci=gate_dti,
                tip_adjacent_recovery_better=gate_tip,
                passed=bool(gate_dti and gate_tip),
                control="iso (per-pixel ablation; preregistered)",
                delta_vs_ablation=delta,
                variant_lane_blur=variant,
                best_arm_by_dti=max(summary["scores"],
                                    key=lambda n: summary["scores"][n]["dti"]),
                rule="both criteria required by the lane brief: paired HOLDOUT-DTI "
                     "gain vs the ablation with 95% CI > 0, AND better tip-adjacent "
                     "recovery")

    card = dict(
        label="HOLDOUT-DTI", evaluator_version=EVAL_VERSION,
        arms=ARMS, candidate=CANDIDATE,
        withheld_positive_pixels=cand["withheld_positive_pixels"],
        n_fold_cells=len(fold_reports), seeds=list(seeds),
        scores=summary["scores"], paired_differences=summary["paired_differences"],
        bootstrap=summary["bootstrap"], tip_adjacent_gate=tip_gate, gate=gate,
        folds=fold_reports, canary=canaries,
        params=lanemod.PARAMS, emission=args.emission,
        implementation_sha256=summary["implementation_sha256"],
        elapsed_s=round(time.time() - t0, 1),
    )
    def _jsonify(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f"not JSON serializable: {type(o)}")

    (out / "experiments.json").write_text(
        json.dumps(card, indent=1, allow_nan=False, default=_jsonify) + "\n")
    print(f"wrote {out / 'experiments.json'}  gate={gate}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
