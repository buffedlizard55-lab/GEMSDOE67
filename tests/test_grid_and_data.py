"""Grid/IO facts, each re-read from the hash-pinned competition rasters."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems67 import grid  # noqa: E402
from gems67.dataio import DATA_DIR, write_submission  # noqa: E402

REGISTRY = json.loads((ROOT / "data" / "registry.json").read_text())


def test_registry_pins_match_grid_module():
    assert REGISTRY["grid"]["epsg"] == grid.EPSG
    assert tuple(REGISTRY["grid"]["shape"]) == grid.GRID_SHAPE
    assert tuple(REGISTRY["grid"]["transform"]) == grid.TRANSFORM
    assert REGISTRY["metric"]["alpha"] == grid.ALPHA
    assert REGISTRY["metric"]["beta"] == grid.BETA
    assert tuple(REGISTRY["bands"]) == grid.BAND_NAMES


@pytest.mark.skipif(not (DATA_DIR / "labels.tif").exists(), reason="competition data not present")
def test_labels_counts_match_the_published_provenance():
    import tifffile

    a = tifffile.TiffFile(DATA_DIR / "labels.tif").pages[0].asarray()
    assert a.shape == grid.GRID_SHAPE
    assert int((a == -1).sum()) == 7111787
    assert int((a == 0).sum()) == 5106385
    assert int((a == 1).sum()) == 60988


@pytest.mark.skipif(not (DATA_DIR / "sample_submission.tif").exists(),
                    reason="competition data not present")
def test_sample_submission_is_the_catalogue_rasterised():
    """The organizers' sample puts 1.0 exactly on the mapped faults, NaN outside."""
    import tifffile

    s = tifffile.TiffFile(DATA_DIR / "sample_submission.tif").pages[0].asarray()
    lab = tifffile.TiffFile(DATA_DIR / "labels.tif").pages[0].asarray()
    assert np.array_equal(s == 1.0, lab == 1)
    assert np.array_equal(np.isnan(s), lab == -1)
    assert np.array_equal(s == 0.0, lab == 0)


def test_write_and_validate_round_trip(tmp_path, monkeypatch):
    """A tiny synthetic raster written with the real writer keeps its georeferencing."""
    monkeypatch.setattr(grid, "GRID_SHAPE", (16, 12))
    from gems67 import dataio

    monkeypatch.setattr(dataio, "GRID_SHAPE", (16, 12))
    v = np.zeros((16, 12), np.float32)
    v[4:8, 3:6] = 1.0
    v[:, 10:] = np.nan
    out = tmp_path / "tiny.tif"
    dataio.write_submission(out, v, nodata=np.nan)
    rep = dataio.validate_submission(out)
    assert rep["shape"] == [16, 12]
    assert rep["dtype"] == "float32"
    assert rep["pixel_scale"][:2] == [100.0, 100.0]
    assert rep["tiepoint"][3:5] == [243350.0, 4508550.0]
    assert rep["positive_cells"] == 12
    assert rep["any_out_of_range"] is False
    if "error" not in rep.get("gdal", {}):
        assert rep["gdal"]["crs"] == "EPSG:32611"
