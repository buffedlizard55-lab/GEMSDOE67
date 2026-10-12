"""The shipped artifact must satisfy the published submission format, read back from disk."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DOWNLOADS = ROOT / "docs" / "downloads"
PRIMARY = "gemsdoe67-ovtr-ml-cover-tau3p0-20261012"
DATA = Path("/tmp/gems_data")
HAS_DATA = (DATA / "labels.tif").exists() and (DATA / "labels.tif").stat().st_size > 0
needs_data = pytest.mark.skipif(not HAS_DATA,
                                reason="competition rasters (login-walled) are not in this checkout")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


@pytest.mark.skipif(not (DOWNLOADS / f"{PRIMARY}-nan.tif").exists(),
                    reason="artifact not built in this checkout")
def test_primary_artifact_header_matches_its_receipt():
    """Readable without the login-walled inputs: bytes, hash, shape, dtype, value range."""
    import tifffile

    rep = json.loads((DOWNLOADS / f"checks-{PRIMARY}.json").read_text())
    p = DOWNLOADS / f"{PRIMARY}-nan.tif"
    assert sha256(p) == rep["files"]["nan"]["sha256"]
    assert p.stat().st_size == rep["files"]["nan"]["bytes"]
    with tifffile.TiffFile(p) as t:
        a = t.pages[0].asarray()
    assert a.shape == (3730, 3292)
    assert a.dtype == np.float32
    assert rep["files"]["nan"]["positive_cells"] == int((a > 0.5).sum())


@needs_data
@pytest.mark.skipif(not (DOWNLOADS / f"{PRIMARY}-nan.tif").exists(),
                    reason="artifact not built in this checkout")
def test_primary_artifact_is_a_legal_submission():
    import tifffile

    rep = json.loads((DOWNLOADS / f"checks-{PRIMARY}.json").read_text())
    p = DOWNLOADS / f"{PRIMARY}-nan.tif"

    with tifffile.TiffFile(DATA / "labels.tif") as lab:
        labels = lab.pages[0].asarray()
    with tifffile.TiffFile(p) as t:
        a = t.pages[0].asarray()

    assert a.shape == (3730, 3292)
    assert a.dtype == np.float32
    footprint = labels != -1
    inside = a[footprint]
    assert np.isfinite(inside).all(), "no NaN inside the footprint"
    assert inside.min() >= 0.0 and inside.max() <= 1.0
    assert np.isnan(a[~footprint]).all(), "NaN only outside the footprint"
    assert set(np.unique(inside)) <= {0.0, 1.0}, "binary emission"
    assert int((inside > 0).sum()) == rep["files"]["nan"]["positive_cells"]


@pytest.mark.skipif(not (DOWNLOADS / f"{PRIMARY}-zero.tif").exists(),
                    reason="artifact not built in this checkout")
def test_all_finite_twin_carries_no_nan_and_no_nodata_tag():
    import tifffile

    p = DOWNLOADS / f"{PRIMARY}-zero.tif"
    with tifffile.TiffFile(p) as t:
        a = t.pages[0].asarray()
        names = {tg.name for tg in t.pages[0].tags.values()}
    assert np.isfinite(a).all()
    assert a.min() >= 0.0 and a.max() <= 1.0
    assert "GDAL_NODATA" not in names
