"""Hide-and-recover holdout: the only instrument in this repository that is allowed to
make a promotion recommendation.

Protocol (fixed before any emission rule was scored; see docs/run-card.json):

*   The catalogue (``labels.tif``) is cut into connected components (8-connectivity).
*   Four spatial blocks = the four quadrants of the grid.  For fold *k* the components whose
    centroid falls in block *k* are **withheld**; the withheld pixels are the *truth*.
*   Every catalogue-derived quantity for fold *k* is derived **only from the visible faults**
    (catalogue minus the withheld segments dilated by ``buffer_px``).
*   Scoring masks the visible catalogue pixel-exactly, exactly as the organizer masks the
    known USGS/INGENIOUS faults (forum thread 11516), so mass placed on a mapped fault is
    neither credited nor charged — the same freedom the live scorer gives.
*   The headline number is the **pooled** DTI over the four folds: TP/FP/FN are summed over
    folds and one DTI is formed, matching the way the live board pools public-test pixels.

Because the instrument's truth is the *old* catalogue, a pass licenses packaging a candidate
and never a score claim: a genuinely new fault is invisible to it.  It is a screen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt, label

from .dataio import footprint_from, read_labels
from .grid import GRID_SHAPE

BLOCKS = ("NW", "NE", "SW", "SE")
BUFFER_PX = 2


@dataclass
class Fold:
    name: str
    block: np.ndarray            # bool grid, the scored sub-domain
    active: np.ndarray           # bool grid, valid & ~known & block
    truth: np.ndarray            # bool grid, withheld catalogue pixels inside block
    known: np.ndarray            # bool grid, visible catalogue (masked from every term)
    visible: np.ndarray          # bool grid, catalogue minus withheld buffer
    buffer_zone: np.ndarray      # bool grid, dilation of the withheld segments


def block_masks(shape: tuple[int, int] = GRID_SHAPE) -> dict[str, np.ndarray]:
    h, w = shape
    m = np.zeros(shape, bool)
    out = {}
    out["NW"] = (slice(0, h // 2), slice(0, w // 2))
    out["NE"] = (slice(0, h // 2), slice(w // 2, w))
    out["SW"] = (slice(h // 2, h), slice(0, w // 2))
    out["SE"] = (slice(h // 2, h), slice(w // 2, w))
    masks = {k: m.copy() for k in out}
    for k, sl in out.items():
        masks[k][sl] = True
    return masks


def iter_folds(labels: np.ndarray | None = None, buffer_px: int = BUFFER_PX,
               footprint: np.ndarray | None = None):
    """Yield the four folds one at a time (keeps only one fold's masks in memory)."""
    labels = read_labels() if labels is None else labels
    footprint = footprint_from(labels) if footprint is None else footprint
    catalogue = labels == 1
    comp, ncomp = label(catalogue, structure=np.ones((3, 3), int))
    masks = block_masks(labels.shape)

    # component centroid block assignment
    idx = np.arange(1, ncomp + 1)
    comp_block: dict[int, str] = {}
    if ncomp:
        sums_r = np.bincount(comp.ravel(), minlength=ncomp + 1)
        rr = np.arange(labels.shape[0])[:, None] * np.ones((1, labels.shape[1]), int)
        cc = np.ones((labels.shape[0], 1), int) * np.arange(labels.shape[1])[None, :]
        sum_r = np.bincount(comp.ravel(), weights=rr.ravel(), minlength=ncomp + 1)
        sum_c = np.bincount(comp.ravel(), weights=cc.ravel(), minlength=ncomp + 1)
        for i in idx:
            if sums_r[i] == 0:
                continue
            r = sum_r[i] / sums_r[i]
            c = sum_c[i] / sums_r[i]
            comp_block[int(i)] = ("N" if r < labels.shape[0] / 2 else "S") + \
                                 ("W" if c < labels.shape[1] / 2 else "E")

    for name in BLOCKS:
        hidden_comp = np.zeros(ncomp + 1, bool)
        for i, blk in comp_block.items():
            if blk == name:
                hidden_comp[i] = True
        hidden = hidden_comp[comp] if ncomp else np.zeros(labels.shape, bool)
        buffer_zone = binary_dilation(hidden, np.ones((2 * buffer_px + 1, 2 * buffer_px + 1), bool))
        visible = catalogue & ~buffer_zone
        known = visible
        active = footprint & ~known & masks[name]
        truth = hidden & masks[name]
        yield Fold(name=name, block=masks[name], active=active, truth=truth,
                   known=known, visible=visible, buffer_zone=buffer_zone)


def build_folds(labels: np.ndarray | None = None, buffer_px: int = BUFFER_PX,
                footprint: np.ndarray | None = None) -> list[Fold]:
    """Materialise all four folds (convenience wrapper; prefer :func:`iter_folds`)."""
    return list(iter_folds(labels=labels, buffer_px=buffer_px, footprint=footprint))


def score(pred: np.ndarray, fold: Fold) -> dict:
    """Score one fold's emission against its withheld segments with strict masking."""
    from .metric import dti_exact

    return dti_exact(pred, fold.truth, valid=fold.active, known=None)


def pool(rows: list[dict]) -> dict:
    """Pool per-fold components (sum TP/FP/FN) and form one DTI — the headline number."""
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    k = sum(r["n_truth"] for r in rows)
    dti = tp / (tp + 0.2 * fp + 0.8 * fn + 1e-12)
    return dict(tp=tp, fp=fp, fn=fn, n_truth=k, dti=float(dti),
                coverage=(tp / k) if k else 0.0)


def visible_train_masks(fold: Fold, footprint: np.ndarray, min_dist_px: float = 5.0):
    """Positive/negative training pixels for the fold, derived from the visible faults only."""
    d = distance_transform_edt(~fold.visible)
    pos = fold.visible & ~fold.block          # train outside the scored block
    neg = footprint & ~fold.block & (d >= min_dist_px)
    return pos, neg, d
