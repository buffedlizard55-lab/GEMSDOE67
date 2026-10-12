"""Lane-67 geometry-aware decoding: orientation-aware NMS, hysteresis, along-strike tip extension.

The lane brief (Batra et al., CVPR 2019, doi:10.1109/CVPR.2019.01063, as the citation for
learning orientation jointly with segmentation to improve extracted line-network topology) asks
for decoding that respects connectivity rather than per-pixel classification. Three operations:

1. ``orientation_aware_nms``   suppress a candidate only if a *across-strike* neighbour is
   stronger; along-strike neighbours never suppress each other. This is the difference from
   isotropic NMS, which breaks traces into beads and truncates them at every curvature maximum.
2. ``hysteresis``              seed on high support, grow through low support (classic Canny
   hysteresis), so a trace survives a short gap in the physical signal.
3. ``extend_past_tips``        from a visible-trace tip, walk along the *predicted* orientation
   while predicted support persists, up to ``max_len`` cells. This is the mechanism that answers
   the published finding that mapped lengths come up short because tip zones fall below
   resolution (Southampton ePrints 76146; UCD Fault Analysis Group TSG-2008 abstract).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

# four axial bins: 0, 45, 90, 135 degrees. For each bin the *across-strike* offset pair is fixed.
# strike direction s = (-sin t, cos t); across-strike g = (cos t, sin t).
_BIN_ACROSS = {0: (0, 1), 1: (1, 1), 2: (1, 0), 3: (1, -1)}  # (dy, dx) integer across-strike step


def orientation_bins(cos2t: np.ndarray, sin2t: np.ndarray) -> np.ndarray:
    """Quantise an axial orientation field into 4 bins (0..3) of 45 degrees."""
    theta = 0.5 * np.arctan2(sin2t, cos2t)            # in (-pi/2, pi/2]
    b = np.floor((theta + np.pi / 4) / (np.pi / 4)).astype(np.int8) % 4
    return b


def orientation_aware_nms(p: np.ndarray, cos2t: np.ndarray, sin2t: np.ndarray,
                          reach: int = 1) -> np.ndarray:
    """Keep a cell only if no across-strike neighbour within ``reach`` has larger support."""
    p = np.asarray(p, np.float32)
    bins = orientation_bins(cos2t, sin2t)
    keep = np.ones(p.shape, bool)
    for b, (dy, dx) in _BIN_ACROSS.items():
        sel = bins == b
        if not sel.any():
            continue
        best = p.copy()
        for k in range(1, reach + 1):
            best = np.maximum(best, np.roll(np.roll(p, dy * k, axis=0), dx * k, axis=1))
            best = np.maximum(best, np.roll(np.roll(p, -dy * k, axis=0), -dx * k, axis=1))
        # strictly greater across-strike neighbour -> suppressed
        keep &= ~(sel & (best > p + 1e-9))
    return np.where(keep, p, 0.0).astype(np.float32)


def hysteresis(support: np.ndarray, t_hi: float, t_lo: float) -> np.ndarray:
    """Boolean network: 8-connected components of ``support >= t_lo`` containing a ``>= t_hi`` seed."""
    lo = support >= t_lo
    hi = support >= t_hi
    if not hi.any():
        return np.zeros(support.shape, bool)
    lab, n = ndimage.label(lo, structure=np.ones((3, 3), int))
    keep_ids = np.unique(lab[hi])
    keep_ids = keep_ids[keep_ids > 0]
    return np.isin(lab, keep_ids)


def _strike_step(cos2t: np.ndarray, sin2t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Integer along-strike step (dy, dx) per cell, from the axial orientation."""
    theta = 0.5 * np.arctan2(sin2t, cos2t)
    sx = -np.sin(theta)     # column step
    sy = np.cos(theta)      # row step
    dx = np.sign(np.where(np.abs(sx) >= np.abs(sy), sx, 0.0)).astype(np.int8)
    dy = np.sign(np.where(np.abs(sy) > np.abs(sx), sy, 0.0)).astype(np.int8)
    both = (dx != 0) & (dy != 0)
    # prefer the diagonal when the strike is close to 45 degrees, else the dominant axis
    dx = np.where(both & (np.abs(sx) < 0.9 * np.abs(sy)), 0, dx).astype(np.int8)
    dy = np.where(both & (np.abs(sy) < 0.9 * np.abs(sx)), 0, dy).astype(np.int8)
    zero = (dx == 0) & (dy == 0)
    dx = np.where(zero, 1, dx).astype(np.int8)
    return dy, dx


def extend_past_tips(support: np.ndarray, tips: np.ndarray, cos2t: np.ndarray, sin2t: np.ndarray,
                     max_len: int = 8, t_ext: float = 0.2, blocked: np.ndarray | None = None,
                     walk_support: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Walk away from visible tips along the predicted orientation while support persists.

    Returns ``(extended_mask, length_field)`` where ``length_field`` counts how many cells the
    walk travelled from a tip (0 where not reached). ``blocked`` cells (e.g. already-mapped
    traces) stop the walk, so an extension never doubles back onto the catalogue.
    """
    h, w = support.shape
    # the walk is allowed to travel on the *un-thinned* propensity field: NMS removes exactly the
    # off-ridge cells a tip extension has to cross, so testing the walk against the thinned field
    # would make the mechanism unfalsifiable-by-construction (measured: 0 extension cells).
    walk = support if walk_support is None else walk_support
    dy, dx = _strike_step(cos2t, sin2t)
    reached = np.zeros((h, w), bool)
    length = np.zeros((h, w), np.int16)
    blocked = np.zeros((h, w), bool) if blocked is None else blocked
    # seeds sit ON visible trace ends, which are themselves blocked for the walk; filtering the
    # seeds by `blocked` emptied the whole mechanism (measured: 0 extension cells, A2 == A1).
    ys, xs = np.nonzero(tips)
    for sign in (1, -1):
        cy, cx = ys.copy(), xs.copy()
        alive = np.ones(cy.shape, bool)
        for step in range(1, max_len + 1):
            if not alive.any():
                break
            ny = cy + sign * dy[cy, cx].astype(np.int32)
            nx = cx + sign * dx[cy, cx].astype(np.int32)
            ok = alive & (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
            ny = np.clip(ny, 0, h - 1); nx = np.clip(nx, 0, w - 1)
            ok &= ~blocked[ny, nx] & (walk[ny, nx] >= t_ext)
            reached[ny[ok], nx[ok]] = True
            length[ny[ok], nx[ok]] = np.maximum(length[ny[ok], nx[ok]], step)
            alive = ok
            cy, cx = ny, nx
    return reached, length


def decode(propensity: np.ndarray, cos2t: np.ndarray, sin2t: np.ndarray, tips: np.ndarray,
           t_hi: float, t_lo: float, nms_reach: int = 1, max_len: int = 8, t_ext: float = 0.2,
           blocked: np.ndarray | None = None, tip_weight: float = 0.25) -> dict:
    """Full geometry-aware decode; returns the intermediate surfaces for auditing."""
    p_nms = orientation_aware_nms(propensity, cos2t, sin2t, reach=nms_reach)
    net = hysteresis(p_nms, t_hi, t_lo)
    ext, ext_len = extend_past_tips(p_nms, tips, cos2t, sin2t, max_len=max_len, t_ext=t_ext,
                                    blocked=blocked, walk_support=propensity)
    # both terms are put on a comparable [0, 1] scale so the along-strike extension bonus can
    # actually compete with weak network ridges (it is lower-confidence evidence, not higher)
    nrm = float(np.percentile(p_nms[p_nms > 0], 99.9)) if (p_nms > 0).any() else 1.0
    score = p_nms / max(nrm, 1e-12) + tip_weight * ext_len.astype(np.float32) / max(max_len, 1)
    return {"p_nms": p_nms, "network": net, "extension": ext, "extension_len": ext_len,
            "score": np.where(net | ext, score, 0.0).astype(np.float32), "score_norm": nrm}
