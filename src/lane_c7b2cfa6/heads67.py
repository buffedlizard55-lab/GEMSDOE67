"""Lane-67 heads: axial-orientation (cos 2theta, sin 2theta) and tip/junction heatmap targets.

Both heads are *supervised inside the visible catalogue only*:

* orientation targets are defined on cells within ``ORI_RADIUS_PX`` (=3 px) of a visible trace,
  exactly as the lane brief prescribes. They are read off the structure tensor of the visible
  trace mask itself, so the target is the trace's own axial direction, not a geophysical proxy.
* tip targets are Gaussian blobs (sigma 1.5 px, inside the brief's 1-2 px band) centred on
  skeleton endpoints (1 neighbour) and junctions (>=3 neighbours) of the visible traces.

Every function here takes the *visible* mask as an argument so a holdout fold can pass only the
faults that fold is allowed to see. Nothing reads ``labels.tif`` directly.

Orientation convention: ``theta`` returned by :func:`lane_c7b2cfa6.features67.structure_tensor` is the
direction of maximum gradient (perpendicular to a line); the along-strike unit vector is
``s = (-sin theta, cos theta)`` in (x=column, y=row). Because the representation is axial
(period pi), ``cos 2theta``/``sin 2theta`` determine ``s`` up to sign, which is all a trace
extension needs.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

ORI_RADIUS_PX = 3
TIP_SIGMA_PX = 1.5

_SQ3 = np.ones((3, 3), dtype=int)


def _thin(mask: np.ndarray) -> np.ndarray:
    """One-pixel-wide skeleton of a binary trace mask (topological thinning)."""
    from skimage.morphology import thin

    return thin(np.asarray(mask, dtype=bool), max_num_iter=4000)


def neighbour_count(skel: np.ndarray) -> np.ndarray:
    """8-neighbour occupancy count of a skeleton raster."""
    return ndimage.convolve(skel.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - skel.astype(np.uint8)


def trace_orientation_targets(visible: np.ndarray) -> dict:
    """Axial orientation targets supervised within ``ORI_RADIUS_PX`` of visible traces.

    Returns dict with ``cos2t``, ``sin2t`` (float32, in [-1, 1]) and ``valid`` (bool).
    """
    v = np.asarray(visible, dtype=bool)
    if not v.any():
        z = np.zeros(v.shape, np.float32)
        return {"cos2t": z, "sin2t": z.copy(), "valid": np.zeros(v.shape, bool)}
    img = ndimage.binary_dilation(v, _SQ3, iterations=1).astype(np.float32)
    img = ndimage.gaussian_filter(img, 1.0, mode="nearest")
    gx = ndimage.gaussian_filter(img, 1.0, order=(0, 1), mode="nearest")
    gy = ndimage.gaussian_filter(img, 1.0, order=(1, 0), mode="nearest")
    del img
    jxx = ndimage.gaussian_filter(gx * gx, 1.0, mode="nearest")
    jyy = ndimage.gaussian_filter(gy * gy, 1.0, mode="nearest")
    jxy = ndimage.gaussian_filter(gx * gy, 1.0, mode="nearest")
    del gx, gy
    diff = jxx - jyy
    root = np.sqrt(np.maximum(0.25 * diff * diff + jxy * jxy, 0.0))
    ok = root > 1e-9
    cos2t = np.where(ok, diff / np.maximum(2.0 * root, 1e-12), 0.0).astype(np.float32)
    sin2t = np.where(ok, 2.0 * jxy / np.maximum(2.0 * root, 1e-12), 0.0).astype(np.float32)
    band = ndimage.distance_transform_edt(~v) <= ORI_RADIUS_PX
    valid = band & ok
    return {"cos2t": cos2t, "sin2t": sin2t, "valid": valid}


def tip_targets(visible: np.ndarray, sigma: float = TIP_SIGMA_PX) -> dict:
    """Tip/junction heatmap target: Gaussian blobs at skeleton endpoints and junctions."""
    v = np.asarray(visible, dtype=bool)
    z = np.zeros(v.shape, np.float32)
    if not v.any():
        return {"heat": z, "tips": np.zeros(v.shape, bool), "junctions": np.zeros(v.shape, bool),
                "skeleton": np.zeros(v.shape, bool)}
    skel = _thin(v)
    nc = neighbour_count(skel)
    tips = skel & (nc <= 1)
    junc = skel & (nc >= 3)
    seeds = (tips | junc).astype(np.float32)
    heat = ndimage.gaussian_filter(seeds, sigma, mode="constant").astype(np.float32)
    mx = float(heat.max())
    if mx > 0:
        heat /= mx
    return {"heat": heat, "tips": tips, "junctions": junc, "skeleton": skel}


def fit_head(X: np.ndarray, y: np.ndarray, alpha: float = 1.0):
    """Ridge fit of one head (cos2t, sin2t or tip heat) on the supplied samples."""
    from sklearn.linear_model import Ridge

    m = Ridge(alpha=alpha, fit_intercept=True)
    m.fit(X, y)
    return m
