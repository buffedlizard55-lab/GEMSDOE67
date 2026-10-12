"""Geometry-aware feature stack: per-family lineament evidence + axial orientation field.

Design (this repository's lane, "orientation-voted lineaments"):

1.  Every band is robustly standardised inside the footprint (median / IQR) so that
    radiometric counts per second, nanotesla and metres are commensurable.
2.  Per band, the *gradient structure tensor* (Smith et al. 1995; Weickert 1998) is built
    at gradient scale sigma_1 = 1 px with tensor smoothing sigma_2 = 2 px:

        J = G_{sigma2} * [[gx^2, gx*gy], [gx*gy, gy^2]]

    with eigenvalues l1 >= l2 >= 0 and axial orientation theta = 0.5*atan2(2*Jxy, Jxx-Jyy).
    Because a fault is an *undirected* line, orientation is encoded axially:
    (cos 2*theta, sin 2*theta).  This is the "axial orientation head" of the lane.
3.  Per-band lineament evidence  e_b = sqrt(l1) * (l1 - l2) / (l1 + l2 + eps)  — a strong
    gradient whose direction is *consistent over a neighbourhood* (a lineament), not an
    isolated edge.
4.  Bands are grouped into geological families (magnetic, gravity, topographic, subsurface,
    strain, seismic).  Family evidence is the mean of its members; the multi-physics
    agreement order parameter is  R = |sum_f w_f e^{2i theta_f}| / sum_f w_f  (an axial
    order parameter, exactly as used for orientation statistics of undirected lines).
5.  The reported orientation field is the evidence-weighted axial mean of the family
    orientations; the reported evidence is the sum of family evidence.

No catalogue information enters any of these channels, so the same stack is legal inside a
hide-and-recover fold (the fold only changes labels and the catalogue-distance channel).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, laplace

from .dataio import FEATURE_DIR, band, footprint_from, read_labels, stack_memmap
from .grid import FEATURE_NODATA

SIGMA_GRAD = 1.0
SIGMA_TENSOR = 2.0
EPS = 1e-9

#: Geological families of the 19 provided bands (names read from the file's GDAL_METADATA).
FAMILIES: dict[str, tuple[str, ...]] = {
    "mag": ("mag_anom", "rtp", "tmi", "tmi_hg", "tmi_vg", "tc"),
    "grav": ("iso_grav_anom", "iso_grav_anom_hg", "iso_grav_anom_vg", "iso_grav_anom_slope"),
    "topo": ("det_elev", "det_elev_slope"),
    "subsurf": ("cond_surf", "depth_to_base_surf"),
    "strain": ("geod_2ndinv", "geod_shearrate", "geod_dilaterate"),
    "seis": ("ieq_n100a15", "deq_n100a15"),
}

CHANNELS = (
    "ev",                 # aggregate lineament evidence (sum over families)
    "cos2t", "sin2t",     # axial orientation field (evidence-weighted)
    "order_R",            # multi-physics axial agreement order parameter
    "coh",                # evidence-weighted mean per-band coherence
    "ev_mag", "ev_grav", "ev_topo", "ev_subsurf", "ev_strain", "ev_seis",
    "tpi5",               # topographic position index from det_elev (5 px ring)
    "curv",               # Laplacian of det_elev at sigma=2 (scarp curvature)
    "rough",              # local rugosity of det_elev (std in 3x3)
)


def _robust_standardise(a: np.ndarray, mask: np.ndarray) -> np.ndarray:
    v = a[mask]
    med = float(np.median(v))
    q1, q3 = np.percentile(v, [25.0, 75.0])
    scale = float(q3 - q1) or 1.0
    return (a - med) / scale


def _structure_tensor(a: np.ndarray):
    gx = gaussian_filter(a, SIGMA_GRAD, order=(1, 0), mode="nearest")
    gy = gaussian_filter(a, SIGMA_GRAD, order=(0, 1), mode="nearest")
    jxx = gaussian_filter(gx * gx, SIGMA_TENSOR, mode="nearest")
    jyy = gaussian_filter(gy * gy, SIGMA_TENSOR, mode="nearest")
    jxy = gaussian_filter(gx * gy, SIGMA_TENSOR, mode="nearest")
    tmp = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0))
    l1 = 0.5 * (jxx + jyy + tmp)
    l2 = 0.5 * (jxx + jyy - tmp)
    coh = (l1 - l2) / (l1 + l2 + EPS)
    theta = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy)
    ev = np.sqrt(np.maximum(l1, 0.0)) * coh
    del gx, gy, jxx, jyy, jxy, tmp
    return ev, theta, coh, l1


def _band_evidence(stack, name: str, footprint: np.ndarray):
    a = band(stack, name, footprint)
    a = _robust_standardise(a, footprint)
    ev, theta, coh, l1 = _structure_tensor(a)
    return ev, theta, coh


def build(footprint: np.ndarray | None = None, out_dir: Path | None = None,
          force: bool = False, verbose: bool = True,
          window: tuple[int, int, int, int] | None = None) -> Path:
    """Compute and cache the feature channels as ``<out_dir>/<channel>.npy`` (float32).

    ``window`` = (row0, row1, col0, col1) restricts the computation to a crop; it exists so
    the identical code path can be smoke-tested on a small window before the full run.
    """
    out_dir = Path(out_dir or FEATURE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    if window is None:
        missing = [c for c in CHANNELS if not (out_dir / f"{c}.npy").exists()]
        if not missing and not force:
            if verbose:
                print(f"[features] all {len(CHANNELS)} channels cached in {out_dir}")
            return out_dir

    if window is None:
        labels = read_labels()
        footprint = footprint_from(labels) if footprint is None else footprint
        stack = stack_memmap()
    else:
        r0, r1, c0, c1 = window
        labels = read_labels()[r0:r1, c0:c1]
        footprint = footprint_from(labels) if footprint is None else footprint
        stack = np.asarray(stack_memmap()[r0:r1, c0:c1, :])

    acc_ev = np.zeros(footprint.shape, np.float32)
    acc_cos = np.zeros(footprint.shape, np.float32)
    acc_sin = np.zeros(footprint.shape, np.float32)
    acc_w = np.zeros(footprint.shape, np.float32)
    acc_coh = np.zeros(footprint.shape, np.float32)
    fam_cos: dict[str, np.ndarray] = {}
    fam_sin: dict[str, np.ndarray] = {}
    fam_w: dict[str, np.ndarray] = {}

    for fam, names in FAMILIES.items():
        f_ev = np.zeros(footprint.shape, np.float32)
        f_cos = np.zeros(footprint.shape, np.float32)
        f_sin = np.zeros(footprint.shape, np.float32)
        for name in names:
            ev, theta, coh = _band_evidence(stack, name, footprint)
            scale = float(np.percentile(ev[footprint], 99.0)) or 1.0
            ev = (ev / scale).astype(np.float32)
            f_ev += ev / len(names)
            f_cos += (ev * np.cos(2.0 * theta)).astype(np.float32)
            f_sin += (ev * np.sin(2.0 * theta)).astype(np.float32)
            acc_coh += coh.astype(np.float32)
            if verbose:
                print(f"[features] {name:20s} family={fam:7s} p99(ev)={scale:.4g}")
            del ev, theta, coh
        np.save(out_dir / f"ev_{fam}.npy", f_ev)
        fam_cos[fam] = f_cos
        fam_sin[fam] = f_sin
        fam_w[fam] = np.sqrt(f_cos * f_cos + f_sin * f_sin)
        acc_ev += f_ev
        acc_cos += f_cos
        acc_sin += f_sin
        acc_w += fam_w[fam]
        del f_ev, f_cos, f_sin

    np.save(out_dir / "ev.npy", acc_ev)
    np.save(out_dir / "cos2t.npy", (acc_cos / (acc_w + EPS)).astype(np.float32))
    np.save(out_dir / "sin2t.npy", (acc_sin / (acc_w + EPS)).astype(np.float32))
    np.save(out_dir / "order_R.npy", (acc_w / (acc_ev + EPS)).astype(np.float32))
    np.save(out_dir / "coh.npy", (acc_coh / float(len(_all_bands()))).astype(np.float32))

    # --- topographic extras (all from the provided detrended elevation band) ---
    elev = _robust_standardise(band(stack, "det_elev", footprint), footprint)
    sm = gaussian_filter(elev, 1.0, mode="nearest")
    ring = gaussian_filter(elev, 3.0, mode="nearest")
    np.save(out_dir / "tpi5.npy", (sm - ring).astype(np.float32))
    np.save(out_dir / "curv.npy", laplace(gaussian_filter(elev, 2.0, mode="nearest")).astype(np.float32))
    loc = gaussian_filter(elev * elev, 1.0, mode="nearest") - sm * sm
    np.save(out_dir / "rough.npy", np.sqrt(np.maximum(loc, 0.0)).astype(np.float32))
    return out_dir


def _all_bands() -> tuple[str, ...]:
    out: list[str] = []
    for names in FAMILIES.values():
        out.extend(names)
    return tuple(out)


def load(name: str, out_dir: Path | None = None) -> np.ndarray:
    out_dir = Path(out_dir or FEATURE_DIR)
    return np.load(out_dir / f"{name}.npy", mmap_mode="r")


def load_all(names: tuple[str, ...] = CHANNELS, out_dir: Path | None = None) -> dict[str, np.ndarray]:
    return {n: np.asarray(load(n, out_dir)) for n in names}
