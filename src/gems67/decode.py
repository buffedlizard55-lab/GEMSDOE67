"""Geometry-aware decoding: axial non-maximum suppression, hysteresis, tip relay.

Implements the lane's decoder (see docs/research/):

1.  **Axial NMS** — suppress every pixel whose evidence is below the evidence found by
    bilinear sampling at +/-1 px along the *gradient* direction of the structure tensor,
    i.e. suppression across the line, never along it.  This is what keeps a thin trace thin
    instead of turning it into a ridge band.
2.  **Hysteresis** — keep connected components of ``evidence >= low`` that contain at least
    one pixel with ``evidence >= high`` (Canny-style, applied to the lineament evidence field).
3.  **Tip / junction head** — endpoints (1 neighbour) and junctions (>= 3 neighbours) of the
    skeleton of the *visible* trace set, blurred with a Gaussian of sigma = 1.5 px, used as
    the supervised target for the tip head.
4.  **Tip relay** — from every endpoint of the decoded skeleton, walk along the local axial
    orientation while evidence stays above ``low_relay``; this is the "extend traces past
    mapped tips only along predicted orientation where probability support persists" step.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_dilation, gaussian_filter, label

from .grid import KERNEL_RADIUS_PX

EPS = 1e-9


def _shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Integer shift of ``a`` by (dy, dx) with zero fill (used for comparisons only)."""
    out = np.zeros_like(a)
    h, w = a.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = a[max(0, -dy):min(h, h - dy), max(0, -dx):min(w, w - dx)]
    return out


#: Number of discrete axial directions used by the non-maximum suppression.
N_DIRS = 16


def nms_axial(ev: np.ndarray, cos2t: np.ndarray, sin2t: np.ndarray,
              step: float = 1.0, n_dirs: int = N_DIRS) -> np.ndarray:
    """Keep pixels that are axial local maxima *across* the line.

    The structure tensor's dominant orientation is the gradient direction (normal to a line),
    so suppression runs along theta, never along the trace.  Orientation is quantised to
    ``n_dirs`` axial directions (11.25 deg at the default, i.e. <= 0.1 px of positional error
    at one step), which keeps the comparison on the lattice and out of coordinate grids.
    Ties resolve asymmetrically, which yields a one-pixel-wide skeleton.
    """
    ev = np.asarray(ev, dtype=np.float32)
    theta = 0.5 * np.arctan2(np.asarray(sin2t, np.float64), np.asarray(cos2t, np.float64))
    theta = np.mod(theta, np.pi)
    bins = np.clip((theta / (np.pi / n_dirs)).astype(np.int16), 0, n_dirs - 1)
    keep = np.zeros(ev.shape, bool)
    for k in range(n_dirs):
        th = (k + 0.5) * np.pi / n_dirs
        dy = int(round(step * np.cos(th)))
        dx = int(round(-step * np.sin(th)))
        m = bins == k
        if not m.any():
            continue
        a = _shift(ev, dy, dx)
        b = _shift(ev, -dy, -dx)
        keep[m] = (ev[m] > a[m]) & (ev[m] >= b[m])
    return keep


def hysteresis(ev: np.ndarray, high: float, low: float) -> np.ndarray:
    """Canny-style hysteresis on a scalar evidence field."""
    strong = ev >= high
    weak = ev >= low
    lab, n = label(weak, structure=np.ones((3, 3), int))
    if n == 0:
        return np.zeros_like(weak)
    keep_ids = np.unique(lab[strong])
    keep_ids = keep_ids[keep_ids > 0]
    out = np.isin(lab, keep_ids)
    return out


def skeleton_endpoints_junctions(skel: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Endpoints (1 neighbour) and junctions (>= 3 neighbours) of a binary skeleton."""
    from scipy.ndimage import convolve

    k = np.ones((3, 3), np.int8)
    k[1, 1] = 0
    ncount = convolve(skel.astype(np.int8), k, mode="constant", cval=0)
    endpoints = skel & (ncount == 1)
    junctions = skel & (ncount >= 3)
    return endpoints, junctions


def tip_target(catalogue_mask: np.ndarray, sigma: float = 1.5) -> tuple[np.ndarray, np.ndarray]:
    """Supervised tip target: Gaussian(sigma) blobs at skeleton endpoints and junctions."""
    from skimage.morphology import skeletonize

    skel = skeletonize(catalogue_mask)
    ep, jn = skeleton_endpoints_junctions(skel)
    seed = (ep | jn).astype(np.float32)
    tgt = gaussian_filter(seed, sigma, mode="constant")
    m = float(tgt.max())
    if m > 0:
        tgt /= m
    return tgt.astype(np.float32), skel


def tip_relay(mask: np.ndarray, ev: np.ndarray, cos2t: np.ndarray, sin2t: np.ndarray,
              low_relay: float, max_steps: int = 8) -> np.ndarray:
    """Walk from every endpoint along the local axial orientation while evidence persists.

    The walk direction is the *line* direction, i.e. perpendicular to the structure-tensor
    gradient: (uy, ux) = (cos theta, -sin theta).  Each step moves one pixel to the nearest
    lattice point, which keeps the relay exactly on the 100 m grid and inside the footprint.
    """
    out = mask.copy()
    h, w = out.shape
    theta = 0.5 * np.arctan2(np.asarray(sin2t, np.float64), np.asarray(cos2t, np.float64))
    for _ in range(max_steps):
        ep, _ = skeleton_endpoints_junctions(out)
        rr, cc = np.nonzero(ep)
        if rr.size == 0:
            break
        added = 0
        for r0, c0 in zip(rr, cc):
            th = theta[r0, c0]
            for sgn in (+1.0, -1.0):
                uy = np.cos(th) * sgn
                ux = -np.sin(th) * sgn
                nr = int(round(r0 + uy))
                nc = int(round(c0 + ux))
                if nr == r0 and nc == c0:
                    continue
                if nr < 0 or nc < 0 or nr >= h or nc >= w:
                    continue
                if out[nr, nc] or ev[nr, nc] < low_relay:
                    continue
                out[nr, nc] = True
                added += 1
                break
        if added == 0:
            break
    return out


def decode(ev: np.ndarray, cos2t: np.ndarray, sin2t: np.ndarray, high_q: float, low_q: float,
           search: np.ndarray | None = None, relay_votes: bool = True,
           relay_steps: int = 8) -> dict:
    """Full decode at quantile thresholds of the evidence field.

    ``search`` restricts both the quantiles *and* the report to the pixels the emitter is
    allowed to touch (the fold's active domain), so a fold never sees statistics it is not
    allowed to use.  Returns the thinned skeleton, the hysteresis support and the relayed
    candidate set (which is what the greedy selection consumes).
    """
    ev = np.asarray(ev, dtype=np.float32)
    if search is None:
        search = np.isfinite(ev)
    vals = ev[search & np.isfinite(ev)]
    hi = float(np.quantile(vals, high_q))
    lo = float(np.quantile(vals, low_q))
    thin = nms_axial(ev, cos2t, sin2t) & np.isfinite(ev)
    strong = thin & (ev >= hi)
    hyst = hysteresis(np.where(thin, ev, 0.0), hi, lo)
    skel = thin & hyst
    if relay_votes:
        # the acceptance test uses the *raw* evidence field (the thin field is zero off-ridge,
        # so testing against it would make the relay a no-op — that bug is recorded in
        # docs/run-card.json as IR-67-02)
        relayed = tip_relay(skel, ev, cos2t, sin2t, lo, max_steps=relay_steps)
        candidates = relayed & np.isfinite(ev)
    else:
        relayed = skel
        candidates = skel
    return dict(high=hi, low=lo, thin=thin, strong=strong, hyst=hyst, skel=skel,
                relayed=relayed, candidates=candidates)
