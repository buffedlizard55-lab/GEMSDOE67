"""Lane-67 unit tests: physics conventions, decode geometry, budget mechanics, gates.

Everything here is synthetic and small; the full-grid instruments live in
``scripts/run_lane_ef0d41a0.py`` and are recorded as JSON evidence, not re-run in CI.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

ROOT_ = Path(__file__).resolve().parents[1]
HAS_BRIDGE = (ROOT_ / "data" / "bridge" / "existing_faults.tif").exists()


def _artifacts_available():
    if not HAS_BRIDGE:
        return False
    try:
        from gems57 import grid as _G
        _G.load_grid()
    except Exception:                                   # noqa: BLE001 - any load failure skips
        return False
    return True


DATA = pytest.mark.skipif(not _artifacts_available(),
                          reason="pinned bridge rasters absent (CI restores them separately)")

from lane_ef0d41a0 import arms as A
from lane_ef0d41a0 import decode as D
from lane_ef0d41a0 import fields as F
from lane_ef0d41a0 import heads as HD

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# orientation convention                                                     #
# --------------------------------------------------------------------------- #
def test_axial_frame_conventions():
    """Gradient along y -> horizontal tangent (cos2=+1); along x -> cos2=-1."""
    one = np.ones((4, 4), np.float32)
    zero = np.zeros((4, 4), np.float32)
    cos2, sin2, coh = F.axial_frame(2.0 * one, zero, zero)      # jyy only: grad along y
    assert np.allclose(cos2, 1.0) and np.allclose(sin2, 0.0) and np.allclose(coh, 1.0)
    cos2, sin2, coh = F.axial_frame(zero, 2.0 * one, zero)      # jxx only: grad along x
    assert np.allclose(cos2, -1.0) and np.allclose(sin2, 0.0) and np.allclose(coh, 1.0)
    cos2, sin2, _ = F.axial_frame(one, one, 0.5 * one)          # 45 degrees
    assert np.allclose(cos2, 0.0) and np.allclose(sin2, -1.0)
    # axial symmetry: (cos2, sin2) and its negation describe the same line
    c2a, s2a, _ = F.axial_frame(3.0 * one, one, 0.2 * one)
    c2b, s2b, _ = F.axial_frame(3.0 * one, one, -0.2 * one)
    assert np.isclose(c2a[0, 0], c2b[0, 0]) and np.isclose(s2a[0, 0], -s2b[0, 0])


def test_tensor_at_scale_on_horizontal_ridge():
    """A horizontally varying image has a horizontally directed gradient."""
    y, x = np.mgrid[0:64, 0:64]
    img = np.cos(2 * np.pi * x / 16.0).astype(np.float32)
    jyy, jxx, jyx, energy = F.tensor_at_scale(img, np.ones_like(img, bool), 1.5)
    cos2, sin2, coh = F.axial_frame(jyy, jxx, jyx)
    core = (slice(8, 56), slice(8, 56))
    assert np.median(cos2[core]) < -0.9          # gradient along x -> cos2 = -1
    assert np.median(coh[core]) > 0.9
    assert energy[core].mean() > 0


def test_trace_frame_tangent_frame_is_unit():
    """trace_frame must return an axial frame with unit coherence on a clean line."""
    mask = np.zeros((40, 40), bool)
    mask[:, 20] = True                            # vertical line, 1 px wide
    cos2, sin2, support = HD.trace_frame(mask, smooth_px=1.0)
    norm = np.sqrt(cos2 ** 2 + sin2 ** 2)
    assert np.allclose(norm[norm > 0.5], 1.0, atol=1e-4)   # unit wherever defined
    assert cos2[20, 20] < -0.9                    # vertical tangent -> cos2 = -1
    assert norm[20, 20] > 0.99 and norm[20, 30] < 0.05     # decays away from the trace


# --------------------------------------------------------------------------- #
# decode geometry                                                            #
# --------------------------------------------------------------------------- #
def test_nms_across_strike_keeps_single_peak():
    """A ramp across strike keeps exactly one cell per strike column."""
    ev = np.tile(np.linspace(0, 1, 21, dtype=np.float32), (21, 1))   # varies along x
    cos2 = -np.ones_like(ev)                     # tangent vertical -> normal along x
    sin2 = np.zeros_like(ev)
    keep = D.nms_across_strike(ev, cos2, sin2, np.ones_like(ev, bool))
    assert keep[5, :].sum() == 1
    assert int(keep.sum()) == ev.shape[0]


def test_march_bridges_a_gap():
    """Hysteresis must follow a straight line through a short low-evidence gap."""
    shape = (60, 60)
    ev = np.zeros(shape, np.float32)
    ev[30, 5:55] = 1.0
    ev[30, 25:29] = 0.5                         # a 4 px gap: below hi (1.0), above lo (0.35)
    cos2 = np.ones(shape, np.float32)           # horizontal tangent
    sin2 = np.zeros(shape, np.float32)
    guard = np.ones(shape, bool)
    out = D.march(ev, cos2, sin2, guard, allow_extension=False, max_seeds=500)
    trace = out["trace"]
    assert trace[30, 20] and trace[30, 26]
    assert trace[30, 5] and trace[30, 50]
    assert not trace[10, 10]


def test_allowed_away_from_catalogue_masks_the_bar():
    """The 200 m exclusion is exact: 2 px around the catalogue is removed."""
    cat = np.zeros((30, 30), bool)
    cat[15, 15] = True
    fp = np.ones_like(cat)
    allowed = D.allowed_away_from_catalogue(cat, fp, exclude_px=2.0)
    assert not allowed[15, 15] and not allowed[15, 17] and not allowed[13, 15]
    assert allowed[15, 18] and allowed[12, 15]


# --------------------------------------------------------------------------- #
# budget mechanics                                                           #
# --------------------------------------------------------------------------- #
def test_tile_ranking_and_prefix_are_a_partition_and_an_order():
    rng = np.random.default_rng(0)
    credit = rng.random((30, 30)).astype(np.float32)
    allowed = np.ones((30, 30), bool)
    ranked = A.tile_ranking(credit, allowed, tile_px=3)
    dots = ranked > 0
    assert dots.sum() == 100                    # 10 x 10 tiles
    assert sorted(ranked[dots].tolist()) == list(range(1, dots.sum() + 1))
    # the ranking must be non-increasing in the *tile maximum* of each emitted dot
    order = np.argsort(ranked[dots])
    ys, xs = np.nonzero(dots)
    tile_max = np.array([
        credit[max(0, y - y % 3): y - y % 3 + 3, max(0, x - x % 3): x - x % 3 + 3].max()
        for y, x in zip(ys, xs)])
    assert np.all(np.diff(tile_max[order]) <= 1e-6)


def test_emit_prefix_returns_exactly_the_budget():
    from gems57 import emit
    rng = np.random.default_rng(1)
    ranked = np.zeros((40, 40), np.int32)
    pick = rng.choice(40 * 40, 200, replace=False)
    ranked.ravel()[pick] = np.arange(1, 201, dtype=np.int32)
    dots = emit.emit_prefix(ranked, 37)
    assert int(dots.sum()) == 37


def test_nms_before_ranking_is_not_identity():
    """Guard against a silent no-op: NMS must actually thin a thick ridge."""
    shape = (40, 40)
    ev = np.zeros(shape, np.float32)
    ev[18:22, 5:35] = 1.0                       # 4 px thick horizontal bar
    cos2 = np.ones(shape, np.float32)
    sin2 = np.zeros(shape, np.float32)
    keep = D.nms_across_strike(ev, cos2, sin2, np.ones(shape, bool))
    assert 0 < int(keep.sum()) <= 2 * 30


# --------------------------------------------------------------------------- #
# gates and artifacts                                                        #
# --------------------------------------------------------------------------- #
def test_prior_index_schema_and_hashes():
    index = json.loads((ROOT / "registry" / "prior_index.json").read_text())
    assert index["schema"] == "lane67-prior-index-v1"
    assert index["complete_accessible_scan"] is False       # honest: 51 of 751
    assert index["rasters"], "index must not be empty"
    for rec in index["rasters"]:
        assert {"repo_first", "sources", "cache_file", "sha256"} <= set(rec)
        path = ROOT / rec["cache_file"]
        assert path.exists(), rec["cache_file"]
    rec = index["rasters"][0]
    h = hashlib.sha256((ROOT / rec["cache_file"]).read_bytes()).hexdigest()
    assert h == rec["sha256"] or rec["provenance"] == "upstream-sha256"


@DATA
def test_shipped_raster_passes_validation_and_range():
    from gems57 import grid as G
    from gems57 import validate as V
    subs = sorted((ROOT / "submissions").glob("*.tif"))
    if not subs:
        pytest.skip("no shipped raster yet")
    g = G.load_grid()
    out = V.validate(subs[-1], g.footprint, g.catalogue)
    assert out["all_checks_passed"], out["checks"]
    assert out["min"] >= 0.0 and out["max"] <= 1.0
    assert out["checks"]["range_0_1_guaranteed"]


@DATA
def test_validation_rejects_out_of_range_negative_control(tmp_path):
    """The prior user-visible failure mode: values must be within [0, 1]."""
    import rasterio
    from gems57 import grid as G
    from gems57 import validate as V
    g = G.load_grid()
    path = tmp_path / "cc-bad-range-zeros.tif"
    pred = np.zeros(g.footprint.shape, np.float32)
    pred[g.footprint] = 1.5
    with rasterio.open(path, "w", driver="GTiff", height=pred.shape[0], width=pred.shape[1],
                       count=1, dtype="float32", crs="EPSG:32611",
                       transform=G.TRANSFORM, nodata=None) as dst:
        dst.write(pred, 1)
    out = V.validate(path, g.footprint, g.catalogue)
    assert not out["all_checks_passed"]
    assert out["checks"]["range_0_1_guaranteed"] is False
