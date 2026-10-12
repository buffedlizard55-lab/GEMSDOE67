"""Lane-67 feature stack: label-free physical channels on the official 100 m grid.

Everything here is computed from the 19 official GeoDAWN bands (mirrored copy, sha256-pinned in
``registry/data_manifest.json``) plus two *named* auxiliary products whose band meanings are
declared inside the files themselves or in the sibling code that produced them:

* ``geodawn_rad_u8.tif``  band 1 = radiometric K, band 2 = radiometric Th
  (band assignment read from ``60GEMSDOE/scripts/build_features70.py`` lines 133-140,
  ``krad = src.read(1)``, ``th = src.read(2)``).
* ``topo_10m_derived_100m_u8.tif`` 9 bands, names taken from the file's own band tags.

No channel in this module reads ``labels.tif``, ``existing_faults.tif``, ``sample_submission.tif``
or any scored submission, so every channel is safe to evaluate on a spatial holdout.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

H, W = 3730, 3292
OFFICIAL_BANDS = [
    "mag_anom", "rtp", "tmi_hg", "geod_2ndinv", "iso_grav_anom_slope", "tc",
    "geod_shearrate", "geod_dilaterate", "tmi_vg", "deq_n100a15", "iso_grav_anom_vg",
    "det_elev", "iso_grav_anom", "tmi", "depth_to_base_surf", "ieq_n100a15",
    "cond_surf", "iso_grav_anom_hg", "det_elev_slope",
]
# bands whose structure tensor / Hessian line response we compute (index into OFFICIAL_BANDS)
LINE_BANDS = {"det_elev": 11, "tmi": 13, "iso_grav_anom": 12}
SIGMAS = (1.5, 3.0)
FEATURE_NODATA = -1e38


def robust_unit(a: np.ndarray, mask: np.ndarray, lo: float = 1.0, hi: float = 99.0) -> np.ndarray:
    """Percentile-normalise to [0, 1] inside ``mask``; 0 elsewhere. NaN-safe."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = mask & np.isfinite(a)
    if not v.any():
        return out
    qlo, qhi = np.percentile(a[v], [lo, hi])
    if not np.isfinite(qlo) or not np.isfinite(qhi) or qhi <= qlo:
        out[v] = 0.5
        return out
    out[v] = np.clip((a[v] - qlo) / (qhi - qlo), 0.0, 1.0)
    return out


def _filled(a: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Replace non-finite / out-of-mask cells with the in-mask median (no NaN propagation)."""
    v = mask & np.isfinite(a)
    med = float(np.median(a[v])) if v.any() else 0.0
    return np.where(v, a, med).astype(np.float32)


def structure_tensor(a: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (energy, coherence, cos2theta, sin2theta) of the gradient structure tensor.

    theta is the *axial* (undirected) orientation of the local lineament, so the natural
    regression targets are cos 2theta and sin 2theta -- the representation used by the lane brief
    and by Batra et al. (CVPR 2019, doi:10.1109/CVPR.2019.01063) for orientation heads.
    """
    gx = gaussian_filter(a, sigma, order=(0, 1), mode="nearest")
    gy = gaussian_filter(a, sigma, order=(1, 0), mode="nearest")
    jxx = gaussian_filter(gx * gx, sigma, mode="nearest")
    jyy = gaussian_filter(gy * gy, sigma, mode="nearest")
    jxy = gaussian_filter(gx * gy, sigma, mode="nearest")
    tr = jxx + jyy
    diff = jxx - jyy
    root = np.sqrt(np.maximum(0.25 * diff * diff + jxy * jxy, 0.0))
    energy = tr.astype(np.float32)
    coherence = (2.0 * root / np.maximum(tr, 1e-12)).astype(np.float32)
    cos2t = (diff / np.maximum(2.0 * root, 1e-12)).astype(np.float32)
    sin2t = (2.0 * jxy / np.maximum(2.0 * root, 1e-12)).astype(np.float32)
    return energy, coherence, np.clip(cos2t, -1, 1), np.clip(sin2t, -1, 1)


def line_response(a: np.ndarray, sigma: float) -> np.ndarray:
    """Frangi/Sato curvilinear response: -min-eigenvalue of the Hessian (both polarities)."""
    axx = gaussian_filter(a, sigma, order=(0, 2), mode="nearest")
    ayy = gaussian_filter(a, sigma, order=(2, 0), mode="nearest")
    axy = gaussian_filter(a, sigma, order=(1, 1), mode="nearest")
    tmp = np.sqrt(np.maximum((0.5 * (axx - ayy)) ** 2 + axy ** 2, 0.0))
    l1 = 0.5 * (axx + ayy) + tmp
    l2 = 0.5 * (axx + ayy) - tmp
    small = np.where(np.abs(l1) >= np.abs(l2), l2, l1)
    return (-small).astype(np.float32)


def channel_names() -> list[str]:
    names = list(OFFICIAL_BANDS)
    for b in LINE_BANDS:
        for s in SIGMAS:
            tag = f"{b}_s{str(s).replace('.', '')}"
            names += [f"coh_{tag}", f"cos2t_{tag}", f"sin2t_{tag}", f"line_{tag}"]
    names += ["rad_k", "rad_th", "rad_k_over_th"]
    names += ["topo_slope_p90", "topo_slope_max", "topo_steep_frac", "topo_slope_std",
              "topo_relief_local", "topo_curv_prof_absmax", "topo_aspect_coherence",
              "topo_hs_lineament", "topo_dem_mean"]
    return names


def build(features_path: Path, rad_path: Path, topo_path: Path, out_dir: Path,
          footprint: np.ndarray | None = None, verbose: bool = True) -> dict:
    """Build the float16 channel cube ``out_dir/channels.f16.npy`` (memmap-able) + meta json."""
    import rasterio

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = channel_names()
    cube = np.lib.format.open_memmap(
        out_dir / "channels.f16.npy", mode="w+", dtype=np.float16, shape=(H, W, len(names)))

    with rasterio.open(features_path) as src:
        assert (src.height, src.width) == (H, W), f"unexpected grid {src.height}x{src.width}"
        band1 = src.read(1).astype(np.float64)
        fp = np.isfinite(band1) & (band1 > FEATURE_NODATA) if footprint is None else footprint
        raw = {}
        for i, nm in enumerate(OFFICIAL_BANDS, start=1):
            b = src.read(i).astype(np.float32)
            b[~np.isfinite(b) | (b < FEATURE_NODATA)] = np.nan
            raw[nm] = b
            u = robust_unit(np.nan_to_num(b, nan=0.0), fp & np.isfinite(b))
            cube[:, :, i - 1] = u.astype(np.float16)
            if verbose:
                print(f"  band {i:2d} {nm:22s} finite={int(np.isfinite(b).sum()):8d}", flush=True)
        del band1

        k = len(OFFICIAL_BANDS)
        for bname, _idx in LINE_BANDS.items():
            a = _filled(raw[bname], fp)
            # per-band scale normalisation so that sigma comparisons are amplitude-fair
            sd = float(np.std(a[fp])) or 1.0
            a = (a / sd).astype(np.float32)
            for s in SIGMAS:
                _e, coh, c2, s2 = structure_tensor(a, s)
                ln = line_response(a, s)
                lq = np.percentile(ln[fp], 99.5) if fp.any() else 1.0
                ln = np.clip(ln / max(float(lq), 1e-9), 0.0, 1.0).astype(np.float32)
                for arr in (coh, c2, s2, ln):
                    cube[:, :, k] = arr.astype(np.float16)
                    k += 1
                if verbose:
                    print(f"  tensor {bname} sigma={s} done ({k}/{len(names)})", flush=True)
        del raw

    # --- auxiliary named products -----------------------------------------------------------
    def _read_u8(path: Path, nb: int):
        with rasterio.open(path) as src:
            assert (src.height, src.width) == (H, W), f"{path.name} off-grid {src.height}x{src.width}"
            out = []
            for i in range(1, nb + 1):
                v = src.read(i).astype(np.float32)
                v[v <= 0] = np.nan  # declared nodata = 0 for these products
                out.append(v)
        return out

    krad, th = _read_u8(rad_path, 2)
    cube[:, :, k] = robust_unit(np.nan_to_num(krad), fp & np.isfinite(krad)).astype(np.float16); k += 1
    cube[:, :, k] = robust_unit(np.nan_to_num(th), fp & np.isfinite(th)).astype(np.float16); k += 1
    ratio = np.where(np.isfinite(krad) & np.isfinite(th) & (th > 0), krad / th, np.nan)
    cube[:, :, k] = robust_unit(np.nan_to_num(ratio), fp & np.isfinite(ratio)).astype(np.float16); k += 1

    topo = _read_u8(topo_path, 9)
    for t in topo:
        cube[:, :, k] = robust_unit(np.nan_to_num(t), fp & np.isfinite(t)).astype(np.float16); k += 1

    assert k == len(names), f"channel bookkeeping bug: wrote {k}, declared {len(names)}"
    np.save(out_dir / "footprint.npy", fp)
    meta = {
        "shape_hw": [H, W], "n_channels": len(names), "channels": names,
        "dtype": "float16", "file": "channels.f16.npy",
        "footprint_cells": int(fp.sum()),
        "sources": {
            "official_19_bands": str(features_path),
            "geodawn_rad_u8": str(rad_path),
            "topo_10m_derived_100m_u8": str(topo_path),
        },
    }
    (out_dir / "channels_meta.json").write_text(json.dumps(meta, indent=2))
    cube.flush()
    del cube
    return meta


def load(out_dir: Path):
    """Return (memmap cube float16 -> float32 on demand, footprint, names)."""
    out_dir = Path(out_dir)
    meta = json.loads((out_dir / "channels_meta.json").read_text())
    cube = np.load(out_dir / meta["file"], mmap_mode="r")
    fp = np.load(out_dir / "footprint.npy")
    return cube, fp, meta["channels"]
