"""Catalogue-supervised heads: the axial orientation head and the tip/junction head.

Supervision scope (lane text)
-----------------------------
* **Orientation head** -- ``(cos 2theta, sin 2theta)`` regressed from the local
  per-band axial descriptors, with the training pixels restricted to within
  ``SUPERVISION_RADIUS_PX = 3`` of catalogue traces.  Undirected faults are handled
  by the axial frame, so a trace and its reverse give the same target.
* **Tip/junction head** -- a heatmap target built as a Gaussian
  (``TIP_SIGMA_PX = 1.5``, inside the lane's 1-2 px band) centred on the endpoints
  and junctions of the *vector* catalogue, regressed from the same descriptors plus
  the aggregate evidence.

Both heads are fitted only on the **visible** catalogue of whichever holdout fold
is being scored, so no head ever sees withheld truth.  The fitted models are
closed-form ridge solutions (no iterative solver, no random seed).
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

SUPERVISION_RADIUS_PX = 3.0
TIP_SIGMA_PX = 1.5
RIDGE_LAMBDA = 1.0


# --------------------------------------------------------------------------- #
# vector catalogue -> polylines, tips, junctions
# --------------------------------------------------------------------------- #
class TraceGraph:
    """Undirected planar graph of the catalogue trace segments, on the pixel grid.

    ``segments`` is an ``(n, 4)`` float64 array of ``(x0, y0, x1, y1)`` in map
    units (metres, EPSG:32611), exactly as published in the competition's vector
    label file.  Vertices are merged at ``vertex_tol_m`` before degrees are
    counted, so sub-pixel endpoint duplication does not manufacture junctions.
    """

    def __init__(self, segments: np.ndarray, transform, shape: tuple[int, int],
                 vertex_tol_m: float = 1.0):
        self.segments = np.asarray(segments, np.float64)
        if self.segments.ndim != 2 or self.segments.shape[1] != 4:
            raise ValueError("segments must be an (n, 4) array of x0, y0, x1, y1")
        self.transform = transform
        self.shape = tuple(shape)
        self.vertex_tol_m = float(vertex_tol_m)
        self.vertices, self.vertex_degree = self._build_vertices()
        self.tip_vertices = self.vertices[self.vertex_degree == 1]
        self.junction_vertices = self.vertices[self.vertex_degree >= 3]

    def _build_vertices(self):
        pts = np.concatenate([self.segments[:, 0:2], self.segments[:, 2:4]], axis=0)
        # quantise to the merge tolerance, then count occurrences
        q = np.round(pts / self.vertex_tol_m).astype(np.int64)
        _, inverse, counts = np.unique(q, axis=0, return_inverse=True, return_counts=True)
        sums = np.zeros((counts.size, 2), np.float64)
        np.add.at(sums, inverse.ravel(), pts)
        verts = sums / counts[:, None]
        return verts, counts

    def map_to_pixel(self, xy: np.ndarray) -> np.ndarray:
        """``(n, 2)`` map coordinates -> ``(n, 2)`` integer ``(row, col)`` indices."""
        inv = ~self.transform
        cols, rows = inv * (xy[:, 0], xy[:, 1])
        return np.stack([np.rint(np.asarray(rows)), np.rint(np.asarray(cols))], axis=1).astype(np.int64)

    def tip_mask(self, radius_px: float = TIP_SIGMA_PX, which: str = "all") -> np.ndarray:
        """Gaussian-sigma heatmap of tips (``which='tip'``), junctions or both."""
        if which not in {"all", "tip", "junction"}:
            raise ValueError("which must be 'all', 'tip' or 'junction'")
        pts = []
        if which in {"all", "tip"}:
            pts.append(self.tip_vertices)
        if which in {"all", "junction"}:
            pts.append(self.junction_vertices)
        pts = np.concatenate(pts, axis=0) if pts and len(pts[0]) else np.zeros((0, 2))
        out = np.zeros(self.shape, np.float32)
        if pts.size == 0:
            return out
        rc = self.map_to_pixel(pts)
        ok = ((rc[:, 0] >= 0) & (rc[:, 0] < self.shape[0])
              & (rc[:, 1] >= 0) & (rc[:, 1] < self.shape[1]))
        rc = rc[ok]
        if rc.size == 0:
            return out
        seeds = np.zeros(self.shape, np.float32)
        seeds[rc[:, 0], rc[:, 1]] = 1.0
        return ndi.gaussian_filter(seeds, radius_px, mode="constant", truncate=3.0).astype(np.float32)

    def rasterize(self, shape: tuple[int, int] | None = None) -> np.ndarray:
        """Rasterise every segment as 1-px cells (Bresenham-like supersampling).

        Used only to verify that the published vector file and the published
        raster label agree; it is never an input to a head.
        """
        shape = self.shape if shape is None else tuple(shape)
        out = np.zeros(shape, bool)
        inv = ~self.transform
        x0, y0, x1, y1 = (self.segments[:, 0], self.segments[:, 1],
                          self.segments[:, 2], self.segments[:, 3])
        length_px = np.hypot(x1 - x0, y1 - y0) / abs(self.transform.a)
        n = np.maximum(2, np.ceil(length_px * 2.0).astype(np.int64))
        total = int(n.sum())
        if total > 40_000_000:
            raise ValueError("rasterisation would exceed the memory guard")
        seg_id = np.repeat(np.arange(len(n)), n)
        t = (np.arange(total) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
        x = x0[seg_id] + t * (x1[seg_id] - x0[seg_id])
        y = y0[seg_id] + t * (y1[seg_id] - y0[seg_id])
        c, r = inv * (x, y)
        rr = np.rint(np.asarray(r)).astype(np.int64)
        cc = np.rint(np.asarray(c)).astype(np.int64)
        ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
        out[rr[ok], cc[ok]] = True
        return out


def load_trace_graph(csv_path: str | Path, transform, shape: tuple[int, int],
                     vertex_tol_m: float = 1.0) -> TraceGraph:
    """Read the published trace-segment CSV (``record_id,x0,y0,x1,y1,...``)."""
    xs0, ys0, xs1, ys1 = [], [], [], []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            xs0.append(float(row["x0"])); ys0.append(float(row["y0"]))
            xs1.append(float(row["x1"])); ys1.append(float(row["y1"]))
    seg = np.stack([xs0, ys0, xs1, ys1], axis=1)
    return TraceGraph(seg, transform, shape, vertex_tol_m=vertex_tol_m)


def trace_frame(trace_mask: np.ndarray, smooth_px: float = 2.0):
    """Axial tangent frame of a trace raster (truth for the orientation head).

    Same convention as :func:`lane_ef0d41a0.fields.axial_frame`.  The frame is *unit-norm
    wherever it is defined* but the tensor is smoothed, so it decays over a few
    pixels rather than stopping at the trace edge; the returned ``support`` is the
    1-px dilation of the mask and marks where supervision is allowed.
    """
    m = np.asarray(trace_mask, np.float32)
    gy, gx = np.gradient(ndi.gaussian_filter(m, 1.0, mode="constant"))
    jyy = ndi.gaussian_filter((gy * gy).astype(np.float32), smooth_px, mode="constant")
    jxx = ndi.gaussian_filter((gx * gx).astype(np.float32), smooth_px, mode="constant")
    jyx = ndi.gaussian_filter((gy * gx).astype(np.float32), smooth_px, mode="constant")
    diff = jyy.astype(np.float64) - jxx.astype(np.float64)
    d = np.sqrt(diff ** 2 + 4.0 * jyx.astype(np.float64) ** 2)
    cos2 = np.divide(diff, d, out=np.zeros_like(d), where=d > 1e-30).astype(np.float32)
    sin2 = np.divide(-2.0 * jyx.astype(np.float64), d, out=np.zeros_like(d),
                     where=d > 1e-30).astype(np.float32)
    support = ndi.binary_dilation(m > 0, np.ones((3, 3), bool), iterations=1)
    return cos2, sin2, support


# --------------------------------------------------------------------------- #
# sampling / fitting
# --------------------------------------------------------------------------- #
def supervision_pixels(mask: np.ndarray, radius_px: float = SUPERVISION_RADIUS_PX,
                       rng: np.random.Generator | None = None,
                       max_pixels: int = 200_000) -> np.ndarray:
    """Index array of pixels within ``radius_px`` of ``mask`` (optionally capped)."""
    near = ndi.distance_transform_edt(~np.asarray(mask, bool)) <= radius_px
    ys, xs = np.nonzero(near)
    if ys.size == 0:
        raise ValueError("no supervision pixels: the mask is empty")
    if ys.size > max_pixels:
        rng = np.random.default_rng(0) if rng is None else rng
        pick = rng.choice(ys.size, size=max_pixels, replace=False)
        ys, xs = ys[pick], xs[pick]
    return np.stack([ys, xs], axis=1)


def design_matrix(stack, idx: np.ndarray, extra: np.ndarray | None = None,
                  extra_scale: float | None = None) -> np.ndarray:
    """Stream the sampled design matrix: ``[wcos2_0, wsin2_0, ..., wcos2_n, wsin2_n, (extra), 1]``.

    ``idx`` is capped by the caller (:func:`supervision_pixels`), so the matrix is
    ``n_sample x (2 * n_feat + 2)`` -- a few MB -- while the underlying channels
    stay on disk.  Streaming is what keeps the fit inside the sandbox memory.
    """
    ys, xs = idx[:, 0], idx[:, 1]
    n = ys.size
    ncol = 2 * len(stack) + (1 if extra is not None else 0) + 1
    X = np.empty((n, ncol), np.float32)
    for k in range(len(stack)):
        c, sn = stack.channels(k)
        X[:, 2 * k] = c[ys, xs]
        X[:, 2 * k + 1] = sn[ys, xs]
    if extra is not None:
        ref = float(np.max(extra)) if extra_scale is None else float(extra_scale)
        X[:, -2] = extra[ys, xs] / max(ref, 1e-30)
    X[:, -1] = 1.0
    return X


def _ridge(X: np.ndarray, Y: np.ndarray, lam: float) -> np.ndarray:
    XtX = X.astype(np.float64).T @ X.astype(np.float64)
    XtY = X.astype(np.float64).T @ Y.astype(np.float64)
    XtX[np.arange(XtX.shape[0]), np.arange(XtX.shape[0])] += lam * np.trace(XtX) / XtX.shape[0]
    return np.linalg.solve(XtX, XtY)


def fit_axial_head(stack, target_cos2: np.ndarray, target_sin2: np.ndarray,
                   idx: np.ndarray, lam: float = RIDGE_LAMBDA) -> np.ndarray:
    """Closed-form ridge fit of the axial orientation head.

    Design columns are the confidence-weighted axial channels
    ``[c*cos2t, c*sin2t, 1]`` per (band, scale); the target is the observed trace
    frame ``(cos2t*, sin2t*)``.  Returns a ``(2, 2*n_feat + 1)`` coefficient matrix
    (row 0 -> cos, row 1 -> sin).
    """
    X = design_matrix(stack, idx)
    Y = np.stack([target_cos2[idx[:, 0], idx[:, 1]],
                  target_sin2[idx[:, 0], idx[:, 1]]], axis=1).astype(np.float64)
    good = np.isfinite(X).all(axis=1) & np.isfinite(Y).all(axis=1)
    X, Y = X[good], Y[good]
    if X.shape[0] < X.shape[1] * 4:
        raise ValueError("too few supervision pixels for the axial head fit")
    return _ridge(X, Y, lam).T.astype(np.float64)


def apply_axial_head(stack, coef: np.ndarray, guard: np.ndarray):
    """Evaluate the fitted head over the footprint; returns ``(cos2, sin2, mag)``.

    One streaming pass over the channel files; only two accumulator arrays live in
    memory besides the output.
    """
    n_feat = len(stack)
    coef = np.asarray(coef, np.float64)
    if coef.shape != (2, 2 * n_feat + 1):
        raise ValueError(f"coef shape {coef.shape} does not match {n_feat} features")
    c = np.full(stack.shape, float(coef[0, -1]), np.float32)
    s = np.full(stack.shape, float(coef[1, -1]), np.float32)
    for k in range(n_feat):
        c2, s2 = stack.channels(k)
        c += (coef[0, 2 * k] * c2 + coef[0, 2 * k + 1] * s2).astype(np.float32)
        s += (coef[1, 2 * k] * c2 + coef[1, 2 * k + 1] * s2).astype(np.float32)
    mag = np.hypot(c, s)
    cos2 = np.zeros(stack.shape, np.float32)
    sin2 = np.zeros(stack.shape, np.float32)
    nz = mag > 1e-12
    cos2[nz] = (c[nz] / mag[nz]).astype(np.float32)
    sin2[nz] = (s[nz] / mag[nz]).astype(np.float32)
    cos2[~guard] = 0.0
    sin2[~guard] = 0.0
    mag[~guard] = 0.0
    return cos2, sin2, mag


def fit_tip_head(stack, evidence: np.ndarray, target: np.ndarray,
                 idx: np.ndarray, lam: float = RIDGE_LAMBDA) -> np.ndarray:
    """Ridge fit of the tip/junction heatmap head (same design matrix + evidence)."""
    X = design_matrix(stack, idx, extra=evidence)
    y = target[idx[:, 0], idx[:, 1]].astype(np.float64)
    good = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X, y = X[good], y[good]
    if X.shape[0] < X.shape[1] * 4:
        raise ValueError("too few supervision pixels for the tip head fit")
    return _ridge(X, y[:, None], lam).ravel().astype(np.float64)


def apply_tip_head(stack, evidence: np.ndarray, coef: np.ndarray,
                   guard: np.ndarray) -> np.ndarray:
    """Evaluate the tip head over the footprint (raw linear response)."""
    n_feat = len(stack)
    coef = np.asarray(coef, np.float64)
    if coef.shape != (2 * n_feat + 2,):
        raise ValueError(f"coef shape {coef.shape} does not match {n_feat} features")
    out = np.full(stack.shape, float(coef[-1]), np.float32)
    for k in range(n_feat):
        c2, s2 = stack.channels(k)
        out += (coef[2 * k] * c2 + coef[2 * k + 1] * s2).astype(np.float32)
    out += (coef[-2] * evidence / max(float(np.max(evidence)), 1e-30)).astype(np.float32)
    out[~guard] = 0.0
    return out


def circular_error_deg(pred_cos2: np.ndarray, pred_sin2: np.ndarray,
                       true_cos2: np.ndarray, true_sin2: np.ndarray,
                       idx: np.ndarray) -> float:
    """Mean axial angular error in degrees over ``idx`` (0 = perfect, 90 = orthogonal)."""
    ys, xs = idx[:, 0], idx[:, 1]
    dot = pred_cos2[ys, xs] * true_cos2[ys, xs] + pred_sin2[ys, xs] * true_sin2[ys, xs]
    ang = 0.5 * np.arccos(np.clip(dot, -1.0, 1.0))
    return float(np.degrees(np.mean(ang)))


def block_auc(score: np.ndarray, label: np.ndarray, idx: np.ndarray,
              block_px: int = 200, n_blocks: int = 6) -> dict:
    """Spatially blocked AUC: blocks are held out in turn, AUC averaged (label-free folds).

    ``score`` higher = more likely positive.  Used for the leakage canary
    (single feature vs the catalogue) and for the tip head's held-out skill.
    """
    ys, xs = idx[:, 0], idx[:, 1]
    s = np.asarray(score, np.float64)[ys, xs]
    y = np.asarray(label, bool)[ys, xs]
    good = np.isfinite(s)
    s, y = s[good], y[good]
    by, bx = ys[good], xs[good]
    if y.sum() == 0 or (~y).sum() == 0:
        return dict(auc=float("nan"), n_pos=int(y.sum()), n_neg=int((~y).sum()),
                    per_block=[], note="degenerate label balance")
    bid = (by // block_px) * 10_000 + (bx // block_px)
    uniq = np.unique(bid)
    rng = np.random.default_rng(0)
    rng.shuffle(uniq)
    folds = np.array_split(uniq, max(2, min(n_blocks, uniq.size)))
    per_block = []
    for f in folds:
        te = np.isin(bid, f)
        if y[te].sum() == 0 or (~y[te]).sum() == 0:
            continue
        per_block.append(float(_auc(s[te], y[te])))
    return dict(auc=float(np.mean(per_block)) if per_block else float("nan"),
                n_pos=int(y.sum()), n_neg=int((~y).sum()), per_block=per_block,
                n_blocks=len(per_block), block_px=block_px)


def _auc(score: np.ndarray, label: np.ndarray) -> float:
    """Rank AUC (Mann-Whitney), with ties averaged."""
    order = np.argsort(score, kind="stable")
    r = np.empty(score.size, np.float64)
    r[order] = np.arange(1, score.size + 1, dtype=np.float64)
    # average ranks for ties
    s = score[order]
    i = 0
    while i < s.size:
        j = i + 1
        while j < s.size and s[j] == s[i]:
            j += 1
        if j - i > 1:
            r[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    n_pos = float(label.sum())
    n_neg = float(label.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((r[label].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))
