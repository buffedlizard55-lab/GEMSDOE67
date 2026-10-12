"""The supervised head: a gradient-boosted classifier on the cached evidence channels.

The head is deliberately small and auditable: 16-23 channels, no convolutions, no deep model,
fitted in seconds on CPU.  It is trained either inside a hide-and-recover fold (three blocks
visible, one withheld) or on the full visible catalogue for the shipped emission.  Because
every channel is catalogue-free, the same code path is legal in both cases; only the training
labels and the catalogue-distance masks change.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .dataio import FEATURE_DIR, footprint_from, read_labels

#: channels of the evidence stack (catalogue-free)
BASE_CHANNELS: tuple[str, ...] = (
    "ev", "ev_mag", "ev_grav", "ev_topo", "ev_subsurf", "ev_strain", "ev_seis",
    "coh", "order_R", "tpi5", "curv", "rough", "ev_s3", "ev_s8", "ev_mag_s3", "ev_topo_s3",
)

#: channels derived from public USGS products outside the 19-band stack (optional)
EXTERNAL_CHANNELS: tuple[str, ...] = (
    "ev_lidar", "ev_lidar_s3", "ev_rad", "ev_rad_s3", "ev_ext_all", "ev_ext_all_s3",
    "lidar_valid",
)


def available(channels: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(c for c in channels if (FEATURE_DIR / f"{c}.npy").exists())


def gather(channels: tuple[str, ...], rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Design matrix for the given pixel indices, one channel at a time (low memory)."""
    out = np.empty((rows.size, len(channels)), np.float32)
    for j, name in enumerate(channels):
        a = np.load(FEATURE_DIR / f"{name}.npy", mmap_mode="r")
        out[:, j] = a[rows, cols]
        del a
    return out


def sample_training_pixels(footprint: np.ndarray, catalogue: np.ndarray, exclude: np.ndarray,
                           rng: np.random.Generator, max_pos: int = 60000,
                           neg_per_pos: float = 2.0, min_dist_px: float = 5.0):
    """Positives = catalogue pixels outside ``exclude``; negatives = far from any catalogue."""
    from scipy.ndimage import distance_transform_edt

    d = distance_transform_edt(~catalogue)
    pos = catalogue & ~exclude
    pr, pc = np.nonzero(pos)
    if pr.size > max_pos:
        sel = rng.choice(pr.size, max_pos, replace=False)
        pr, pc = pr[sel], pc[sel]
    neg = footprint & ~exclude & (d >= min_dist_px)
    nr, nc = np.nonzero(neg)
    n_take = min(nr.size, int(pr.size * neg_per_pos))
    sel = rng.choice(nr.size, n_take, replace=False)
    nr, nc = nr[sel], nc[sel]
    rows = np.concatenate([pr, nr])
    cols = np.concatenate([pc, nc])
    y = np.concatenate([np.ones(pr.size, np.int8), np.zeros(nr.size, np.int8)])
    return rows, cols, y


def fit(channels: tuple[str, ...], rows, cols, y, iters: int = 200, seed: int = 0):
    from sklearn.ensemble import HistGradientBoostingClassifier

    X = gather(channels, rows, cols)
    clf = HistGradientBoostingClassifier(max_iter=iters, learning_rate=0.08, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=seed)
    clf.fit(X, y)
    del X
    return clf


def predict_full(clf, channels: tuple[str, ...], domain: np.ndarray,
                 band_rows: int = 1_500_000) -> np.ndarray:
    """Predict over a boolean domain, in row bands, without materialising a full design matrix."""
    rr, cc = np.nonzero(domain)
    out = np.zeros(domain.shape, np.float32)
    for i in range(0, rr.size, band_rows):
        r = rr[i:i + band_rows]
        c = cc[i:i + band_rows]
        out[r, c] = clf.predict_proba(gather(channels, r, c))[:, 1]
    return out


def load_labels_and_footprint():
    labels = read_labels()
    return labels, footprint_from(labels)
