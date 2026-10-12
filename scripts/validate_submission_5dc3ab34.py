"""Fail-closed local preflight for a candidate GEMS submission GeoTIFF.

Wraps the vendored shared validator (``gems57.validate`` + ``gems57.gates``)
and re-derives every claim from the bytes on disk.  A PASS here means:

* single-band float32 GeoTIFF on the pinned grid (3730x3292, EPSG:32611,
  100 m, transform (100, 0, 243350, 0, -100, 4508550));
* every cell finite, in [0, 1], and zero outside the official footprint
  (the all-finite export policy shared by ``gates`` and ``validate``) -- a
  file that passes here cannot trip the portal's "Predicted values must be
  in range [0, 1]" error;
* optionally: zero positive mass on the mapped catalogue.

The alternative sample-faithful representation (finite values inside the
footprint, NaN outside, NaN nodata) is checked with ``--allow-outside-nan``
which enforces the same in-footprint contract with the NaN encoding.

A local PASS is NOT organiser acceptance.  It clears the file for download on
the site; uploading to the weekly slot is a separate human/selector step.

Usage::

    PYTHONPATH=src python scripts/validate_submission.py FILE.tif
    PYTHONPATH=src python scripts/validate_submission.py TWIN.tif --allow-outside-nan
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vendor")]

from gems57 import gates, grid as gridmod, validate as vmod  # noqa: E402


def validate_submission(path: Path, *, sample: Path, data_dir: Path,
                        allow_outside_nan: bool = False,
                        catalogue_check: bool = True) -> dict:
    g = gridmod.load_grid(data_dir)
    report = gates.format_report(path, sample, footprint=g.footprint)
    local = vmod.validate(path, g.footprint, g.catalogue if catalogue_check else None)

    import rasterio
    with rasterio.open(path) as ds:
        a = ds.read(1)
        nodata = ds.nodata
    fp = g.footprint
    nan_inside = int(np.isnan(a[fp]).sum())
    finite_outside = np.isfinite(a[~fp])
    range_ok = bool(np.isfinite(a[fp]).all()
                    and (a[fp] >= 0.0).all() and (a[fp] <= 1.0).all())
    if allow_outside_nan:
        # sample-faithful twin: NaN (only) outside, finite [0,1] inside
        twin_ok = bool(nan_inside == 0 and range_ok
                       and np.isnan(a[~fp]).all()
                       and nodata is not None and np.isnan(nodata))
        checks = dict(
            single_band=report.get("bands") == 1,
            dtype_float32=report.get("dtype") == "float32",
            crs_epsg_32611=report.get("crs") == "EPSG:32611",
            shape_matches=(report.get("height"), report.get("width"))
            == (gridmod.HEIGHT, gridmod.WIDTH),
            transform_matches=report.get("transform")
            == [100.0, 0.0, 243350.0, 0.0, -100.0, 4508550.0],
            values_in_0_1_inside_footprint=range_ok,
            nan_only_outside_footprint=twin_ok,
            no_nan_inside_footprint=nan_inside == 0,
            zero_mass_on_catalogue=(
                local.get("on_catalogue_positive_pixels", 1) == 0
                if catalogue_check else True),
        )
    else:
        checks = dict(
            single_band=local["checks"]["single_band"],
            dtype_float32=local["checks"]["dtype_float32"],
            crs_epsg_32611=local["checks"][f"crs_epsg_{gridmod.EPSG}"],
            shape_matches=local["checks"][f"dimensions_{gridmod.HEIGHT}x{gridmod.WIDTH}"],
            transform_matches=local["checks"]["transform_matches_sample_submission"],
            values_in_0_1_inside_footprint=local["checks"]["in_footprint_range_0_1"],
            all_finite_everywhere=local["checks"]["no_nan_anywhere"]
            and local["checks"]["no_inf_anywhere"],
            zero_outside_footprint=local["checks"]["outside_footprint_zero"],
            no_sentinels=local["checks"]["no_sentinel_values"],
            zero_mass_on_catalogue=local["checks"].get(
                "zero_dots_on_mapped_catalogue", True),
        )
    result = dict(
        file=str(path),
        representation="all-finite zeros-outside" if not allow_outside_nan
        else "sample-faithful NaN-outside",
        gates_format_report_ok=bool(report["ok"]),
        gates_problems=report.get("problems", []),
        validator_receipt=local,
        checks=checks,
    )
    result["pass"] = bool(all(checks.values()) and
                          (report["ok"] or allow_outside_nan))
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tif", type=Path)
    ap.add_argument("--sample", type=Path, default=Path("data/bridge/sample_submission.tif"))
    ap.add_argument("--data-dir", type=Path, default=Path("data/bridge"))
    ap.add_argument("--allow-outside-nan", action="store_true")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    rep = validate_submission(args.tif, sample=args.sample, data_dir=args.data_dir,
                              allow_outside_nan=args.allow_outside_nan)
    def _scrub(o):
        if isinstance(o, float) and o != o:
            return None
        if isinstance(o, dict):
            return {k: _scrub(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_scrub(v) for v in o]
        return o

    rep = _scrub(rep)
    text = json.dumps(rep, indent=2, allow_nan=False)
    print(text)
    if args.json_out:
        args.json_out.write_text(text + "\n")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
