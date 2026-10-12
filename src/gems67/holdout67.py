"""Lane-67 evaluation: hide-and-recover holdout, pooled DTI, leakage canary, tip-adjacent recovery.

Protocol (lane brief, item 2): withhold whole fault segments with a buffer, derive every
catalogue-based feature only from the visible faults, mask visible faults pixel-exactly, and score
pooled DTI (alpha 0.2, beta 0.8, 300 m triangular kernel) over the withheld positives.

The shared evaluator is ``gems.metric.tversky_terms`` (template provenance in
``registry/template_provenance.json``); this module only builds the masks and pools the terms.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from gems.holdout import spatial_block_holdout
from gems.metric import tversky_terms

PIXEL_M = 100.0


def make_folds(fault_mask: np.ndarray, coverage: np.ndarray, n_folds: int = 4,
               block_px: int = 64, holdout_fraction: float = 0.25, buffer_px: int = 3,
               seed0: int = 67) -> list[dict]:
    """Spatially blocked hide-and-recover folds. ``coverage`` = the official footprint."""
    folds = []
    for f in range(n_folds):
        # rotate the withheld fraction across folds by shifting the seed only (blocks are random)
        sp = spatial_block_holdout(fault_mask, coverage, block_px=block_px,
                                   holdout_fraction=holdout_fraction, buffer_px=buffer_px,
                                   seed=seed0 + 101 * f, min_lidar_fraction=0.0)
        sp["fold"] = f
        folds.append(sp)
    return folds


def pooled_dti(pred: np.ndarray, folds: list[dict], mask_visible: bool = True) -> dict:
    """Pool TP/FP/FN across folds and return DTI with a fold-level bootstrap CI.

    ``mask_visible`` implements "mask visible faults pixel-exactly": any emission on a cell that is
    a *visible* fault in that fold is removed before scoring, so the number measures discovery of
    withheld structure and not memory of the catalogue.
    """
    tp = fp = fn = 0.0
    per_fold = []
    for sp in folds:
        p = np.asarray(pred, np.float64).copy()
        if mask_visible:
            p[sp["visible"]] = 0.0
        # the scored domain is the withheld block; zero everything outside it so that FP mass
        # placed elsewhere in the footprint is not charged to this fold (pooled convention).
        outside = ~sp["held_block"]
        p_out = p.copy()
        p_out[outside] = 0.0
        t, f_, n_ = tversky_terms(p_out, sp["holdout"])
        tp += t; fp += f_; fn += n_
        per_fold.append({"fold": sp["fold"], "tp": t, "fp": f_, "fn": n_,
                         "dti": t / (t + 0.2 * f_ + 0.8 * n_ + 1e-9) if (t + f_ + n_) else 0.0,
                         "withheld_positives": int(sp["holdout"].sum())})
    from gems.metric import dti_from_terms
    dti = dti_from_terms(tp, fp, fn)
    vals = np.array([d["dti"] for d in per_fold], float)
    n = len(vals)
    se = float(vals.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    return {"dti_pooled": float(dti), "tp_w": float(tp), "fp_w": float(fp), "fn_w": float(fn),
            "per_fold": per_fold, "withheld_positives_total": int(sum(d["withheld_positives"] for d in per_fold)),
            "fold_mean": float(vals.mean()) if n else None,
            "ci95": [float(vals.mean() - 1.96 * se), float(vals.mean() + 1.96 * se)] if n > 1 else None,
            "evaluator": "gems.metric.tversky_terms (template) pooled over folds, alpha=0.2 beta=0.8 R=300m"}


def tip_adjacent_recovery(pred: np.ndarray, folds: list[dict], radius_px: int = 5) -> dict:
    """Recovery of withheld pixels that lie within ``radius_px`` of a *visible* trace tip.

    This is the lane's own gate: the mechanism claims to extend traces past mapped tips, so the
    withheld positives it should recover best are exactly those adjacent to where a visible trace
    stops. Tip = 8-connected-component pixel of the visible mask with <=1 visible neighbour in the
    component skeleton sense, approximated here by "visible pixel whose visible 8-neighbour count
    is <=3" (a thin trace end). Reported as the pooled DTI restricted to that subpopulation.
    """
    tp = fp = fn = 0.0
    n_tip_pos = 0
    for sp in folds:
        vis = sp["visible"]
        nc = ndimage.convolve(vis.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - vis.astype(np.uint8)
        ends = vis & (nc <= 3)
        if not ends.any():
            continue
        near_tip = ndimage.distance_transform_edt(~ends) <= radius_px
        truth = sp["holdout"] & near_tip
        n_tip_pos += int(truth.sum())
        p = np.asarray(pred, np.float64).copy()
        p[vis] = 0.0
        p[~sp["held_block"]] = 0.0
        t, f_, n_ = tversky_terms(p, truth)
        tp += t; fp += f_; fn += n_
    from gems.metric import dti_from_terms
    return {"dti_tip_adjacent": float(dti_from_terms(tp, fp, fn)), "tip_adjacent_positives": int(n_tip_pos),
            "radius_px": radius_px}


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    """Rank-based AUC (Mann-Whitney), ties handled by average rank."""
    y = np.asarray(y).astype(bool).ravel()
    s = np.asarray(s, float).ravel()
    n1 = int(y.sum()); n0 = int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), float)
    ss = s[order]
    i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))
