"""Building the deliverable: calibrated greedy dot emission, then the legal GeoTIFF.

The emission rule (fixed before scoring; see docs/research/run-card.json):

1.  evidence -> calibrated probability ``q`` (bin calibration on the *visible* catalogue only)
2.  axial NMS -> hysteresis (high/low quantiles of the in-footprint evidence) -> tip relay
3.  expected credit ``EC(x) = sum_{|d|<=3px} k(|d|) q(x+d)``, the greedy objective
4.  greedy selection in descending EC with exclusion radius ``r_excl`` and bar ``alpha*DTI_est``
5.  binary values: 1.0 where a dot was selected, 0.0 elsewhere inside the footprint, NaN (or
    nothing) outside — the exact structure the organizers' own sample submission uses
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation

from . import decode, emit, features
from .dataio import FEATURE_DIR, footprint_from, read_labels
from .grid import ALPHA


def build_emission(ev: np.ndarray, cos2t: np.ndarray, sin2t: np.ndarray,
                   catalogue: np.ndarray, footprint: np.ndarray,
                   high_q: float = 0.90, low_q: float = 0.70, bar: float = ALPHA * 0.28,
                   r_excl: float = 2.0, off_catalogue_px: int = 2,
                   max_dots: int | None = None, relay_steps: int = 8) -> dict:
    """Produce the emission and the diagnostics needed to audit it.

    ``catalogue`` is the set of *visible* mapped-fault pixels used for calibration (all
    60 988 in the final build; only the non-withheld ones inside a fold).
    ``off_catalogue_px`` prunes dots within that Chebyshev distance of the catalogue: those
    pixels are masked or nearly masked by the organizer, so they cannot earn hidden-fault
    credit while they can still be charged as false positives.
    """
    from scipy.ndimage import distance_transform_edt

    d_cat = distance_transform_edt(~catalogue)
    within3 = d_cat <= 3.0
    train_mask = footprint & (catalogue | (d_cat >= 5.0))
    cal = emit.calibrate_q(ev, within3, train_mask)
    q = emit.apply_calibration(ev, cal)

    search = footprint & (d_cat > off_catalogue_px)
    dec = decode.decode(ev, cos2t, sin2t, high_q=high_q, low_q=low_q, search=footprint,
                        relay_steps=relay_steps)
    ec = emit.expected_credit(np.where(np.isfinite(q), q, 0.0).astype(np.float32))
    cand = dec["candidates"] & search
    dots = emit.greedy_dots(ec, bar=bar, r_excl=r_excl, candidate_mask=cand, max_dots=max_dots)

    return dict(dots=dots, q=q, cal=cal, dec=dec, ec=ec, d_cat=d_cat,
                n_candidates=int(cand.sum()), n_dots=int(dots.sum()),
                bar=bar, r_excl=r_excl, high_q=high_q, low_q=low_q,
                off_catalogue_px=off_catalogue_px,
                min_dot_distance_to_catalogue=float(d_cat[dots].min()) if dots.any() else None)


def to_submission(dots: np.ndarray, footprint: np.ndarray, outside: str = "nan") -> np.ndarray:
    """Binary dots -> the competition raster.

    ``outside='nan'`` reproduces the organizer sample (NaN outside the footprint);
    ``outside='zero'`` writes an all-finite raster, which is the safer of the two against a
    validator that ignores the nodata tag.
    """
    v = np.where(dots, np.float32(1.0), np.float32(0.0))
    if outside == "nan":
        v = np.where(footprint, v, np.float32(np.nan))
    elif outside != "zero":
        raise ValueError("outside must be 'nan' or 'zero'")
    return v.astype(np.float32)


def load_evidence() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ev = np.asarray(features.load("ev"))
    cos2t = np.asarray(features.load("cos2t"))
    sin2t = np.asarray(features.load("sin2t"))
    return ev, cos2t, sin2t
