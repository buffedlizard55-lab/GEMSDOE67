"""Geometry-aware decoding: across-strike NMS, hysteresis marching, tip extension.

The decode is deliberately *not* a per-pixel threshold.  It follows the predicted
axial orientation field, which is the whole point of the lane:

1. :func:`nms_across_strike` suppresses everything that is not a local maximum
   *across* the lineament (along the predicted normal), so a 2-3 px wide evidence
   ridge contributes one path instead of three.
2. :func:`march` walks from the strongest surviving seeds along the predicted
   tangent, both ways, in lockstep for all seeds at once.  This is the hysteresis
   step: a walk continues while the evidence stays above ``lo`` even through
   stretches that are individually below the seed bar ``hi``.
3. When a walk reaches a tip (evidence below ``lo``), it may *extend* past it for
   at most ``max_ext_px`` further steps, along the same predicted orientation,
   while the evidence stays above the weaker floor ``lo_ext``.  This is the lane's
   "extend traces past mapped tips only along predicted orientation where
   probability support persists".  ``allow_extension=False`` is the ablation arm.

Nothing here reads the catalogue.  All arithmetic is float32 on the full grid;
the step loop touches only the walked cells, never a full-grid transcendental.
"""
from __future__ import annotations

import numpy as np

_ANGLE_STEP = np.pi / 4.0
_DIRS = np.array([(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)],
                 np.int64)


def tangent_field(cos2: np.ndarray, sin2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unit tangent ``(t_y, t_x)`` of the axial frame (single definition for the lane)."""
    theta = 0.5 * np.arctan2(sin2.astype(np.float32), cos2.astype(np.float32))
    return np.sin(theta).astype(np.float32), np.cos(theta).astype(np.float32)


def _dir_index(ny: np.ndarray, nx: np.ndarray) -> np.ndarray:
    a = np.arctan2(ny.astype(np.float32), nx.astype(np.float32))
    return np.mod(np.rint(a / _ANGLE_STEP).astype(np.int64), 8)


def _shift(a: np.ndarray, dy: int, dx: int, fill: float | None = None) -> np.ndarray:
    """``out[i, j] = a[i + dy, j + dx]``.

    ``fill=None`` clamps at the array edge, so a missing neighbour reads the cell's
    own value.  With the ``>=``/``>`` tie-break in :func:`nms_across_strike` that
    means a border cell is kept only when it is strictly above its interior
    neighbour -- padding with ``-inf`` instead would keep every untouched border
    cell of an otherwise empty grid, which is a real (previously latent) defect:
    the footprint touches the array border on all four sides here.
    """
    h, w = a.shape
    if fill is None:
        ys = np.clip(np.arange(h) + dy, 0, h - 1)
        xs = np.clip(np.arange(w) + dx, 0, w - 1)
        return a[np.ix_(ys, xs)]
    out = np.full(a.shape, fill, dtype=a.dtype)
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = a[max(0, -dy):min(h, h - dy), max(0, -dx):min(w, w - dx)]
    return out


def nms_across_strike(evidence: np.ndarray, cos2: np.ndarray, sin2: np.ndarray,
                      guard: np.ndarray) -> np.ndarray:
    """Keep cells that are a local maximum along the predicted *normal*.

    Ties break deterministically (``>=`` on one side, ``>`` on the other), so a
    strictly monotone ramp profile keeps exactly one cell.
    """
    e = np.asarray(evidence, np.float32)
    ty, tx = tangent_field(cos2, sin2)
    idx = _dir_index(-tx, ty)
    keep = np.zeros(e.shape, bool)
    for k in range(8):
        dy, dx = int(_DIRS[k, 0]), int(_DIRS[k, 1])
        sel = (idx == k) & guard
        if not sel.any():
            continue
        plus = _shift(e, dy, dx)[sel]
        minus = _shift(e, -dy, -dx)[sel]
        keep[sel] = (e[sel] >= plus) & (e[sel] > minus)
    return keep & np.asarray(guard, bool)


def _sample(field: np.ndarray, y: np.ndarray, x: np.ndarray, fill: float):
    """Nearest-cell sampling at float positions; returns ``(values, inside)``."""
    h, w = field.shape
    ry = np.rint(y).astype(np.int64)
    rx = np.rint(x).astype(np.int64)
    ok = (ry >= 0) & (ry < h) & (rx >= 0) & (rx < w)
    out = np.full(y.shape, fill, dtype=field.dtype)
    if ok.any():
        out[ok] = field[ry[ok], rx[ok]]
    return out, ok


def march(evidence: np.ndarray, cos2: np.ndarray, sin2: np.ndarray, guard: np.ndarray,
          *, hi_pct: float = 99.0, lo_ratio: float = 0.35, lo_ext_ratio: float = 0.22,
          max_seeds: int = 4000, max_steps: int = 200, max_ext_px: int = 6,
          direction_momentum: float = 0.60, allow_extension: bool = True,
          extension_length_scale: np.ndarray | None = None,
          junction_heat: np.ndarray | None = None, junction_block: float = 0.35) -> dict:
    """March along the predicted orientation from the strongest ridge seeds.

    Deterministic: seeds are ranked by evidence (ties by index), directions come
    from the predicted frame, and there is no random component anywhere.
    """
    e = np.asarray(evidence, np.float32)
    guard = np.asarray(guard, bool)
    vals = e[guard]
    if vals.size == 0:
        raise ValueError("empty guard")
    hi = float(np.percentile(vals, hi_pct))
    if not np.isfinite(hi) or hi <= 0:
        hi = float(vals.max())
    lo = lo_ratio * hi
    lo_ext = lo_ext_ratio * hi

    cand = nms_across_strike(e, cos2, sin2, guard) & (e >= hi)
    ys, xs = np.nonzero(cand)
    empty = dict(trace=np.zeros(e.shape, bool), extension=np.zeros(e.shape, bool),
                 seed_count=0, steps=0, extension_cells=0, hi=hi, lo=lo, lo_ext=lo_ext,
                 nms_candidates=int(ys.size))
    if ys.size == 0:
        return empty
    order = np.argsort(-e[ys, xs], kind="stable")[:max_seeds]
    sy = ys[order].astype(np.float32)
    sx = xs[order].astype(np.float32)
    n_seed = sy.size

    ty_f, tx_f = tangent_field(cos2, sin2)
    guard_f = guard.astype(np.float32)
    ext_scale = None if extension_length_scale is None else extension_length_scale.astype(np.float32)
    jheat = None if junction_heat is None else junction_heat.astype(np.float32)

    trace = np.zeros(e.shape, bool)
    extension = np.zeros(e.shape, bool)
    trace[ys[order], xs[order]] = True
    steps_used = 0
    max_ext_px_f = float(max_ext_px)

    for sign in (1.0, -1.0):
        y = sy.copy()
        x = sx.copy()
        vy, _ = _sample(ty_f, y, x, 0.0)
        vx, _ = _sample(tx_f, y, x, 0.0)
        vy = (vy * sign).astype(np.float32)
        vx = (vx * sign).astype(np.float32)
        active = np.ones(n_seed, bool)
        ext_len = np.zeros(n_seed, np.float64)
        for _step in range(max_steps):
            if not active.any():
                break
            ny_, _ = _sample(ty_f, y, x, 0.0)
            nx_, _ = _sample(tx_f, y, x, 0.0)
            vy = (direction_momentum * vy + (1.0 - direction_momentum) * ny_).astype(np.float32)
            vx = (direction_momentum * vx + (1.0 - direction_momentum) * nx_).astype(np.float32)
            norm = np.hypot(vy, vx).astype(np.float32)
            norm[norm < 1e-9] = 1.0
            vy, vx = vy / norm, vx / norm
            y = (y + vy).astype(np.float32)
            x = (x + vx).astype(np.float32)
            ev, _ = _sample(e, y, x, -np.inf)
            gd, _ = _sample(guard_f, y, x, 0.0)
            inside = gd > 0.5
            lim = np.full(n_seed, max_ext_px_f)
            if ext_scale is not None:
                s_, _ = _sample(ext_scale, y, x, 0.0)
                lim = np.clip(lim * s_.astype(np.float64), 0.0, max_ext_px_f)
            in_hyst = active & inside & (ev >= lo)
            if allow_extension:
                blocked = np.zeros(n_seed, bool)
                if jheat is not None:
                    j_, _ = _sample(jheat, y, x, 0.0)
                    blocked = j_ > junction_block
                in_ext = (active & inside & (ev >= lo_ext) & (ev < lo)
                          & (~blocked) & (ext_len < lim))
            else:
                in_ext = np.zeros(n_seed, bool)
            take = in_hyst | in_ext
            if not take.any():
                break
            ry = np.rint(y).astype(np.int64)
            rx = np.rint(x).astype(np.int64)
            if in_hyst.any():
                trace[ry[in_hyst], rx[in_hyst]] = True
            if in_ext.any():
                extension[ry[in_ext], rx[in_ext]] = True
                ext_len[in_ext] += 1.0
            active &= take
            active &= ~(ext_len >= lim - 1e-9)          # exhausted its extension allowance
            steps_used += int(take.sum())
    return dict(trace=trace, extension=extension, seed_count=int(n_seed),
                steps=steps_used, extension_cells=int(extension.sum()),
                hi=hi, lo=lo, lo_ext=lo_ext, nms_candidates=int(ys.size))


def decimate_by_spacing(support: np.ndarray, score: np.ndarray, spacing_px: float,
                        max_dots: int = 220_000) -> np.ndarray:
    """Greedy spacing selection: visit cells by descending ``score``, block a disc.

    A cell is kept when no already-kept cell lies within ``spacing_px``.  On a 1-px
    skeleton this reproduces "a dot every ``spacing_px`` along the path".  Ties are
    broken by index order, so the result is deterministic.
    """
    s = np.asarray(support, bool)
    if spacing_px <= 0:
        raise ValueError("spacing_px must be positive")
    ys, xs = np.nonzero(s)
    if ys.size == 0:
        return np.zeros(s.shape, bool)
    sc = np.asarray(score, np.float32)
    order = np.argsort(-sc[ys, xs], kind="stable")
    r = int(np.ceil(spacing_px))
    ky, kx = np.mgrid[-r:r + 1, -r:r + 1]
    disc = ((ky * ky + kx * kx) <= spacing_px * spacing_px)
    blocked = np.zeros(s.shape, bool)
    out = np.zeros(s.shape, bool)
    h, w = s.shape
    hits = 0
    for i in order:
        y, x = int(ys[i]), int(xs[i])
        if blocked[y, x]:
            continue
        out[y, x] = True
        hits += 1
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        sub = disc[(y0 - y + r):(y0 - y + r) + (y1 - y0), (x0 - x + r):(x0 - x + r) + (x1 - x0)]
        blocked[y0:y1, x0:x1] |= sub
        if hits >= max_dots:
            break
    return out


def allowed_away_from_catalogue(catalogue: np.ndarray, footprint: np.ndarray,
                                exclude_px: float = 2.0) -> np.ndarray:
    """Cells at least ``exclude_px`` from any mapped trace, inside the footprint.

    Measured on the live bytes by the sibling lanes: the 200 m annulus around the
    mapped catalogue earned exactly zero credit, so emitting there is pure
    placement tax.  ``exclude_px=2`` is that 200 m rule at the 100 m cell size.
    """
    from scipy import ndimage as ndi
    cat = np.asarray(catalogue, bool)
    if not cat.any():
        return np.asarray(footprint, bool).copy()
    d = ndi.distance_transform_edt(~cat)
    return np.asarray(footprint, bool) & (d > float(exclude_px))
