#!/usr/bin/env python3
"""Independent verification of a shipped artifact, read-only, with a second GDAL build.

Every assertion is recomputed from the bytes on disk with `rasterio` (GDAL 3.10.3) -- not
with the writer's own library -- so a bug in the writer cannot hide here.  The report is
appended to evidence/verify_<artifact>.json and the exit code is non-zero if any check fails.

Usage: python scripts/verify_artifact.py [--artifact STEM] [--allow-fail]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATA = Path("/tmp/gems_data")
DOWNLOADS = ROOT / "docs" / "downloads"

EXPECT_SHAPE = (3730, 3292)
EXPECT_CRS = "EPSG:32611"
EXPECT_TRANSFORM = (100.0, 0.0, 243350.0, 0.0, -100.0, 4508550.0)
EXPECT_CATALOGUE_PX = 60988
EXPECT_FOOTPRINT_PX = 5167373


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def check(name: str, ok: bool, detail) -> dict:
    return {"check": name, "ok": bool(ok), "detail": detail}


def main() -> int:
    import rasterio

    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default="gemsdoe67-ovtr-ml-cover-tau3p0-20261012")
    ap.add_argument("--allow-fail", action="store_true")
    args = ap.parse_args()
    stem = args.artifact

    labels = np.load(DATA / "labels.npy") if (DATA / "labels.npy").exists() else None
    if labels is None:
        import tifffile

        with tifffile.TiffFile(DATA / "labels.tif") as t:
            labels = t.pages[0].asarray()
        np.save(DATA / "labels.npy", labels)
    footprint = labels != -1
    catalogue = labels == 1

    results: list[dict] = []
    files: dict[str, dict] = {}

    with rasterio.open(DOWNLOADS / f"{stem}-nan.tif") as ds:
        a = ds.read(1)
        prof = {
            "driver": ds.driver,
            "count": ds.count,
            "dtype": ds.dtypes[0],
            "shape": [ds.height, ds.width],
            "crs": None if ds.crs is None else ds.crs.to_string(),
            "transform": tuple(ds.transform)[:6],
            "nodata": None if ds.nodata is None else float(ds.nodata),
            "compress": ds.compression.value if ds.compression else None,
        }
        results.append(check("primary driver is GTiff", prof["driver"] == "GTiff", prof["driver"]))
        results.append(check("primary is single band", prof["count"] == 1, prof["count"]))
        results.append(check("primary dtype float32", prof["dtype"] == "float32", prof["dtype"]))
        results.append(check("primary shape", tuple(prof["shape"]) == EXPECT_SHAPE, prof["shape"]))
        results.append(check("primary CRS", prof["crs"] == EXPECT_CRS, prof["crs"]))
        results.append(check("primary transform",
                             tuple(round(v, 6) for v in prof["transform"]) == EXPECT_TRANSFORM,
                             prof["transform"]))
        inside = a[footprint]
        outside = a[~footprint]
        fin_in = np.isfinite(inside)
        results.append(check("no NaN/Inf inside the footprint", bool(fin_in.all()),
                             int((~fin_in).sum())))
        results.append(check("all inside values in [0, 1]",
                             bool(fin_in.all() and inside[fin_in].min() >= 0.0
                                  and inside[fin_in].max() <= 1.0),
                             [float(np.nanmin(inside)), float(np.nanmax(inside))]))
        results.append(check("NaN only outside the footprint", bool(np.isnan(outside).all()),
                             int(np.isfinite(outside).sum())))
        vals = np.unique(inside[fin_in])
        results.append(check("binary emission {0, 1}", set(vals.tolist()) <= {0.0, 1.0},
                             vals.tolist()[:5]))
        dots = a > 0.5
        n_dots = int(dots.sum())
        results.append(check("emission is inside the footprint only",
                             bool((dots & ~footprint).sum() == 0),
                             int((dots & ~footprint).sum())))
        near_cat3 = None
        try:
            from scipy import ndimage as ndi

            d = ndi.distance_transform_edt(~catalogue)
            near_cat3 = float((dots & (d <= 3.0)).sum()) / max(n_dots, 1)
        except Exception as exc:  # pragma: no cover - scipy is present in this env
            print(f"[verify] distance transform skipped: {exc}")
        files["nan"] = {
            "file": f"{stem}-nan.tif",
            "sha256": sha256(DOWNLOADS / f"{stem}-nan.tif"),
            "bytes": (DOWNLOADS / f"{stem}-nan.tif").stat().st_size,
            "profile": prof,
            "positive_cells": n_dots,
            "nan_cells": int(np.isnan(a).sum()),
            "fraction_of_dots_within_3px_of_mapped_fault": near_cat3,
        }

    with rasterio.open(DOWNLOADS / f"{stem}-zero.tif") as ds:
        z = ds.read(1)
        zprof = {
            "count": ds.count,
            "dtype": ds.dtypes[0],
            "shape": [ds.height, ds.width],
            "crs": None if ds.crs is None else ds.crs.to_string(),
            "transform": tuple(ds.transform)[:6],
            "nodata": None if ds.nodata is None else float(ds.nodata),
        }
        results.append(check("twin is finite everywhere", bool(np.isfinite(z).all()),
                             int((~np.isfinite(z)).sum())))
        results.append(check("twin values in [0, 1]",
                             bool(z.min() >= 0.0 and z.max() <= 1.0), [float(z.min()), float(z.max())]))
        results.append(check("twin carries no nodata tag", zprof["nodata"] is None, zprof["nodata"]))
        results.append(check("twin agrees with primary inside the footprint",
                             bool(np.array_equal(z[footprint], np.nan_to_num(a[footprint]))), None))
        results.append(check("twin CRS/transform match primary",
                             zprof["crs"] == EXPECT_CRS
                             and tuple(round(v, 6) for v in zprof["transform"]) == EXPECT_TRANSFORM,
                             [zprof["crs"], zprof["transform"]]))
        files["zero"] = {
            "file": f"{stem}-zero.tif",
            "sha256": sha256(DOWNLOADS / f"{stem}-zero.tif"),
            "bytes": (DOWNLOADS / f"{stem}-zero.tif").stat().st_size,
            "profile": zprof,
        }

    zpath = DOWNLOADS / f"{stem}.zip"
    if zpath.exists():
        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            results.append(check("zip holds exactly one file", len(names) == 1, names))
            member = names[0]
            blob = zf.read(member)
        h_member = hashlib.sha256(blob).hexdigest()
        with zipfile.ZipFile(zpath) as zf, zf.open(names[0]) as fh:
            import io

            with rasterio.open(io.BytesIO(fh.read())) as ds:
                az = ds.read(1)
                zprofile = {"crs": ds.crs.to_string() if ds.crs else None,
                            "shape": [ds.height, ds.width],
                            "transform": tuple(ds.transform)[:6]}
        results.append(check("zip member is the primary raster", h_member == files["nan"]["sha256"],
                             h_member[:16]))
        results.append(check("zip member reads as the same array",
                             bool(np.array_equal(az, a, equal_nan=True)),
                             {"crs": zprofile["crs"], "shape": zprofile["shape"]}))
        files["zip"] = {"file": zpath.name, "sha256": sha256(zpath), "bytes": zpath.stat().st_size,
                        "member": member}

    results.append(check("catalogue pixel count matches the pinned measurement",
                         int(catalogue.sum()) == EXPECT_CATALOGUE_PX, int(catalogue.sum())))
    results.append(check("footprint pixel count matches the pinned measurement",
                         int(footprint.sum()) == EXPECT_FOOTPRINT_PX, int(footprint.sum())))
    results.append(check("the sample submission's 1-cells are exactly the catalogue",
                         _sample_is_catalogue(DATA), None))

    ok = all(r["ok"] for r in results)
    report = {
        "artifact": stem,
        "reader": f"rasterio {rasterio.__version__} / GDAL {rasterio.__gdal_version__} "
                  f"(independent of the writer)",
        "checks": results,
        "files": files,
        "all_checks_pass": ok,
    }
    out = ROOT / "evidence" / f"verify_{stem}.json"
    out.write_text(json.dumps(report, indent=1))
    for r in results:
        print(f"[verify] {'PASS' if r['ok'] else 'FAIL'}  {r['check']}  {r['detail']}")
    print(f"[verify] {'ALL CHECKS PASS' if ok else 'FAILURES PRESENT'} -> {out}")
    return 0 if (ok or args.allow_fail) else 1


def _sample_is_catalogue(data_dir: Path) -> bool:
    """The organizers describe sample_submission.tif as 'predicts total fault absence'.
    If its 1-cells are exactly the mapped catalogue, that only makes sense because known
    fault pixels are excluded from the metric, which is the assumption this build makes."""
    import tifffile

    with tifffile.TiffFile(data_dir / "sample_submission.tif") as t:
        s = t.pages[0].asarray()
    with tifffile.TiffFile(data_dir / "labels.tif") as t:
        lab = t.pages[0].asarray()
    return bool(np.array_equal(s > 0.5, lab == 1))


if __name__ == "__main__":
    raise SystemExit(main())
