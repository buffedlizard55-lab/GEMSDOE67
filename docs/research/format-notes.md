# Submission format: what the portal actually checks, and both ways it says no

## The rule, verbatim

From the problem description, "Submission format"
(<https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/>):

* same projected CRS as the training data — **EPSG:32611** (UTM 11N);
* same resolution — **100 m**;
* same bounds, and "data outside the bounds is **null or nan**";
* "a single layer with datatype of **32-bit float** (`float32`) with values **between 0 and 1**";
* the organizers' `sample_submission.tif` is offered as the template.

On the submission page itself: "You can submit a single-band GeoTIFF (.tif) file, or a .zip file
containing a single GeoTIFF, with your predictions. It must match the submission format's CRS,
shape, and geotransform."

## The error `"Predicted values must be in range [0, 1]"` — two mechanisms

Both were measured in this family of repositories; the first is reproduced here from the pinned
bytes with `tifffile`:

1. **A float32 sentinel.** `training_features.tif` carries
   `GDAL_NODATA = -3.4028234663852886e+38`. **[MEASURED, this checkout]** 3 061 cells of band 1
   inside the footprint carry that sentinel, and 3 073 distinct footprint cells carry it in at
   least one band. A writer that copies such values — or re-uses them as its own nodata tag —
   hands the validator a number far outside `[0, 1]`.
2. **A NaN nodata tag.** `sample_submission.tif` (the organizers' own template) carries
   `GDAL_NODATA = nan` and 7 111 787 NaN cells outside the footprint. This is legal today, and
   it is the format the shipped primary copies — but a validator that ignores the nodata tag
   and takes `min()`/`max()` over all cells sees `nan`, and a strict reading can reject it.

Because the two are different failures with the same message, this repository ships **both
twins** for every artifact:

| file | outside the footprint | nodata tag | when to prefer it |
| --- | --- | --- | --- |
| `…-nan.tif` | NaN | `nan` (identical to `sample_submission.tif`) | default; matches the template byte-for-byte in structure |
| `…-zero.tif` | 0.0 (all-finite) | none | if a validator ever rejects NaN |

Values inside the footprint are `0.0` or `1.0` in both, so both are inside `[0, 1]` everywhere
the competitor controls the value, and the two files are identical inside the footprint.

## Independent verification performed here

`validate_submission()` re-opens the written file from disk and reports shape, dtype,
`ModelPixelScaleTag`, `ModelTiepointTag`, GeoKeys, compression, cell counts, min/max, the
number of cells outside `[0, 1]`, and — when GDAL is available — the CRS and affine transform
as read by **GDAL**, not by the writer. Two independent readers (`tifffile 2026.3.3` and
`rasterio 1.4.4` / GDAL 3.10.3) are used so the georeferencing check is not self-referential.
The receipts are published next to each download (`checks-<name>.json`).
