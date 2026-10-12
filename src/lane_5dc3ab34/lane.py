"""Lane orchestration: fit -> predict -> decode -> emit, per fold and arm.

Arms
----
``iso``   ablation E1: isotropic hysteresis on the segmentation head only,
          no NMS, no tip extension (per-pixel classification regime).
``lane``  E2: orientation-gated hysteresis + orientation-aware NMS + tip
          extension along predicted orientation (the lane brief).
``lane_blur`` E3: E2 with a wider scatter kernel in the allocation field.

Every catalogue-derived quantity comes from ``visible`` only.  Scoring is
delegated to the shared ``gems57.evaluate_holdout`` instrument (pooled exact
DTI, alpha 0.2, beta 0.8, 300 m triangular kernel).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi

from . import decode as dec
from . import heads as headsmod
from . import nodes as nodesmod

# preregistered parameters -- chosen before any fold truth was read
PARAMS = dict(
    tau_hi=0.55, tau_lo=0.35, tau_ext=0.30, tau_tip=0.55,
    tip_max_len=6, nms_halfwidth=2, max_turn_deg=45.0, tip_turn_deg=60.0,
    flank_px=2.0, alloc_sigma=1.5, alloc_sigma_blur=2.2,
    k_truth=45000.0, spacing=3.0, floor=0.02,
)


@dataclass
class ArmResult:
    arm: str
    emitted: np.ndarray           # bool full-grid node field
    support: np.ndarray           # bool decoded trace support
    extended: np.ndarray          # bool tip-extension pixels
    n_dots: int
    receipt: dict = field(default_factory=dict)


def run_arm(arm: str, cache, visible: np.ndarray, footprint: np.ndarray,
            heads: headsmod.Heads | None = None, *,
            params: dict | None = None, preds: headsmod.Predictions | None = None,
            emission: str = "greedy") -> ArmResult:
    """Run one arm end-to-end on the full grid.

    ``visible`` is the fold's feature-visible catalogue (already buffer-
    collared by the shared holdout).  ``heads``/``preds`` may be passed in to
    share one fit across arms (identical prediction surface, different
    decoding -- the ablation contract).
    """
    P = dict(PARAMS, **(params or {}))
    if preds is None:
        if heads is None:
            heads = headsmod.fit_heads(cache, visible)
        preds = headsmod.predict_full(cache, heads)

    if arm == "iso":
        support = dec.oriented_hysteresis(
            preds.p, preds.cos2, preds.sin2, P["tau_hi"], P["tau_lo"],
            orient_gate=False)
        extended = np.zeros(support.shape, bool)
        n_tip_ext = 0
    elif arm in ("lane", "lane_blur"):
        gated = dec.oriented_hysteresis(
            preds.p, preds.cos2, preds.sin2, P["tau_hi"], P["tau_lo"],
            max_turn_deg=P["max_turn_deg"], orient_gate=True)
        thinned = dec.oriented_nms(preds.p, preds.cos2, preds.sin2, gated,
                                   halfwidth=P["nms_halfwidth"])
        res = dec.extend_tips(thinned, preds.p, preds.cos2, preds.sin2,
                              preds.tip, max_len=P["tip_max_len"],
                              tau_ext=P["tau_ext"], tau_tip=P["tau_tip"],
                              max_turn_deg=P["tip_turn_deg"])
        support, extended = res.support, res.extended
        n_tip_ext = res.n_tips_extended
    else:
        raise ValueError(f"unknown arm {arm!r}")

    # emission domain: footprint, off the (visible) catalogue flank, with
    # tip-extension pixels protected from the flank prune.  Protection never
    # overrides the catalogue itself: no positive mass may sit on mapped faults
    # (the shared writer enforces this).
    allowed = dec.flank_prune(support & footprint, visible,
                              protect=extended, flank_px=P["flank_px"])
    allowed &= footprint & ~np.asarray(visible, bool)

    sigma = P["alloc_sigma_blur"] if arm == "lane_blur" else P["alloc_sigma"]
    p_alloc = nodesmod.allocation_field(preds.p, allowed, sigma=sigma)

    if emission == "greedy":
        alloc = nodesmod.greedy_nodes(p_alloc, allowed, P["k_truth"],
                                      floor=P["floor"])
        emitted = alloc.emitted
        receipt = dict(emission="greedy", n_dots=int(alloc.n_dots),
                       rounds=alloc.rounds, surrogate_dti=alloc.surrogate_dti,
                       expected_covered_credit=alloc.expected_covered_credit,
                       expected_self_credit=alloc.expected_self_credit)
    elif emission == "spacing":
        emitted = nodesmod.spacing_nodes(allowed, p_alloc, spacing=P["spacing"])
        receipt = dict(emission="spacing", spacing=P["spacing"],
                       n_dots=int(emitted.sum()))
    else:
        raise ValueError(f"unknown emission {emission!r}")

    receipt.update(arm=arm, n_support_px=int(support.sum()),
                   n_extension_px=int(extended.sum()),
                   n_tips_extended=int(n_tip_ext),
                   n_allowed_px=int(allowed.sum()))
    return ArmResult(arm=arm, emitted=emitted, support=support,
                     extended=extended, n_dots=int(emitted.sum()),
                     receipt=receipt)


def tip_adjacent_truth(truth: np.ndarray, radius_px: float = 3.0) -> np.ndarray:
    """Withheld-truth pixels within ``radius_px`` of a withheld component tip.

    The gate's second criterion: "better recovery of masked tip-adjacent
    segments in hide-and-recover blocks".
    """
    t = np.asarray(truth, bool)
    tips_y, tips_x = dec.tip_points(t)
    if len(tips_y) == 0:
        return np.zeros(t.shape, bool)
    tip_mask = np.zeros(t.shape, bool)
    tip_mask[tips_y, tips_x] = True
    near_tip = ndi.distance_transform_edt(~tip_mask) <= radius_px
    return t & near_tip
