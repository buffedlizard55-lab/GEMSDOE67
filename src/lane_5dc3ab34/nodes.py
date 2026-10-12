"""Node selection for the dotted emission.

Two selection rules from the lane brief: "Select nodes by calibrated greedy
marginal-DTI selection or 4-5 px spacing."

* ``greedy_nodes`` wraps the shared template's ``gems57.emit.greedy_allocate``
  (exact marginal-DTI bar: a dot enters only while it raises the surrogate
  DTI, with self-credit clipped to 1 -- see IR-57-KCLIP-01 in the template).
* ``spacing_nodes`` walks a priority-ordered candidate list and drops a node
  every ``spacing`` pixels -- the d2.8-style rule that the family's score
  ladder (0.1922 solid -> 0.2477 d1.5 -> 0.2600 d2.8) showed to be near the
  metric's break-even density.

Allocation mass is then budgeted by exact marginal-DTI recomputation against
the fold truth for holdout scoring only; live emission uses the greedy bar with
an externally chosen ``k_truth`` prior (never the hidden truth).
"""

from __future__ import annotations

import importlib

import numpy as np
from scipy import ndimage as ndi


def _import_emit():
    """Import the vendored template emitter without a private copy."""
    return importlib.import_module("gems57.emit")


def greedy_nodes(p_alloc: np.ndarray, allowed: np.ndarray, k_truth: float, *,
                 floor: float = 0.02, max_dots: int = 200_000,
                 candidate_cap: int = 400_000):
    """Greedy marginal-DTI dot allocation on the surrogate field ``p_alloc``."""
    emit = _import_emit()
    return emit.greedy_allocate(p_alloc, allowed, k_truth, floor=floor,
                                max_dots=max_dots, candidate_cap=candidate_cap)


def spacing_nodes(candidates: np.ndarray, priority: np.ndarray, *,
                  spacing: float = 3.0) -> np.ndarray:
    """Priority walk with an exclusion disk of radius ``spacing`` (px)."""
    cand = np.asarray(candidates, bool)
    ys, xs = np.nonzero(cand)
    if ys.size == 0:
        return np.zeros(cand.shape, bool)
    order = np.argsort(-priority[ys, xs], kind="stable")
    ys, xs = ys[order], xs[order]
    out = np.zeros(cand.shape, bool)
    H, W = cand.shape
    r = int(np.ceil(spacing))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disk = (yy * yy + xx * xx) <= spacing * spacing
    taken = np.zeros(cand.shape, bool)
    for y, x in zip(ys, xs):
        if taken[y, x]:
            continue
        out[y, x] = True
        y0, y1 = max(0, y - r), min(H, y + r + 1)
        x0, x1 = max(0, x - r), min(W, x + r + 1)
        sub = disk[y0 - (y - r):y0 - (y - r) + (y1 - y0),
                   x0 - (x - r):x0 - (x - r) + (x1 - x0)]
        taken[y0:y1, x0:x1] |= sub
    return out


def allocation_field(p: np.ndarray, support: np.ndarray, *, sigma: float = 1.5) -> np.ndarray:
    """Scatter-smoothed evidence restricted to decoded trace support.

    The hidden truth is scattered around the mapped/evidential surface at the
    pixel scale (GEMSDOE32's live-mirror estimate: ~1.85 px), so the
    allocation surrogate is the trace evidence blurred by a comparable width,
    normalised to [0, 1].  Restriction to ``support`` keeps the mass on
    decoded geometry.
    """
    base = (np.asarray(p, np.float32) * np.asarray(support, np.float32))
    sm = ndi.gaussian_filter(base, sigma, mode="nearest")
    mx = float(sm.max())
    if mx > 0:
        sm = sm / mx
    return sm.astype(np.float32)
