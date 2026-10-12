"""The lane's comparison arms.

Every arm is an emission produced from the *same* label-free evidence field, so the
only things that differ are the lane's own mechanisms.  Budgets are equalised so
that "beats random" isolates placement, not mass:

======================  ==========================================================
``random``              same support, same dot count, uniform over the allowed set
``lattice_d3``          the champion-family control: one dot per 3 x 3 px tile at
                        the tile's best expected kernel credit (the shared
                        template's ``emit_decimated``), budget-matched
``orient_noext``        this lane, hysteresis marching + across-strike NMS, tips
                        **not** extended (ablation for the extension mechanism)
``orient_ext``          this lane, marching + NMS + tip extension, fixed spacing
``orient_marginal``     this lane, marching + NMS + tip extension, nodes chosen by
                        calibrated greedy marginal-DTI selection
======================  ==========================================================
"""
from __future__ import annotations

import numpy as np

from gems57 import emit

from . import decode


def arm_bank(evidence: np.ndarray, cos2: np.ndarray, sin2: np.ndarray,
             guard: np.ndarray, allowed: np.ndarray, *, spacing_px: float = 2.83,
             hi_pct: float = 99.0, max_seeds: int = 4000, max_steps: int = 200,
             max_ext_px: int = 6, direction_momentum: float = 0.60,
             lo_ratio: float = 0.35, lo_ext_ratio: float = 0.22,
             k_truth: float = 14088.7, seed: int = 67,
             extension_length_scale: np.ndarray | None = None,
             junction_heat: np.ndarray | None = None,
             junction_block: float = 0.35,
             want_marginal: bool = True) -> dict:
    """Build every arm as a dict ``name -> (dot mask, diagnostics)``.

    ``k_truth`` is the calibrated ``|G|`` used by the marginal-DTI allocation.  It
    is a *surrogate-calibration* constant, taken from the sibling lanes' two-score
    solve on the live bytes (14,088.7 px, ``knowledge/103`` of the GEMSDOE52 line),
    not from anything measured on this holdout.
    """
    allowed = np.asarray(allowed, bool)
    guard = np.asarray(guard, bool)
    m_ext = decode.march(evidence, cos2, sin2, guard, hi_pct=hi_pct, lo_ratio=lo_ratio,
                         lo_ext_ratio=lo_ext_ratio, max_seeds=max_seeds,
                         max_steps=max_steps, max_ext_px=max_ext_px,
                         direction_momentum=direction_momentum, allow_extension=True,
                         extension_length_scale=extension_length_scale,
                         junction_heat=junction_heat, junction_block=junction_block)
    m_no = decode.march(evidence, cos2, sin2, guard, hi_pct=hi_pct, lo_ratio=lo_ratio,
                        lo_ext_ratio=lo_ext_ratio, max_seeds=max_seeds,
                        max_steps=max_steps, max_ext_px=max_ext_px,
                        direction_momentum=direction_momentum, allow_extension=False)

    support_ext = (m_ext["trace"] | m_ext["extension"]) & allowed
    support_no = m_no["trace"] & allowed
    score = np.asarray(evidence, np.float32)

    dots_ext = decode.decimate_by_spacing(support_ext, score, spacing_px)
    dots_no = decode.decimate_by_spacing(support_no, score, spacing_px)

    # lattice control at matched budget
    p_unit = _unit_field(score, allowed)
    ranked, _credit = emit.emit_decimated(p_unit, allowed, tile_px=3)
    budget = int(dots_ext.sum())
    dots_lat = emit.emit_prefix(ranked, max(budget, 1))

    arms = {
        "orient_ext": (dots_ext, dict(dots=int(dots_ext.sum()),
                                      support=int(support_ext.sum()),
                                      spacing_px=spacing_px,
                                      seed_count=m_ext["seed_count"],
                                      steps=m_ext["steps"],
                                      extension_cells=m_ext["extension_cells"],
                                      hi=m_ext["hi"], lo=m_ext["lo"],
                                      lo_ext=m_ext["lo_ext"],
                                      nms_candidates=m_ext["nms_candidates"])),
        "orient_noext": (dots_no, dict(dots=int(dots_no.sum()),
                                       support=int(support_no.sum()),
                                       spacing_px=spacing_px,
                                       seed_count=m_no["seed_count"],
                                       steps=m_no["steps"],
                                       extension_cells=0,
                                       hi=m_no["hi"], lo=m_no["lo"],
                                       nms_candidates=m_no["nms_candidates"])),
        "lattice_d3": (dots_lat, dict(dots=int(dots_lat.sum()), tile_px=3,
                                      budget_matched_to="orient_ext", budget=budget)),
        "random": _random_arm(dots_ext, allowed, seed=seed),
    }

    if want_marginal:
        p_skel = np.where(support_ext, _unit_field(score, support_ext), 0.0).astype(np.float32)
        alloc = emit.allocate_by_marginal_bar(p_skel, allowed, float(k_truth),
                                              floor=0.0, max_dots=200_000,
                                              candidate_cap=600_000)
        dots_marg = alloc.emitted & allowed
        arms["orient_marginal"] = (dots_marg, dict(
            dots=int(dots_marg.sum()), k_truth=float(k_truth),
            expected_covered_credit=float(alloc.expected_covered_credit),
            expected_self_credit=float(alloc.expected_self_credit),
            surrogate_dti=float(alloc.surrogate_dti), support=int(support_ext.sum())))
    return arms


def tile_ranking(expected_credit: np.ndarray, allowed: np.ndarray, *, tile_px: int = 3,
                 floor: float = 0.0) -> np.ndarray:
    """Tile-decimated ranking from a precomputed ``E[k]`` field.

    Identical arithmetic to :func:`gems57.emit.emit_decimated` (one dot per
    ``tile_px`` x ``tile_px`` tile, at the tile's ``argmax E[k]``, tiles ordered by
    their maximum), but it reuses an ``E[k]`` that was computed once, which makes a
    per-fold budget sweep cost one tile pass instead of one full convolution.
    Returns an int32 array whose positive values are the 1-based rank of each dot.
    """
    ek = np.where(np.asarray(allowed, bool), np.asarray(expected_credit, np.float32), 0.0)
    H, W = ek.shape
    ph, pw = (-H) % tile_px, (-W) % tile_px
    padded = np.pad(ek, ((0, ph), (0, pw)), mode="constant")
    th, tw = padded.shape[0] // tile_px, padded.shape[1] // tile_px
    tiles = padded.reshape(th, tile_px, tw, tile_px).transpose(0, 2, 1, 3)
    tiles = tiles.reshape(th * tw, tile_px * tile_px)
    tile_max = tiles.max(axis=1)
    tile_arg = tiles.argmax(axis=1)
    ids = np.flatnonzero(tile_max > np.float32(floor))
    order = ids[np.argsort(-tile_max[ids], kind="stable")]
    ty = (order // tw) * tile_px
    tx = (order % tw) * tile_px
    ay = ty + (tile_arg[order] // tile_px)
    ax = tx + (tile_arg[order] % tile_px)
    keep = (ay < H) & (ax < W)
    ay, ax = ay[keep], ax[keep]
    ranked = np.zeros(ek.shape, np.int32)
    ranked[ay, ax] = np.arange(1, ay.size + 1, dtype=np.int32)
    return ranked


def _unit_field(score: np.ndarray, mask: np.ndarray, hi_pct: float = 99.5) -> np.ndarray:
    """Scale a non-negative evidence field to [0, 1] over ``mask``."""
    m = np.asarray(mask, bool)
    vals = np.asarray(score, np.float32)[m]
    if vals.size == 0:
        return np.zeros(np.asarray(score).shape, np.float32)
    ref = float(np.percentile(vals, hi_pct))
    if ref <= 0:
        return np.zeros(np.asarray(score).shape, np.float32)
    return np.clip(np.asarray(score, np.float32) / ref, 0.0, 1.0)


def _random_arm(reference: np.ndarray, allowed: np.ndarray, seed: int = 67):
    """Uniform random dots inside ``allowed`` at the reference arm's dot count."""
    ref = np.asarray(reference, bool)
    m = np.asarray(allowed, bool)
    n = int(ref.sum())
    ys, xs = np.nonzero(m)
    out = np.zeros(ref.shape, bool)
    if ys.size == 0 or n == 0:
        return out, dict(dots=0, note="empty allowed set or zero budget")
    rng = np.random.default_rng(seed)
    pick = rng.choice(ys.size, size=min(n, ys.size), replace=False)
    out[ys[pick], xs[pick]] = True
    return out, dict(dots=int(out.sum()), budget=int(n), allowed_cells=int(ys.size),
                     seed=int(seed), note="uniform over allowed cells; same budget as orient_ext")


def recovery_of_masked_tip_pixels(dots: np.ndarray, hidden: np.ndarray,
                                  distance_to_visible: np.ndarray,
                                  tip_band_px: float = 5.0) -> dict:
    """Fraction of withheld *tip-adjacent* truth pixels credited within 300 m.

    ``hidden`` is the withheld truth mask of a fold, ``distance_to_visible`` the
    Euclidean distance (px) from every cell to the fold's visible catalogue.  The
    tip band is the set of withheld cells within ``tip_band_px`` of a visible
    trace: the sibling instrument reports 88.5 % of its withheld truth lies there,
    and it is exactly the population the extension mechanism claims to reach.
    """
    from scipy import ndimage as ndi
    from gems57.metric import kernel
    d = np.asarray(dots, bool)
    hid = np.asarray(hidden, bool)
    band = hid & (distance_to_visible <= tip_band_px)
    if not hid.any():
        return dict(n_hidden=0, n_tip_band=0, recovery=float("nan"), tip_recovery=float("nan"))
    if not d.any():
        return dict(n_hidden=int(hid.sum()), n_tip_band=int(band.sum()),
                    recovery=0.0, tip_recovery=0.0)
    dp = ndi.distance_transform_edt(~d)
    cred = kernel(dp)
    return dict(n_hidden=int(hid.sum()), n_tip_band=int(band.sum()),
                recovery=float(cred[hid].sum() / hid.sum()),
                tip_recovery=float(cred[band].sum() / band.sum()) if band.any() else float("nan"))
