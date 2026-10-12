"""Geometry-aware decoding: orientation-gated hysteresis, orientation-aware
non-maximum suppression, and tip extension along the predicted orientation.

The lane brief: "Decode with orientation-aware non-maximum suppression and
hysteresis.  Extend traces past mapped tips only along predicted orientation
where probability support persists."

Ablation contract (what experiment E1 runs instead): plain isotropic
hysteresis with no NMS and no tip extension -- the per-pixel classification
regime the brief contrasts against.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

_STRUCT3 = np.ones((3, 3), bool)


def axial_angle_deg(cos2: np.ndarray, sin2: np.ndarray) -> np.ndarray:
    """Axial angle in [0, 180) degrees from the doubled-angle representation."""
    return np.degrees(0.5 * np.arctan2(sin2, cos2)) % 180.0


def orientation_consistent(cos2: np.ndarray, sin2: np.ndarray, seeds: np.ndarray,
                           max_turn_deg: float = 45.0) -> np.ndarray:
    """Pixels whose axial orientation is within ``max_turn_deg`` of the nearest seed.

    |dtheta| <= max_turn  <=>  cos(2 dtheta) >= cos(2 max_turn), and
    cos(2 dtheta) = c1*c2 + s1*s2 for unit axial vectors.
    """
    if not seeds.any():
        return np.zeros(seeds.shape, bool)
    _, (iy, ix) = ndi.distance_transform_edt(~seeds, return_indices=True)
    c1 = cos2[iy, ix]
    s1 = sin2[iy, ix]
    dot = c1 * cos2 + s1 * sin2
    return dot >= np.cos(np.radians(2.0 * max_turn_deg))


def oriented_hysteresis(p: np.ndarray, cos2: np.ndarray, sin2: np.ndarray,
                        tau_hi: float, tau_lo: float,
                        max_turn_deg: float = 45.0,
                        orient_gate: bool = True) -> np.ndarray:
    """Hysteresis connected-component growth, optionally orientation-gated."""
    seeds = p >= tau_hi
    growable = p >= tau_lo
    if orient_gate:
        growable = growable & orientation_consistent(cos2, sin2, seeds, max_turn_deg)
    return ndi.binary_propagation(seeds, mask=growable, structure=_STRUCT3)


def oriented_nms(p: np.ndarray, cos2: np.ndarray, sin2: np.ndarray, support: np.ndarray,
                 halfwidth: int = 2) -> np.ndarray:
    """Thin ridges by keeping only local maxima along the predicted normal.

    For each pixel, sample ``p`` at +-1..+-halfwidth steps along the normal of
    the predicted axial orientation and suppress the pixel if any neighbour has
    strictly larger ``p``.  The normal is axial too, so sampling symmetric
    offsets removes any half-turn sign ambiguity.
    """
    H, W = p.shape
    theta = 0.5 * np.arctan2(sin2, cos2)
    ny = -np.sin(theta)      # normal of the ridge line
    nx = np.cos(theta)
    keep = support.copy()
    yy, xx = np.nonzero(support)
    if yy.size == 0:
        return keep
    best = p[yy, xx].copy()
    my_idx = yy * W + xx
    best_idx = my_idx.copy()      # row-major identity of the running winner
    for k in range(1, halfwidth + 1):
        for sign in (1.0, -1.0):
            # sample p bilinearly along the true normal so fractional offsets
            # do not collapse onto the same pixel at oblique orientations
            coords = np.stack([yy + sign * k * ny[yy, xx],
                               xx + sign * k * nx[yy, xx]])
            inside = ((coords[0] >= 0) & (coords[0] <= H - 1) &
                      (coords[1] >= 0) & (coords[1] <= W - 1))
            neigh = np.zeros(yy.size, np.float64)
            neigh[inside] = ndi.map_coordinates(
                p, coords[:, inside], order=1, mode="nearest")
            sy = np.clip(np.rint(coords[0]), 0, H - 1).astype(np.int64)
            sx = np.clip(np.rint(coords[1]), 0, W - 1).astype(np.int64)
            # rank neighbours by (value, row-major index) so exact ties keep
            # exactly one winner; the pixel itself competes with its own index
            better = inside & ((neigh > best) | ((neigh == best) &
                                                 ((sy * W + sx) < best_idx)))
            best = np.where(better, neigh, best)
            best_idx = np.where(better, sy * W + sx, best_idx)
    suppress = (best > p[yy, xx]) | ((best == p[yy, xx]) & (best_idx < my_idx))
    keep[yy[suppress], xx[suppress]] = False
    return keep


@dataclass
class DecodeResult:
    support: np.ndarray      # bool, decoded trace pixels (pre-emission)
    extended: np.ndarray     # bool, pixels added by tip extension
    n_tips_extended: int
    n_extension_px: int


def tip_points(support: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Endpoints of 8-connected trace pixels (exactly one trace neighbour)."""
    m = np.asarray(support, bool)
    n = ndi.convolve(m.astype(np.int16), np.ones((3, 3), np.int16),
                     mode="constant") - m.astype(np.int16)
    tips = m & (n == 1)
    return np.nonzero(tips)


def extend_tips(support: np.ndarray, p: np.ndarray, cos2: np.ndarray, sin2: np.ndarray,
                tip_heat: np.ndarray, *, max_len: int = 6, tau_ext: float = 0.30,
                tau_tip: float = 0.55, max_turn_deg: float = 60.0) -> DecodeResult:
    """March past each decoded tip along the outward trace direction.

    A step is accepted while segmentation support persists (``p >= tau_ext``)
    or the tip head fires (``tip_heat >= tau_tip`` and ``p >= tau_ext / 2``),
    and while the heading stays within ``max_turn_deg`` of the predicted axial
    orientation (geometry-aware continuation).  At most ``max_len`` pixels are
    added per tip (6 px = 600 m: published tip under-mapping runs to about
    500 m per fault in one seismic array and 100-200 m of DEM truncation in
    another rift -- see docs/research.html).
    """
    sup = support.copy()
    ext = np.zeros(support.shape, bool)
    H, W = support.shape
    ty, tx = tip_points(support)
    order = np.lexsort((tx, ty))
    n_tips = 0
    for idx in order:
        y0, x0 = int(ty[idx]), int(tx[idx])
        nb = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny_, nx_ = y0 + dy, x0 + dx
                if 0 <= ny_ < H and 0 <= nx_ < W and sup[ny_, nx_]:
                    nb.append((ny_, nx_))
        if not nb:
            continue
        # outward heading: away from the mean of the trace-side neighbours
        py = y0 - float(np.mean([q[0] for q in nb]))
        px = x0 - float(np.mean([q[1] for q in nb]))
        nrm = float(np.hypot(py, px))
        if nrm < 1e-9:
            continue
        dyv, dxv = py / nrm, px / nrm
        y, x = float(y0), float(x0)
        added = 0
        for _ in range(max_len):
            y += dyv
            x += dxv
            yi, xi = int(round(y)), int(round(x))
            if not (0 <= yi < H and 0 <= xi < W):
                break
            if sup[yi, xi] and not ext[yi, xi]:
                break   # collided with existing trace
            support_ok = (p[yi, xi] >= tau_ext) or (
                tip_heat[yi, xi] >= tau_tip and p[yi, xi] >= tau_ext / 2.0)
            if not support_ok:
                break
            # axial continuity: heading vs predicted axis at the new pixel
            h2x = (dxv * dxv - dyv * dyv)
            h2y = (2.0 * dxv * dyv)
            if h2x * float(cos2[yi, xi]) + h2y * float(sin2[yi, xi]) < np.cos(np.radians(2.0 * max_turn_deg)):
                break
            sup[yi, xi] = True
            ext[yi, xi] = True
            added += 1
        if added:
            n_tips += 1
    return DecodeResult(support=sup, extended=ext, n_tips_extended=n_tips,
                        n_extension_px=int(ext.sum()))


def flank_prune(candidates: np.ndarray, visible_catalogue: np.ndarray,
                protect: np.ndarray | None = None, flank_px: float = 2.0) -> np.ndarray:
    """Drop candidate pixels within ``flank_px`` of the mapped catalogue.

    The h33 flank-prune lesson (GEMSDOE32): marginal dots hugging mapped
    faults carry little off-catalogue credit.  Tip-extension pixels are
    exempt: the lane's whole point is to probe past mapped tips, and the
    hide-and-recover buffer guarantees withheld truth sits >= 4 px from the
    visible catalogue, so only the outer extension can reach it.
    """
    dist = ndi.distance_transform_edt(~np.asarray(visible_catalogue, bool))
    prot = np.asarray(protect, bool) if protect is not None else np.zeros(candidates.shape, bool)
    return candidates & ((dist > flank_px) | prot)
