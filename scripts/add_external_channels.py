#!/usr/bin/env python3
"""Add lineament-evidence channels derived from public USGS products outside the 19-band stack.

Products (owner-mirrored, grid-verified here: 3730 x 3292, EPSG:32611, 100 m, tiepoint
243350 / 4508550 — identical to the competition grid, checked by re-reading the tags):

  lidar_scarp_features_u8.tif  12 bands derived from USGS 3DEP 1 m lidar
                               (ex_max, ex_mean, step_max, lapneg_max, lappos_max,
                                downface_max, upface_max, cross_max, relief, coh100,
                                strike, valid); source DOI 10.5066/P93LGLVQ area 1+2 DEM
  geodawn_rad_u8.tif           4 bands K, Th, U, TC radiometrics (GeoDAWN release)
  geodawn_extensions_u8.tif    4 bands ThK, UK, UTh ratios and TMI upward-continued 150 m

The competition explicitly allows additional data sources ("Participants are allowed to use
any additional data sources, provided that the participants possess a license that permits the
data to be used in this challenge", problem description, External datasets).

These channels are *derived products of USGS data*, mirrored by the group's own CI, not
organizer files: their provenance is recorded in data/registry.json and docs/research/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import tifffile
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SRC = Path("/tmp/gemsdoe24/data/external")
OUT = Path("/tmp/gems_data/features")

#: channel name -> (tif, band index) of the evidence sources
BANDS = {
    "ex_max": ("lidar_scarp_features_u8.tif", 0),
    "step_max": ("lidar_scarp_features_u8.tif", 2),
    "downface_max": ("lidar_scarp_features_u8.tif", 5),
    "upface_max": ("lidar_scarp_features_u8.tif", 6),
    "lapneg_max": ("lidar_scarp_features_u8.tif", 3),
    "lappos_max": ("lidar_scarp_features_u8.tif", 4),
    "cross_max": ("lidar_scarp_features_u8.tif", 7),
    "K": ("geodawn_rad_u8.tif", 0),
    "Th": ("geodawn_rad_u8.tif", 1),
    "TC": ("geodawn_rad_u8.tif", 3),
    "ThK": ("geodawn_extensions_u8.tif", 0),
    "UK": ("geodawn_extensions_u8.tif", 1),
    "UTh": ("geodawn_extensions_u8.tif", 2),
}

FAMILIES = {
    "lidar": ("ex_max", "step_max", "downface_max", "upface_max", "lapneg_max", "lappos_max",
              "cross_max"),
    "rad": ("K", "Th", "TC"),
    "ext": ("ThK", "UK", "UTh"),
}

EPS = 1e-9
SIGMA_GRAD = 1.0
SIGMA_TENSOR = 2.0


def structure_evidence(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gx = gaussian_filter(a, SIGMA_GRAD, order=(1, 0), mode="nearest")
    gy = gaussian_filter(a, SIGMA_GRAD, order=(0, 1), mode="nearest")
    jxx = gaussian_filter(gx * gx, SIGMA_TENSOR, mode="nearest")
    jyy = gaussian_filter(gy * gy, SIGMA_TENSOR, mode="nearest")
    jxy = gaussian_filter(gx * gy, SIGMA_TENSOR, mode="nearest")
    tmp = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0))
    l1 = 0.5 * (jxx + jyy + tmp)
    l2 = 0.5 * (jxx + jyy - tmp)
    coh = (l1 - l2) / (l1 + l2 + EPS)
    ev = np.sqrt(np.maximum(l1, 0.0)) * coh
    del gx, gy, jxx, jyy, jxy, tmp, l1, l2
    return ev, coh


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    valid = np.asarray(tifffile.TiffFile(SRC / "lidar_scarp_features_u8.tif")
                       .pages[0].asarray()[:, :, 11], bool)
    np.save(OUT / "lidar_valid.npy", valid)

    fam_ev: dict[str, np.ndarray] = {}
    for fam, names in FAMILIES.items():
        acc = np.zeros(valid.shape, np.float32)
        for name in names:
            tif, bi = BANDS[name]
            a = np.asarray(tifffile.TiffFile(SRC / tif).pages[0].asarray()[:, :, bi],
                           np.float32)
            m = a > 0
            if m.sum() < 1e5:
                print(f"[ext] {name}: too few valid pixels, skipped")
                continue
            v = a[m]
            a = (a - np.median(v)) / (np.percentile(v, 75) - np.percentile(v, 25) or 1.0)
            ev, coh = structure_evidence(a)
            p99 = float(np.percentile(ev[valid], 99.0)) or 1.0
            acc += (ev / p99).astype(np.float32) / len(names)
            print(f"[ext] {name:14s} family={fam:5s} p99(ev)={p99:.4g} valid={int(m.sum())}")
            del a, ev, coh
        fam_ev[fam] = acc
        np.save(OUT / f"ev_{fam}.npy", acc)

    total = sum(fam_ev.values())
    np.save(OUT / "ev_ext_all.npy", total.astype(np.float32))
    for base in ("ev_lidar", "ev_rad", "ev_ext_all"):
        a = np.load(OUT / f"{base}.npy", mmap_mode="r")
        s = gaussian_filter(np.asarray(a, np.float32), 3.0, mode="nearest").astype(np.float32)
        np.save(OUT / f"{base}_s3.npy", s)
        del a, s
    print("[ext] wrote ev_lidar, ev_rad, ev_ext_all (+_s3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
