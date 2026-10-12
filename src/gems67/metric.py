"""Distance-weighted Tversky index (DTI) — the competition metric, verified line by line.

Source (official): DrivenData competition #306, problem description, section
"Performance metric" — https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/

Published equations, transcribed without change:

    k(d)  = (1 - d/R)_+                      triangular kernel, R = 300 m (= 3 px at 100 m)
    TP_w  = sum_{g in G} max_{x: d(x,g) <= R} p(x) * k(d(x,g))
    FP_w  = sum_{x: p(x) > 0} p(x) * [1 - max_{g in G} k(d(x,g))]
    FN_w  = sum_{g in G} [1 - max_{x: d(x,g) <= R} p(x) * k(d(x,g))]
    DTI   = TP_w / (TP_w + alpha*FP_w + beta*FN_w + eps),  alpha = 0.2, beta = 0.8

Two identities are used throughout this repository and are both unit-tested
(``tests/test_metric.py``):

1.  ``FN_w = |G| - TP_w``  (exact, because the inner max is zero when no prediction
    is within R, and ``p`` is clipped to [0, 1]).
2.  ``DTI = T / (alpha*(T + S - M) + beta*|G|)`` with ``T = TP_w``, ``S = sum_x p(x)``
    and ``M = sum_x p(x) * max_g k(d(x,g))``, since ``FP_w = S - M``.

Corollary used for emission (marginal-inclusion bar): adding one unit of mass at a
pixel whose best kernel weight to any truth pixel is ``k`` changes the numerator by
at most ``k`` and the denominator by exactly ``alpha`` when ``T = M`` (mass on
truth); the score is non-decreasing iff ``k > alpha * DTI``.  Because the score is
*linear* in the mass placed at a single pixel while ``k > alpha*DTI``, and *decreasing*
while ``k < alpha*DTI``, the optimal submission for a fixed set of emission sites is
binary ``{0, 1}`` — this is why binary dot fields beat probability fields of equal
support, and it is verified numerically in ``tests/test_metric.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt

from .grid import ALPHA, BETA, KERNEL_RADIUS_PX as RADIUS_PX

EPS: float = 1e-12


def kernel(d, radius: float = RADIUS_PX):
    """Triangular kernel ``k(d) = max(1 - d/radius, 0)``; ``d`` and ``radius`` in pixels."""
    return np.maximum(1.0 - np.asarray(d, dtype=np.float64) / radius, 0.0)


def kernel_offsets(radius: float = RADIUS_PX) -> list[tuple[int, int, float]]:
    """All integer offsets with non-zero kernel weight, with their weight."""
    r = int(np.ceil(radius))
    out: list[tuple[int, int, float]] = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            k = float(kernel(np.hypot(dy, dx), radius))
            if k > 0.0:
                out.append((dy, dx, k))
    return out


_OFFS = kernel_offsets()


def _shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Shift ``a`` by (dy, dx) with zero fill (valid here: all shifted sources are >= 0)."""
    out = np.zeros_like(a)
    h, w = a.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = a[max(0, -dy):min(h, h - dy), max(0, -dx):min(w, w - dx)]
    return out


def _prepare(pred, truth, valid=None, known=None):
    pred = np.asarray(pred)
    truth = np.asarray(truth)
    if pred.ndim != 2 or pred.shape != truth.shape:
        raise ValueError("prediction and truth must be equal-shaped 2-D grids")
    valid = np.ones(pred.shape, bool) if valid is None else np.asarray(valid, bool)
    known = np.zeros(pred.shape, bool) if known is None else np.asarray(known, bool)
    if valid.shape != pred.shape or known.shape != pred.shape:
        raise ValueError("mask grid mismatch")
    active = valid & ~known
    vals = np.asarray(pred, dtype=np.float64)[active]
    if not np.isfinite(vals).all():
        raise ValueError("predictions inside the scored domain must be finite")
    if (vals < 0).any() or (vals > 1).any():
        raise ValueError("predictions inside the scored domain must lie in [0, 1]")
    p = np.where(active, np.nan_to_num(pred, nan=0.0, posinf=1.0, neginf=0.0), 0.0).astype(np.float64)
    g = active & (np.asarray(truth) > 0)
    return p, g, active


def dti_exact(pred, truth, valid=None, known=None, alpha: float = ALPHA, beta: float = BETA) -> dict:
    """Exact DTI for soft or binary predictions, with organizer-style masking.

    ``known`` marks pixels excluded from *every* term (the organizer masks known
    USGS/INGENIOUS faults — verified in the competition forum thread 11516, answer by
    DrivenData staff: "Pixels corresponding to known USGS/INGENIOUS faults are masked /
    excluded from evaluation, so they do not count towards penalty terms").
    """
    p, g, _ = _prepare(pred, truth, valid, known)
    h, w = p.shape
    yy, xx = np.nonzero(g)
    n = int(yy.size)
    if n == 0:
        return dict(tp=0.0, fp=float(p.sum()), fn=0.0, n_truth=0, dti=0.0, coverage=0.0)
    credit = np.zeros(n, dtype=np.float64)
    for dy, dx, k in _OFFS:
        ny, nx = yy + dy, xx + dx
        ok = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
        credit[ok] = np.maximum(credit[ok], p[ny[ok], nx[ok]] * k)
    tp = float(credit.sum())
    fn = float(n) - tp
    d = distance_transform_edt(~g)
    fp = float((p * (1.0 - kernel(d))).sum())
    dti = tp / (tp + alpha * fp + beta * fn + EPS)
    return dict(tp=tp, fp=fp, fn=fn, n_truth=n, dti=float(dti), coverage=tp / n)


def dti_bruteforce(pred, truth, alpha: float = ALPHA, beta: float = BETA,
                   radius: float = RADIUS_PX) -> dict:
    """Literal transcription of the published equations, O(|G| * |P|). Test oracle only."""
    pred = np.asarray(pred, dtype=float)
    truth = np.asarray(truth, bool)
    gs = np.argwhere(truth)
    xs = np.argwhere(pred > 0)
    tp = fp = fn = 0.0
    for g in gs:
        best = 0.0
        for x in xs:
            d = float(np.hypot(*(x - g)))
            if d <= radius:
                best = max(best, pred[tuple(x)] * max(1.0 - d / radius, 0.0))
        tp += best
        fn += 1.0 - best
    for x in xs:
        kbest = 0.0
        for g in gs:
            kbest = max(kbest, max(1.0 - float(np.hypot(*(x - g))) / radius, 0.0))
        fp += pred[tuple(x)] * (1.0 - kbest)
    return dict(tp=tp, fp=fp, fn=fn, n_truth=int(truth.sum()),
                dti=tp / (tp + alpha * fp + beta * fn + EPS))


def dti_from_components(tp: float, fp: float, fn: float, alpha: float = ALPHA,
                        beta: float = BETA) -> float:
    return float(tp / (tp + alpha * fp + beta * fn + EPS))


def components(pred, truth, valid=None, known=None) -> dict:
    """TP_w / FP_w / FN_w plus the algebra terms ``S`` (mass), ``M`` (mass near truth), ``K``."""
    c = dti_exact(pred, truth, valid=valid, known=known)
    p, g, _ = _prepare(pred, truth, valid, known)
    d = distance_transform_edt(~g)
    m = float((p * kernel(d)).sum())
    out = dict(c)
    out.update(S=float(p.sum()), M=m, K=float(g.sum()),
               credit_per_unit_mass=(c["tp"] / float(p.sum())) if p.sum() else 0.0,
               marginal_bar=ALPHA * c["dti"])
    return out


@dataclass(frozen=True)
class CreditAudit:
    n_emitted: int
    total_mass: float
    redundancy_fraction: float
    mean_self_kernel: float


def credit_audit(mask) -> CreditAudit:
    """Truth-free structural audit of an emission mask: how much mass is redundant."""
    m = np.asarray(mask, dtype=np.float64)
    pos = m > 0
    n = int(pos.sum())
    if n == 0:
        return CreditAudit(0, 0.0, 0.0, 0.0)
    best = np.zeros(m.shape)
    for dy, dx, k in _OFFS:
        if dy == 0 and dx == 0:
            continue
        np.maximum(best, _shift(m, -dy, -dx) * k, out=best)
    red = np.clip(best, 0.0, 1.0)
    return CreditAudit(n_emitted=n, total_mass=float(m.sum()),
                       redundancy_fraction=float((red[pos] > 0).mean()),
                       mean_self_kernel=float(red[pos].mean()))
