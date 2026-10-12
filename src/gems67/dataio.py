"""Reading the pinned competition rasters, and writing a legal submission GeoTIFF.

Verified file facts (read back from the hash-pinned bytes; see data/registry.json):

======================  ==================  ================================================
file                    sha256 (prefix)     structure
======================  ==================  ================================================
training_features.tif   4371c82e3b83...     3730 x 3292 x 19 float32, LZW, 19 bands interleaved
                                            (PlanarConfiguration=1), RowsPerStrip=1,
                                            GDAL_NODATA=-3.4028234663852886e+38
labels.tif              7ba308ccdc44...     3730 x 3292 int8, values {-1 (outside), 0, 1},
                                            GDAL_NODATA=-1; 60 988 positives
sample_submission.tif   2176d08e485a...     3730 x 3292 float32, LZW, RowsPerStrip=1,
                                            NaN outside the footprint, GDAL_NODATA=nan,
                                            1.0 exactly on the 60 988 catalogue pixels
======================  ==================  ================================================

The sample submission is the catalogue rasterised: it puts 1.0 on the mapped faults and 0.0
elsewhere inside the footprint.  The organizers describe it as "a sample submission that
predicts total fault absence", which is only consistent with the official statement that
known-fault pixels are masked out of every metric term (forum thread 11516) — the sample
therefore scores exactly 0 in the scored domain.  That is the independent corroboration of
the masking rule used throughout this repository.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import tifffile

from .grid import (BAND_INDEX, BAND_NAMES, EPSG, FEATURE_NODATA, GRID_SHAPE, PIXEL_SIZE_M,
                   TRANSFORM)

DATA_DIR = Path(os.environ.get("GEMS67_DATA", "/tmp/gems_data"))
FEATURES_TIF = DATA_DIR / "training_features.tif"
LABELS_TIF = DATA_DIR / "labels.tif"
STACK_NPY = DATA_DIR / "stack.npy"
FEATURE_DIR = DATA_DIR / "features"

#: GeoKeys of the organizer rasters, copied verbatim (GeoKeyDirectoryTag + GeoAsciiParamsTag).
GEOKEY_DIRECTORY = (1, 1, 0, 7, 1024, 0, 1, 1, 1025, 0, 1, 1, 1026, 34737, 22, 0,
                    2049, 34737, 7, 22, 2054, 0, 1, 9102, 3072, 0, 1, 32611, 3076, 0, 1, 9001)
GEOASCII = "WGS 84 / UTM zone 11N|WGS 84|"


def read_labels(path: Path | None = None) -> np.ndarray:
    """Catalogue raster: int8 with -1 outside the footprint, 1 on mapped faults."""
    with tifffile.TiffFile(path or LABELS_TIF) as t:
        return t.pages[0].asarray()


def footprint_from(labels: np.ndarray) -> np.ndarray:
    """Boolean footprint = valid competition domain (labels != -1)."""
    return labels != -1


def stack_memmap() -> np.ndarray:
    """The 19-band stack as a read-only memmap (rows, cols, bands), float32."""
    if not STACK_NPY.exists():
        raise FileNotFoundError(
            f"{STACK_NPY} missing. Run scripts/prepare_data.py (see README) to decode the "
            "pinned training_features.tif into a memmappable .npy once."
        )
    return np.load(STACK_NPY, mmap_mode="r")


def band(stack: np.ndarray, name: str, footprint: np.ndarray) -> np.ndarray:
    """One band as float32 with the organizer sentinel replaced by nearest-valid neighbours.

    The sentinel ``-3.4028234663852886e+38`` occurs *inside* the footprint (3 061 cells in
    band 1, 3 073 distinct footprint cells across bands; counts read from the pinned file).
    Leaving it in place would dominate every convolution, so it is inpainted by nearest
    valid value (``scipy.ndimage.distance_transform_edt(return_indices=True)``).
    """
    from scipy.ndimage import distance_transform_edt

    idx = BAND_INDEX[name]
    a = np.asarray(stack[:, :, idx], dtype=np.float32)
    bad = ~np.isfinite(a) | (a <= FEATURE_NODATA * 0.5) | ~footprint
    if bad.any():
        ind = distance_transform_edt(bad, return_distances=False, return_indices=True)
        a = a[tuple(ind)]
    a = np.where(footprint, a, np.float32(0.0))
    return np.ascontiguousarray(a, dtype=np.float32)


def write_submission(path: Path, values: np.ndarray, nodata: float | None = np.nan,
                     compress: bool = True) -> dict:
    """Write a single-band float32 EPSG:32611 100 m GeoTIFF that matches the sample's tags.

    ``nodata=np.nan`` reproduces the organizer sample exactly (NaN outside the footprint).
    ``nodata=None`` writes an all-finite raster with no nodata tag.
    """
    values = np.asarray(values, dtype=np.float32)
    if values.shape != GRID_SHAPE:
        raise ValueError(f"expected shape {GRID_SHAPE}, got {values.shape}")
    extratags = [
        (33550, "d", 3, (PIXEL_SIZE_M, PIXEL_SIZE_M, 0.0), False),          # ModelPixelScale
        (33922, "d", 6, (0.0, 0.0, 0.0, TRANSFORM[2], TRANSFORM[5], 0.0), False),  # Tiepoint
        (34735, "H", len(GEOKEY_DIRECTORY), GEOKEY_DIRECTORY, False),       # GeoKeyDirectory
        (34737, "s", 0, GEOASCII, False),                                   # GeoAsciiParams
    ]
    if nodata is not None:
        extratags.append((42113, "s", 0, "nan" if np.isnan(nodata) else repr(float(nodata)), False))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        path, values, photometric="minisblack", dtype=np.float32, planarconfig="contig",
        rowsperstrip=1, compression="lzw" if compress else None, predictor=1 if compress else None,
        extratags=extratags, metadata=None,
    )
    return {"path": str(path), "bytes": path.stat().st_size}


def validate_submission(path: Path) -> dict:
    """Independent re-read of a written file; returns the format receipt dict.

    Two readers are used when available: ``tifffile`` (always) and GDAL via ``rasterio``
    (when installed), so the georeferencing check is not self-referential.
    """
    path = Path(path)
    with tifffile.TiffFile(path) as t:
        page = t.pages[0]
        arr = page.asarray()
        tags = {tg.name: tg.value for tg in page.tags.values()}
    rep: dict = {
        "file": path.name,
        "bytes": path.stat().st_size,
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "nodata_tag": str(tags.get("GDAL_NODATA", None)),
        "pixel_scale": list(tags.get("ModelPixelScaleTag", ())),
        "tiepoint": list(tags.get("ModelTiepointTag", ())),
        "geokeys_present": "GeoKeyDirectoryTag" in tags,
        "compression": str(tags.get("Compression")),
    }
    finite = np.isfinite(arr)
    vals = arr[finite]
    rep.update(
        finite_cells=int(finite.sum()),
        nan_cells=int(np.isnan(arr).sum()),
        min=float(vals.min()) if vals.size else None,
        max=float(vals.max()) if vals.size else None,
        any_out_of_range=bool(vals.size and ((vals < 0).any() or (vals > 1).any())),
        positive_cells=int((vals > 0).sum()),
    )
    try:
        import rasterio

        with rasterio.open(path) as ds:
            rep["gdal"] = {
                "crs": str(ds.crs),
                "shape": [ds.height, ds.width],
                "transform": [ds.transform.a, ds.transform.b, ds.transform.c,
                              ds.transform.d, ds.transform.e, ds.transform.f],
                "dtype": ds.dtypes[0],
                "nodata": ds.nodata,
                "count": ds.count,
            }
    except Exception as exc:  # pragma: no cover - GDAL optional
        rep["gdal"] = {"error": str(exc)}
    return rep


def write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False, default=str) + "\n")
