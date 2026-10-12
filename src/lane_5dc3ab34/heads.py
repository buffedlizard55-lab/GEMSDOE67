"""Three stacked heads for the orientation/tip lane: segmentation, axial
orientation, and tip/junction heat.

Motivation (Batra et al., CVPR 2019, doi:10.1109/CVPR.2019.01063): learning
orientation jointly with segmentation in stacked multi-branch heads improves
the topology of extracted line networks.  Per-pixel classification alone
ignores connectivity; the two auxiliary heads teach the decoder where lines
run and where they stop.

Supervision contract (parallel-run protocol rule 2):

* every catalogue-derived target is computed from the **visible** faults of the
  current hide-and-recover fold only;
* the segmentation positives are the 3-px band around those visible traces and
  negatives are >= 10 px away from any of them;
* the orientation target is the axial trace direction (cos 2t, sin 2t) of the
  visible traces, valid within 3 px of them (the lane brief's supervision
  window) -- undirected faults, so the doubled-angle representation;
* the tip target is a Gaussian (sigma = 1.5 px, inside the brief's 1-2 px
  band) on visible-trace endpoints and junctions.

The heads are scikit-learn linear models: with one raster and no published
hidden truth, "learning" means calibrating the mapping from the geophysical
fabric to catalogue geometry, not deep training.  That mapping is exactly what
must transfer to unmapped faults if the lane's hypothesis holds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from sklearn.linear_model import LogisticRegression, Ridge

from . import features as featmod

TIP_SIGMA = 1.5
AXIAL_WINDOW = 3        # px, supervision window around traces
POS_BAND_PX = 3
NEG_FAR_PX = 10

_STRUCT3 = np.ones((3, 3), bool)


def endpoint_tips(mask: np.ndarray) -> np.ndarray:
    """Trace pixels with exactly one 8-connected trace neighbour (line tips)."""
    m = np.asarray(mask, bool)
    n = ndi.convolve(m.astype(np.int16), np.ones((3, 3), np.int16),
                     mode="constant") - m.astype(np.int16)
    return m & (n == 1)


def junction_pixels(mask: np.ndarray) -> np.ndarray:
    """Trace pixels with >= 3 8-connected trace neighbours (junctions)."""
    m = np.asarray(mask, bool)
    n = ndi.convolve(m.astype(np.int16), np.ones((3, 3), np.int16),
                     mode="constant") - m.astype(np.int16)
    return m & (n >= 3)


def axial_targets(mask: np.ndarray, sigma: float = 1.5):
    """(cos 2t, sin 2t, coherence, near) of the visible trace geometry.

    The local trace direction comes from the structure tensor of the binary
    trace mask (ridge-line orientation of the mask itself), which is stable for
    curved traces and needs no vectorisation.  ``near`` is the 3-px supervision
    window around the trace (the brief's label band).
    """
    m = np.asarray(mask, bool).astype(np.float32)
    gy, gx = np.gradient(ndi.gaussian_filter(m, sigma, mode="nearest"))
    coh, c2, s2 = featmod.structure_tensor(gy, gx, sigma=sigma)
    near = ndi.distance_transform_edt(~np.asarray(mask, bool)) <= AXIAL_WINDOW
    return c2, s2, coh, near


def tip_heatmap(mask: np.ndarray, sigma: float = TIP_SIGMA) -> np.ndarray:
    """Gaussian blobs at endpoints and junctions of the visible traces."""
    tips = endpoint_tips(mask) | junction_pixels(mask)
    if not tips.any():
        return np.zeros(mask.shape, np.float32)
    heat = ndi.gaussian_filter(tips.astype(np.float32), sigma, mode="constant")
    peak = float(heat.max())
    return (heat / peak).astype(np.float32) if peak > 0 else heat.astype(np.float32)


@dataclass
class Heads:
    seg: LogisticRegression
    orient: Ridge
    tip: Ridge
    seg_features: list[str]
    orient_features: list[str]
    seg_scaler: tuple[np.ndarray, np.ndarray]    # (mean, std)
    orient_scaler: tuple[np.ndarray, np.ndarray]
    tip_scaler: tuple[np.ndarray, np.ndarray]
    fit_receipt: dict


def _standardise_fit(X: np.ndarray) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray]]:
    mu = X.mean(axis=0)
    sd = X.std(axis=0) + 1e-6
    return (X - mu) / sd, (mu, sd)


def _standardise_apply(X: np.ndarray, scaler: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    mu, sd = scaler
    return (X - mu) / sd


def fit_heads(cache: featmod.FeatureCache, visible: np.ndarray, *,
              seed: int = 67001, max_samples: int = 240_000) -> Heads:
    """Fit the three heads on the fold's visible catalogue only."""
    rng = np.random.default_rng(seed)
    H, W = cache.shape
    vis = np.asarray(visible, bool)
    if not vis.any():
        raise ValueError("visible catalogue is empty")

    dist_vis = ndi.distance_transform_edt(~vis)
    pos = (dist_vis <= POS_BAND_PX) & cache.valid
    neg = (dist_vis >= NEG_FAR_PX) & cache.valid
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        raise ValueError("degenerate positive/negative sets")

    pos_y, pos_x = np.nonzero(pos)
    neg_y, neg_x = np.nonzero(neg)
    take_neg = min(neg_y.size, max(3 * pos_y.size, 20_000))
    sel = rng.choice(neg_y.size, size=take_neg, replace=False)
    neg_y, neg_x = neg_y[sel], neg_x[sel]

    ys = np.concatenate([pos_y, neg_y])
    xs = np.concatenate([pos_x, neg_x])
    y = np.concatenate([np.ones(pos_y.size), np.zeros(neg_y.size)])

    seg_names = [n for n in cache.layers]
    Xs = cache.sample(ys, xs)
    Xs_std, seg_scaler = _standardise_fit(Xs)
    keep = min(max_samples, Xs_std.shape[0])
    if keep < Xs_std.shape[0]:
        pick = rng.choice(Xs_std.shape[0], size=keep, replace=False)
        Xs_fit, y_fit = Xs_std[pick], y[pick]
    else:
        Xs_fit, y_fit = Xs_std, y
    seg = LogisticRegression(C=1.0, max_iter=300, solver="lbfgs")
    seg.fit(Xs_fit, y_fit)

    # ---- orientation head: axial targets within 3 px of visible traces ----
    c2, s2, coh, near = axial_targets(vis)
    cand = near & cache.valid & (coh > 0.05)
    cy, cx = np.nonzero(cand)
    if cy.size > 200_000:
        pick = rng.choice(cy.size, size=200_000, replace=False)
        cy, cx = cy[pick], cx[pick]
    Xo = cache.sample(cy, cx)
    # add the geometry-independent channels: gradient of the seg score not yet
    # available here; the head sees the same geophysical layers plus coherence
    Xo_std, orient_scaler = _standardise_fit(Xo)
    Yo = np.stack([c2[cy, cx], s2[cy, cx]], axis=1)
    Wo = coh[cy, cx].astype(np.float64) + 0.05
    orient = Ridge(alpha=10.0)
    orient.fit(Xo_std, Yo, sample_weight=Wo)

    # ---- tip head: Gaussian heat at endpoints and junctions ----
    heat = tip_heatmap(vis)
    # regression everywhere inside the footprint is wasteful; the decoder only
    # consults the head near candidate traces, but the head must still fire on
    # isolated lineament endings, so sample globally with a tip-focused oversample
    tip_mask = heat > 0.05
    ty, tx = np.nonzero(tip_mask & cache.valid)
    by, bx = np.nonzero(cache.valid & ~tip_mask)
    take_b = min(by.size, max(6 * max(ty.size, 1), 20_000))
    sel = rng.choice(by.size, size=take_b, replace=False)
    by, bx = by[sel], bx[sel]
    yst = np.concatenate([ty, by])
    xst = np.concatenate([tx, bx])
    yt = heat[yst, xst]
    Xt = cache.sample(yst, xst)
    Xt_std, tip_scaler = _standardise_fit(Xt)
    tip = Ridge(alpha=10.0)
    tip.fit(Xt_std, yt)

    receipt = dict(
        n_pos_pixels=int(pos_y.size), n_neg_pixels=int(neg_y.size),
        seg_samples=int(Xs_fit.shape[0]), orient_samples=int(cy.size),
        tip_samples=int(yst.size), tip_target_pixels=int(ty.size),
        tip_sigma=TIP_SIGMA, axial_window_px=AXIAL_WINDOW,
        pos_band_px=POS_BAND_PX, neg_far_px=NEG_FAR_PX, seed=seed,
    )
    return Heads(seg=seg, orient=orient, tip=tip, seg_features=seg_names,
                 orient_features=list(cache.layers), seg_scaler=seg_scaler,
                 orient_scaler=orient_scaler, tip_scaler=tip_scaler,
                 fit_receipt=receipt)


@dataclass
class Predictions:
    p: np.ndarray            # segmentation probability, float32
    cos2: np.ndarray         # axial orientation field
    sin2: np.ndarray
    tip: np.ndarray          # tip/junction heat in [0, 1]
    orient_conf: np.ndarray  # normalised orientation-vector magnitude


def predict_block(cache: featmod.FeatureCache, heads: Heads,
                  row0: int, row1: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Predict all heads for one row block.  Returns p, cos2, sin2, tip, conf."""
    X = cache.block(row0, row1)                      # (L, h, W)
    L, h, W = X.shape
    flat = X.reshape(L, -1).T                        # (h*W, L)
    ps = heads.seg.predict_proba(
        _standardise_apply(flat, heads.seg_scaler))[:, 1].astype(np.float32)
    o = heads.orient.predict(_standardise_apply(flat, heads.orient_scaler))
    t = heads.tip.predict(_standardise_apply(flat, heads.tip_scaler)).astype(np.float32)
    p = ps.reshape(h, W)
    c2 = o[:, 0].reshape(h, W).astype(np.float32)
    s2 = o[:, 1].reshape(h, W).astype(np.float32)
    tip = np.clip(t.reshape(h, W), 0.0, 1.0)
    conf = np.sqrt(c2 * c2 + s2 * s2).astype(np.float32)
    # renormalise the axial vector to unit length (direction only)
    mag = np.maximum(conf, 1e-6)
    c2 = c2 / mag
    s2 = s2 / mag
    return p, c2, s2, tip, conf


def predict_full(cache: featmod.FeatureCache, heads: Heads,
                 block_rows: int = 256) -> Predictions:
    H, W = cache.shape
    p = np.zeros((H, W), np.float32)
    cos2 = np.zeros((H, W), np.float32)
    sin2 = np.zeros((H, W), np.float32)
    tip = np.zeros((H, W), np.float32)
    conf = np.zeros((H, W), np.float32)
    for r0 in range(0, H, block_rows):
        r1 = min(H, r0 + block_rows)
        pb, c2b, s2b, tb, cfb = predict_block(cache, heads, r0, r1)
        p[r0:r1] = pb
        cos2[r0:r1] = c2b
        sin2[r0:r1] = s2b
        tip[r0:r1] = tb
        conf[r0:r1] = cfb
    return Predictions(p=p, cos2=cos2, sin2=sin2, tip=tip, orient_conf=conf)
