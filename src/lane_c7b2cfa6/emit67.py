"""Lane-67 node selection and emission.

Two selection rules, both from the lane brief:

* ``min_separation_select`` - keep candidates in descending score with a 4-5 px minimum separation
  (Poisson-disk thinning by score). Deterministic, matches the family's "dotted" convention.
* ``greedy_marginal_dti``   - calibrated greedy marginal-DTI acceptance. Using the exact identity
  derived in ``docs/research/metric-derivation.md`` (a new dot is accepted iff its kernel credit to
  a previously uncovered truth cell exceeds ``alpha * DTI``), the *expected* new credit of a
  candidate is ``sum_{|d|<=R} qhat(g) k(d) * uncovered(g)`` where ``qhat`` is the propensity field
  calibrated so that ``sum qhat`` equals the assumed hidden-truth prevalence. Accept iff
  expected new credit > alpha * dti_target.

``qhat`` calibration is a stated assumption, never a measurement: the hidden truth is not
available. Two prevalence assumptions are reported side by side.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

PIXEL_M = 100.0
R_M = 300.0
ALPHA = 0.2
_R_PX = int(np.floor(R_M / PIXEL_M))


def _kernel_lut() -> np.ndarray:
    """(2R+1, 2R+1) triangular kernel weights, 0 outside 300 m."""
    o = np.arange(-_R_PX, _R_PX + 1)
    d = PIXEL_M * np.hypot(o[:, None], o[None, :])
    return np.clip(1.0 - d / R_M, 0.0, None).astype(np.float32)


def calibrate(propensity: np.ndarray, valid: np.ndarray, prevalence_cells: float) -> np.ndarray:
    """Scale a propensity field so its mass over ``valid`` equals ``prevalence_cells``."""
    q = np.where(valid, propensity, 0.0).astype(np.float64)
    s = q.sum()
    if s <= 0:
        return q
    return q * (float(prevalence_cells) / s)


def min_separation_select(score: np.ndarray, candidate: np.ndarray, min_sep_px: float = 4.5,
                          max_dots: int | None = None) -> np.ndarray:
    """Boolean dot mask: descending-score greedy with a hard minimum separation."""
    cand = candidate & np.isfinite(score)
    vals = score[cand]
    ys, xs = np.nonzero(cand)
    order = np.lexsort((xs, ys, -vals))       # score first (last key dominates), ties raster-order
    ys, xs = ys[order], xs[order]
    r = int(np.ceil(min_sep_px))
    keep = np.zeros(score.shape, bool)
    blocked = np.zeros(score.shape, bool)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disk = (np.hypot(yy, xx) < min_sep_px)
    n = 0
    for y, x in zip(ys, xs):
        if blocked[y, x]:
            continue
        keep[y, x] = True
        y0, y1 = max(0, y - r), min(score.shape[0], y + r + 1)
        x0, x1 = max(0, x - r), min(score.shape[1], x + r + 1)
        sub = disk[y0 - (y - r):y1 - (y - r), x0 - (x - r):x1 - (x - r)]
        blocked[y0:y1, x0:x1] |= sub
        n += 1
        if max_dots is not None and n >= max_dots:
            break
    return keep


def greedy_marginal_dti(qhat: np.ndarray, candidate: np.ndarray, dti_target: float = 0.28,
                        max_dots: int | None = None, min_sep_px: float = 0.0) -> dict:
    """Calibrated greedy marginal-DTI selection.

    Returns the dot mask plus the audit trail (accepted count, expected-credit at the margin).
    ``covered`` tracks, for every cell, the best kernel credit already claimed by an accepted dot,
    so a candidate is only paid for credit that is *new* (the metric's max-over-x semantics).
    """
    lut = _kernel_lut()
    covered = np.zeros(qhat.shape, np.float32)
    bar = ALPHA * dti_target
    cand = candidate & (qhat > 0)
    vals = qhat[cand]
    ys, xs = np.nonzero(cand)
    if min_sep_px > 0:
        order = np.lexsort((xs, ys, -vals))
    else:
        order = np.lexsort((xs, ys, -vals))
    ys, xs = ys[order], xs[order]
    keep = np.zeros(qhat.shape, bool)
    last_credit = float("nan")
    n = 0
    for y, x in zip(ys, xs):
        y0, y1 = max(0, y - _R_PX), min(qhat.shape[0], y + _R_PX + 1)
        x0, x1 = max(0, x - _R_PX), min(qhat.shape[1], x + _R_PX + 1)
        kw = lut[y0 - (y - _R_PX):y1 - (y - _R_PX), x0 - (x - _R_PX):x1 - (x - _R_PX)]
        gain = float(np.sum(qhat[y0:y1, x0:x1] * kw * (kw > covered[y0:y1, x0:x1])))
        if gain <= bar:
            continue
        keep[y, x] = True
        np.maximum(covered[y0:y1, x0:x1], kw, out=covered[y0:y1, x0:x1])
        last_credit = gain
        n += 1
        if max_dots is not None and n >= max_dots:
            break
    return {"dots": keep, "n_accepted": n, "bar_alpha_dti": float(bar),
            "last_accepted_expected_credit": last_credit,
            "dti_target_assumed": float(dti_target)}
