"""Catalogue-free geophysical evidence stack for the GEMSDOE67 orientation/tip lane.

Every layer here is derived ONLY from the 19-band GeoDAWN numerical feature
stack (gems-geodawn-numerical-features.tif) plus scalar morphology of those
bands.  No catalogue information enters this module, so the same cache serves
every hide-and-recover fold (parallel-run protocol rule 2: catalogue-based
features are built per-fold in :mod:`gems67.heads`, from visible faults only).

Band identities (GeoTIFF band descriptions, re-read from the file):

    1 mag_anom  2 rtp  3 tmi_hg  4 geod_2ndinv  5 iso_grav_anom_slope
    6 tc  7 geod_shearrate  8 geod_dilaterate  9 tmi_vg  10 deq_n100a15
    11 iso_grav_anom_vg  12 det_elev  13 iso_grav_anom  14 tmi
    15 depth_to_base_surf  16 ieq_n100a15  17 cond_surf
    18 iso_grav_anom_hg  19 det_elev_slope

Memory contract: the sandbox has ~3 GB RAM and the grid is 3730x3292, so all
derived layers live in a float32 ``np.memmap`` on disk (about 50 MB per layer)
and are read block-wise.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

BANDS = [
    "mag_anom", "rtp", "tmi_hg", "geod_2ndinv", "iso_grav_anom_slope", "tc",
    "geod_shearrate", "geod_dilaterate", "tmi_vg", "deq_n100a15",
    "iso_grav_anom_vg", "det_elev", "iso_grav_anom", "tmi",
    "depth_to_base_surf", "ieq_n100a15", "cond_surf", "iso_grav_anom_hg",
    "det_elev_slope",
]

# Bands whose gradients carry structural-fabric (edge) information.
FABRIC = [
    "rtp", "tmi", "tmi_hg", "tmi_vg", "tc",
    "iso_grav_anom_hg", "iso_grav_anom_vg", "iso_grav_anom_slope",
    "det_elev", "cond_surf", "depth_to_base_surf",
]

SENTINEL = -3.4028234663852886e+38


@dataclass
class FeatureCache:
    """Memmap-backed derived layer store."""

    path: Path
    layers: list[str]         # layer names, index = memmap band
    shape: tuple[int, int]
    valid: np.ndarray         # bool full-grid footprint of finite feature data
    mm: np.memmap             # (n_layers, H, W) float32

    def layer(self, name: str) -> np.ndarray:
        return self.mm[self.layers.index(name)]

    def block(self, row0: int, row1: int) -> np.ndarray:
        """Return (n_layers, row1-row0, W) float32 copy for one row band."""
        return np.asarray(self.mm[:, row0:row1, :], dtype=np.float32)

    def sample(self, ys: np.ndarray, xs: np.ndarray) -> np.ndarray:
        """Return (n_samples, n_layers) design matrix at the given pixels."""
        out = np.empty((len(ys), len(self.layers)), np.float32)
        order = np.argsort(ys, kind="stable")
        ys_s, xs_s = ys[order], xs[order]
        # group by row to make memmap access sequential
        i = 0
        while i < len(ys_s):
            j = i
            while j < len(ys_s) and ys_s[j] == ys_s[i]:
                j += 1
            rows = self.mm[:, ys_s[i], :]
            out[order[i:j]] = rows[:, xs_s[i:j]].T
            i = j
        return out


def _rank01(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Map ``a`` to [0,1] by empirical CDF rank inside ``valid``; 0 outside."""
    out = np.zeros(a.shape, np.float32)
    v = a[valid]
    if v.size == 0:
        return out
    order = np.argsort(v, kind="stable")
    ranks = np.empty(v.size, np.float64)
    ranks[order] = np.arange(v.size, dtype=np.float64) / max(v.size - 1, 1)
    out[valid] = ranks.astype(np.float32)
    return out


def _fill(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Replace non-finite/sentinel cells with the inside-footprint median."""
    good = valid & np.isfinite(a) & (a > SENTINEL * 0.5)
    if not good.any():
        return np.zeros(a.shape, np.float32)
    med = float(np.median(a[good]))
    out = np.where(good, a, med).astype(np.float32)
    return out


def _grad(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gy, gx = np.gradient(a)
    return gy.astype(np.float32), gx.astype(np.float32)


def ridge_orientation(gy: np.ndarray, gx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Axial ridge-line direction (cos 2phi, sin 2phi).

    The gradient (gx, gy) points across the ridge; the line direction is
    perpendicular: phi = atan2(gy, gx) + pi/2.  Doubling the angle makes the
    representation undirected (phi == phi + pi), as required for fault strike.
    """
    mag = np.hypot(gx, gy)
    tiny = mag < 1e-12
    gx = np.where(tiny, 1.0, gx)
    gy = np.where(tiny, 0.0, gy)
    phi = np.arctan2(gy, gx) + np.pi / 2.0
    return np.cos(2.0 * phi).astype(np.float32), np.sin(2.0 * phi).astype(np.float32)


def structure_tensor(gy: np.ndarray, gx: np.ndarray, sigma: float = 2.0):
    """Coherence and axial ridge orientation from the structure tensor."""
    jxx = ndi.gaussian_filter(gx * gx, sigma, mode="nearest")
    jyy = ndi.gaussian_filter(gy * gy, sigma, mode="nearest")
    jxy = ndi.gaussian_filter(gx * gy, sigma, mode="nearest")
    num = np.sqrt((jxx - jyy) ** 2 + 4.0 * jxy * jxy)
    den = jxx + jyy + 1e-12
    coh = (num / den).astype(np.float32)
    # principal variation direction (gradient-like) then +90 deg to the line
    theta = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy) + np.pi / 2.0
    return coh, np.cos(2.0 * theta).astype(np.float32), np.sin(2.0 * theta).astype(np.float32)


def build_cache(features_path: Path, cache_path: Path,
                footprint: np.ndarray, overwrite: bool = False) -> FeatureCache:
    """Derive all catalogue-free layers into a memmap cache.

    Layers (in order): one ``edge_<band>`` rank layer per FABRIC band, the raw
    rank layers for scalar evidence bands, ridge morphology of det_elev,
    absolute geodetic rates, seismicity proximity, structure-tensor coherence
    and ridge orientation of the blended edge field, and per-band axial
    orientations of the three highest-SNR fabric fields (rtp, det_elev, cond).
    """
    import rasterio

    cache_path = Path(cache_path)
    H, W = footprint.shape
    edge_names = [f"edge_{b}" for b in FABRIC]
    scalar_names = ["geod_2ndinv", "abs_shearrate", "abs_dilaterate",
                    "seis_prox", "ieq", "ridge_topo"]
    orient_names = ["cos2_rtp", "sin2_rtp", "cos2_elev", "sin2_elev",
                    "cos2_cond", "sin2_cond"]
    st_names = ["st_coh", "st_cos2", "st_sin2"]
    names: list[str] = edge_names + scalar_names + orient_names + st_names

    if cache_path.exists() and not overwrite:
        mm = np.memmap(cache_path, dtype=np.float32, mode="r", shape=(len(names), H, W))
        return FeatureCache(cache_path, names, (H, W), footprint, mm)

    tmp = cache_path.with_suffix(".building")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    mm = np.memmap(tmp, dtype=np.float32, mode="w+", shape=(len(names), H, W))

    blended = np.zeros((H, W), np.float32)
    band_grads: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    with rasterio.open(features_path) as ds:
        assert ds.count == 19, f"expected 19 bands, got {ds.count}"
        valid = footprint.copy()
        for bi in range(1, 20):
            name = BANDS[bi - 1]
            raw = ds.read(bi)
            good = np.isfinite(raw) & (raw > SENTINEL * 0.5) & footprint
            valid &= good
            a = _fill(raw, footprint)
            del raw
            if name in FABRIC:
                sm = ndi.gaussian_filter(a, 1.0, mode="nearest")
                gy, gx = _grad(sm)
                mag = np.hypot(gx, gy)
                idx = names.index(f"edge_{name}")
                mm[idx] = _rank01(mag, footprint)
                blended += mm[idx]
                if name in ("rtp", "det_elev", "cond_surf"):
                    band_grads[name] = (gy, gx)
            if name == "geod_2ndinv":
                mm[names.index("geod_2ndinv")] = _rank01(a, footprint)
            elif name == "geod_shearrate":
                mm[names.index("abs_shearrate")] = _rank01(np.abs(a), footprint)
            elif name == "geod_dilaterate":
                mm[names.index("abs_dilaterate")] = _rank01(np.abs(a), footprint)
            elif name == "ieq_n100a15":
                mm[names.index("ieq")] = _rank01(a, footprint)
            elif name == "deq_n100a15":
                # closer to seismicity -> larger evidence
                mm[names.index("seis_prox")] = _rank01(-a, footprint)
            elif name == "det_elev":
                opened = ndi.grey_opening(a, size=5, mode="nearest")
                mm[names.index("ridge_topo")] = _rank01(a - opened, footprint)
            del a

    # structure tensor on the blended edge field
    gy, gx = _grad(ndi.gaussian_filter(blended, 1.0, mode="nearest"))
    coh, c2, s2 = structure_tensor(gy, gx, sigma=2.0)
    mm[names.index("st_coh")] = coh * valid
    mm[names.index("st_cos2")] = c2
    mm[names.index("st_sin2")] = s2
    del blended, gy, gx, coh, c2, s2

    for band, tag in (("rtp", "rtp"), ("det_elev", "elev"), ("cond_surf", "cond")):
        gy, gx = band_grads[band]
        c2, s2 = ridge_orientation(gy, gx)
        mm[names.index(f"cos2_{tag}")] = c2
        mm[names.index(f"sin2_{tag}")] = s2
        del gy, gx, c2, s2

    mm.flush()
    del mm
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp.replace(cache_path)
    mm = np.memmap(cache_path, dtype=np.float32, mode="r", shape=(len(names), H, W))
    return FeatureCache(cache_path, names, (H, W), valid, mm)
