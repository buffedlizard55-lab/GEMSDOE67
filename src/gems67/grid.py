"""Canonical competition grid, verified from the pinned competition rasters.

Every constant here was read back from the hash-pinned bytes (see data/registry.json):
  training_features.tif  sha256 4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5
  labels.tif             sha256 7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093
  sample_submission.tif  sha256 2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc
"""

from __future__ import annotations

#: (rows, cols)
GRID_SHAPE: tuple[int, int] = (3730, 3292)
#: GDAL-style affine: (x_scale, row_rot, x_origin, col_rot, y_scale, y_origin)
TRANSFORM: tuple[float, ...] = (100.0, 0.0, 243350.0, 0.0, -100.0, 4508550.0)
EPSG: int = 32611
PIXEL_SIZE_M: float = 100.0
TOTAL_CELLS: int = GRID_SHAPE[0] * GRID_SHAPE[1]  # 12 279 160

#: Metric parameters, verbatim from the published problem description (page 967).
ALPHA: float = 0.2
BETA: float = 0.8
KERNEL_RADIUS_PX: float = 3.0  # 300 m at 100 m pixels

#: Sentinel used by the organizer's feature stack (GDAL_NODATA).
FEATURE_NODATA: float = -3.4028234663852886e38

BAND_NAMES: tuple[str, ...] = (
    "mag_anom",
    "rtp",
    "tmi_hg",
    "geod_2ndinv",
    "iso_grav_anom_slope",
    "tc",
    "geod_shearrate",
    "geod_dilaterate",
    "tmi_vg",
    "deq_n100a15",
    "iso_grav_anom_vg",
    "det_elev",
    "iso_grav_anom",
    "tmi",
    "depth_to_base_surf",
    "ieq_n100a15",
    "cond_surf",
    "iso_grav_anom_hg",
    "det_elev_slope",
)
"""Band order read from the ``band_name`` items of the stack's GDAL_METADATA tag (1-based 1..19)."""

BAND_INDEX: dict[str, int] = {name: i for i, name in enumerate(BAND_NAMES)}
