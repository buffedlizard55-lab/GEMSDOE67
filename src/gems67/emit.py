"""Emission: calibrated greedy marginal-DTI selection, and the two reference baselines.

Why greedy marginal selection is the right objective
---------------------------------------------------
Write the metric in its algebra form (verified identity, ``tests/test_metric.py``):

    DTI = T / ( alpha*(T + S - M) + beta*K )

with ``T`` the distance-weighted true-positive credit, ``S`` the total emitted mass, ``M`` the
part of that mass sitting within the 300 m kernel of a truth pixel, and ``K`` the number of
truth pixels.  Adding a unit of mass at a pixel whose best kernel weight to any truth pixel is
``k`` gives, in the worst case that the new mass is the best supporter of that truth pixel,

    dDTI > 0   <=>   k > alpha * DTI          (the marginal-inclusion bar)

so the optimal *binary* support for a fixed scoring situation is the greedily selected set of
pixels whose expected marginal kernel credit exceeds ``0.2 * DTI``.  The objective is
submodular (diminishing returns of overlapping kernels), which is what makes the greedy
selection near-optimal (Nemhauser, Wolsey & Fisher 1978, 1 - 1/e).

At emission time the truth is unknown, so the marginal credit of a candidate pixel is its
*expected* credit, computed from a calibrated probability field ``q``:

    EC(x) = sum_{d : |d| <= 3 px} k(|d|) * q(x + d)

``q`` is calibrated on the fold's *visible* faults only (hide-and-recover), so no withheld
information enters the emission.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_dilation, convolve, distance_transform_edt
from scipy.spatial import cKDTree

from .grid import ALPHA, KERNEL_RADIUS_PX
from .metric import kernel_offsets

_OFFS = kernel_offsets()
_DY = np.array([o[0] for o in _OFFS], dtype=np.int64)
_DX = np.array([o[1] for o in _OFFS], dtype=np.int64)
_KW = np.array([o[2] for o in _OFFS], dtype=np.float64)


def expected_credit(q: np.ndarray) -> np.ndarray:
    """EC(x) = sum over the kernel support of k(d) * q(x + d)."""
    out = np.zeros(q.shape, np.float32)
    for dy, dx, k in _OFFS:
        out += k * _shift(q, dy, dx)
    return out


def _shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    out = np.zeros_like(a)
    h, w = a.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = a[max(0, -dy):min(h, h - dy), max(0, -dx):min(w, w - dx)]
    return out


def calibrate_q(score: np.ndarray, within3: np.ndarray, mask: np.ndarray,
                n_bins: int = 24, prior: float = 0.02) -> dict:
    """Quantile-bin calibration of an evidence field to P(pixel within 3 px of a fault)."""
    v = np.asarray(score, np.float64)[mask]
    y = np.asarray(within3, bool)[mask]
    qs = np.quantile(v, np.linspace(0, 1, n_bins + 1))
    qs = np.unique(qs)
    edges = qs
    idx = np.clip(np.searchsorted(edges, v, side="right") - 1, 0, len(edges) - 2)
    n = np.bincount(idx, minlength=len(edges) - 1).astype(np.float64)
    p = np.bincount(idx, weights=y.astype(np.float64), minlength=len(edges) - 1)
    base = float(y.mean()) if y.size else prior
    rate = (p + prior * 5.0) / (n + 5.0)
    return dict(edges=edges.tolist(), rate=rate.tolist(), base_rate=base, n_bins=int(len(rate)))


def apply_calibration(score: np.ndarray, cal: dict) -> np.ndarray:
    edges = np.asarray(cal["edges"], np.float64)
    rate = np.asarray(cal["rate"], np.float64)
    idx = np.clip(np.searchsorted(edges, np.asarray(score, np.float64), side="right") - 1,
                  0, len(rate) - 1)
    return rate[idx].astype(np.float32)


def greedy_dots(ec: np.ndarray, bar: float, r_excl: float = 2.0,
                candidate_mask: np.ndarray | None = None, max_dots: int | None = None) -> np.ndarray:
    """Greedy submodular selection with an exclusion radius, in descending expected credit.

    ``bar`` is the marginal-inclusion bar ``alpha * DTI_estimate`` (default 0.2 * 0.28 = 0.056).
    The exclusion radius approximates the kernel's own overlap: after a dot is placed, the
    credit it provides to everything within ``r_excl`` is used up.
    """
    cand = np.isfinite(ec) & (ec > bar)
    if candidate_mask is not None:
        cand &= candidate_mask
    rr, cc = np.nonzero(cand)
    if rr.size == 0:
        return np.zeros(ec.shape, bool)
    vals = ec[rr, cc]
    order = np.argsort(-vals, kind="stable")
    rr, cc = rr[order], cc[order]
    pts = np.stack([rr, cc], axis=1).astype(np.float64)
    tree = cKDTree(pts)
    accepted = np.zeros(rr.size, bool)
    taken = np.zeros(ec.shape, bool)
    removed = np.zeros(rr.size, bool)
    n_taken = 0
    for i in range(rr.size):
        if removed[i] or accepted[i]:
            continue
        accepted[i] = True
        taken[rr[i], cc[i]] = True
        n_taken += 1
        for j in tree.query_ball_point(pts[i], r_excl):
            removed[j] = True
        if max_dots is not None and n_taken >= max_dots:
            break
    return taken


# --------------------------------------------------------------------------------------------
# Reference baselines used in the funnel (each is re-emitted at matched pixel count).
# --------------------------------------------------------------------------------------------

def dot_spacing(skeleton: np.ndarray, spacing: int) -> np.ndarray:
    """Dot-thin a binary mask on a lattice: keep every ``spacing``-th pixel of each component.

    Deterministic phase: a pixel is kept when ``(row + col) % spacing == 0`` inside a
    candidate slab, then the slab is thinned to single dots along the trace (this is the
    group's published 'dotted' family, re-implemented so it can be scored on the holdout).
    """
    lab = binary_dilation(skeleton, np.ones((3, 3), bool)) & skeleton
    rr, cc = np.nonzero(lab)
    keep = ((rr + cc) % spacing) == 0
    out = np.zeros_like(skeleton)
    out[rr[keep], cc[keep]] = True
    return out


def catalogue_dilation_dots(visible: np.ndarray, radius_px: int, spacing: int) -> np.ndarray:
    """Baseline B0: dots spaced along the *visible* catalogue dilated by ``radius_px``.

    This is the incumbent family that scored 0.26-0.2778 on the live board; it is the
    reference the funnel must beat.
    """
    zone = binary_dilation(visible, np.ones((2 * radius_px + 1, 2 * radius_px + 1), bool)) & ~visible
    return dot_spacing(zone, spacing)


def cover_greedy(q: np.ndarray, tau: float, candidate_mask: np.ndarray | None = None,
                 radius: float = 3.0, max_dots: int | None = None,
                 score: np.ndarray | None = None) -> np.ndarray:
    """Greedy kernel-coverage of the *estimated* fault set, minimising emitted mass.

    The estimated fault set is ``F = {x : q(x) >= tau}`` restricted to the decoded candidate
    geometry, where ``q`` is the calibrated per-cell fault probability.  Seeds are taken in
    descending ``score`` (default ``q``); a seed that is already covered by a placed dot is
    skipped, otherwise a dot is placed on it and every member of ``F`` within ``radius`` is
    marked covered.  Each dot is therefore one unit of mass that is known to be inside the
    300 m kernel of the model's own best estimate of a fault pixel — the low-mass cover the
    marginal-DTI arithmetic asks for (see the module docstring).
    """
    if candidate_mask is None:
        candidate_mask = np.ones(q.shape, bool)
    f_mask = (q >= tau) & candidate_mask & np.isfinite(q)
    rr, cc = np.nonzero(f_mask)
    if rr.size == 0:
        return np.zeros(q.shape, bool)
    s = q[rr, cc] if score is None else np.asarray(score, np.float64)[rr, cc]
    pts = np.stack([rr, cc], axis=1).astype(np.float64)
    tree = cKDTree(pts)
    order = np.argsort(-s, kind="stable")
    covered = np.zeros(rr.size, bool)
    dots = np.zeros(q.shape, bool)
    n = 0
    for i in order:
        if covered[i]:
            continue
        dots[rr[i], cc[i]] = True
        n += 1
        for j in tree.query_ball_point(pts[i], radius):
            covered[j] = True
        if max_dots is not None and n >= max_dots:
            break
    return dots


def random_control(active: np.ndarray, n: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rr, cc = np.nonzero(active)
    pick = rng.choice(rr.size, size=min(n, rr.size), replace=False)
    out = np.zeros(active.shape, bool)
    out[rr[pick], cc[pick]] = True
    return out
