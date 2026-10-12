"""Label-free structural fields: band descriptors, axial frames, evidence.

Conventions (single definition, used by every other module)
-----------------------------------------------------------
Arrays are ``(row, col) = (y, x)``.  A local lineament has a unit tangent
``u = (u_y, u_x)``.  Because a fault trace is *undirected*, orientation is carried
in the axial (double-angle) frame

    cos2t = u_x**2 - u_y**2 ,      sin2t = 2 * u_x * u_y ,

which is invariant under ``u -> -u``.  For an image whose structure tensor is
``J = [[<g_y g_y>, <g_y g_x>], [<g_y g_x>, <g_x g_x>]]`` the line tangent is
perpendicular to the dominant gradient, so

    cos2t = (J_yy - J_xx) / D ,    sin2t = -2 J_yx / D ,
    D     = sqrt((J_yy - J_xx)**2 + 4 J_yx**2) ,

and the coherence ``c = D / (J_yy + J_xx)`` in [0, 1].  ``tests/test_fields.py``
pins this against synthetic lines whose tangent is known.

Memory design
-------------
A 14-band x 2-scale stack of full-grid float32 channels would be 5.5 GB, which the
2-3 GB sandbox cannot hold.  So the per-feature channels are written to disk as
float16 and read back memory-mapped, one feature at a time.  Nothing in the
pipeline ever holds more than a handful of full-grid arrays:

* :func:`build_evidence` streams band-by-band and writes three float16 channels
  per (band, scale): ``wcos2``, ``wsin2``, ``wenergy``.
* :meth:`EvidenceStack.aggregate` sums them into the resident evidence field and
  aggregate frame.
* :mod:`gems67.heads` accumulates the ridge normal equations feature-by-feature,
  so a head fit is one streaming pass and never materialises the design matrix.

No function here reads the fault catalogue.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage as ndi

BAND_DESCRIPTIONS: dict[int, str] = {
    1: "Magnetic anomaly - deviation from expected Earth's magnetic field",
    2: "Reduced to pole magnetic data - magnetic anomaly corrected for latitude effects",
    3: "Total magnetic intensity horizontal gradient - rate of change in horizontal direction",
    4: "Geodetic second invariant - measure of strain rate tensor magnitude",
    5: "Isostatic gravity anomaly slope - gradient of gravity after isostatic correction",
    6: "Tilt angle or total curvature - magnetic field derivative for edge detection",
    7: "Geodetic shear rate - rate of angular deformation from GPS/InSAR",
    8: "Geodetic dilatation rate - rate of volumetric strain (expansion/contraction)",
    9: "Total magnetic intensity vertical gradient - rate of change in vertical direction",
    10: "Distance to earthquake (n=100km radius, a=15 deg azimuth parameters)",
    11: "Isostatic gravity anomaly vertical gradient - vertical rate of change",
    12: "Detrended elevation - topography with regional trends removed",
    13: "Isostatic gravity anomaly - gravity after compensating for topographic mass",
    14: "Total magnetic intensity - total strength of magnetic field",
    15: "Depth to basement surface - thickness of sedimentary cover",
    16: "Earthquake intensity or density (n=100km radius, a=15 deg parameters)",
    17: "Conductivity surface - electrical conductivity of subsurface",
    18: "Isostatic gravity anomaly horizontal gradient - horizontal rate of change",
    19: "Detrended elevation slope - gradient of elevation after detrending",
}

# The bands this lane uses for boundary/orientation evidence.  Chosen by physical
# role, not by a fit: the magnetic, gravity, topographic and subsurface edge
# carriers (3, 5, 11, 18 are already first derivatives; 6 is a tilt/curvature
# product; 7 and 8 are the geodetic strain rates).
LANE_BANDS: tuple[int, ...] = (2, 3, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 17, 18, 19)

FEATURE_NODATA = -3.4028234663852886e38


def read_band(path: str | Path, index: int) -> tuple[np.ndarray, np.ndarray]:
    """Read one band as float32 with the official nodata sentinel as NaN.

    The sentinel test is ``< -1e38``, exactly as in the organiser's reference
    notebook (``X_orig[X_orig < -1e38] = np.nan``).
    """
    with rasterio.open(path) as src:
        if not 1 <= index <= src.count:
            raise ValueError(f"band {index} out of range 1..{src.count}")
        a = src.read(index).astype(np.float32, copy=True)
    valid = np.isfinite(a) & (a > -1e38)
    a[~valid] = np.nan
    return a, valid


def masked_smooth(a: np.ndarray, valid: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian smoothing of a masked field (nodata does not smear into data)."""
    v = valid.astype(np.float32)
    num = ndi.gaussian_filter(np.where(valid, np.nan_to_num(a, nan=0.0), 0.0), sigma,
                              mode="constant", truncate=3.0)
    den = ndi.gaussian_filter(v, sigma, mode="constant", truncate=3.0)
    return np.divide(num, den, out=np.zeros_like(num), where=den > 1e-6).astype(np.float32)


def axial_frame(jyy: np.ndarray, jxx: np.ndarray, jyx: np.ndarray):
    """Axial line tangent frame from a structure tensor (see module docstring)."""
    diff = jyy.astype(np.float64) - jxx.astype(np.float64)
    d = np.sqrt(diff * diff + 4.0 * jyx.astype(np.float64) ** 2)
    tr = jyy.astype(np.float64) + jxx.astype(np.float64)
    coh = np.divide(d, tr, out=np.zeros_like(d), where=tr > 1e-30)
    cos2 = np.divide(diff, d, out=np.zeros_like(d), where=d > 1e-30)
    sin2 = np.divide(-2.0 * jyx.astype(np.float64), d, out=np.zeros_like(d), where=d > 1e-30)
    return cos2.astype(np.float32), sin2.astype(np.float32), coh.astype(np.float32)


def tensor_at_scale(a: np.ndarray, valid: np.ndarray, sigma: float):
    """Structure tensor of one band at one scale: ``(jyy, jxx, jyx, energy)``."""
    s = masked_smooth(a, valid, sigma)
    gy, gx = np.gradient(s)
    w = sigma * 2.0
    jyy = ndi.gaussian_filter((gy * gy).astype(np.float32), w, mode="nearest", truncate=3.0)
    jxx = ndi.gaussian_filter((gx * gx).astype(np.float32), w, mode="nearest", truncate=3.0)
    jyx = ndi.gaussian_filter((gy * gx).astype(np.float32), w, mode="nearest", truncate=3.0)
    return jyy, jxx, jyx, np.sqrt(np.maximum(jyy + jxx, 0.0))


def robust_unit(x: np.ndarray, mask: np.ndarray, hi_pct: float = 99.0) -> np.ndarray:
    """Scale a non-negative field to [0, 1] by its high percentile over ``mask``."""
    vals = x[mask & np.isfinite(x)]
    if vals.size == 0:
        return np.zeros_like(x, dtype=np.float32)
    ref = float(np.percentile(vals, hi_pct))
    if ref <= 0:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip(x / ref, 0.0, 1.0).astype(np.float32)


class EvidenceStack:
    """Disk-backed stack of per-(band, scale) axial descriptor channels.

    Channels per feature ``k``, all float16 on disk and float32 on read:

    * ``wcos2[k]``   ``c * cos2t``  (confidence-weighted axial cosine)
    * ``wsin2[k]``   ``c * sin2t``
    * ``wenergy[k]`` ``c * e``      (contribution to the aggregate evidence)
    """

    def __init__(self, root: str | Path, band_ids, scales, shape):
        self.root = Path(root)
        self.band_ids = tuple(int(b) for b in band_ids)
        self.scales = tuple(float(s) for s in scales)
        self.shape = tuple(int(v) for v in shape)
        if len(self.band_ids) * len(self.scales) == 0:
            raise ValueError("empty feature stack")
        self._n_feat = len(self.band_ids) * len(self.scales)

    def __len__(self) -> int:
        return self._n_feat

    def label(self, k: int) -> str:
        return f"band{self.band_ids[k // len(self.scales)]}_s{self.scales[k % len(self.scales)]}"

    def _channel(self, k: int, kind: str) -> np.ndarray:
        p = self.root / f"{k:03d}_{kind}.npy"
        a = np.load(p, mmap_mode="r")
        if tuple(a.shape) != self.shape:
            raise ValueError(f"cached channel {p} has shape {a.shape}, expected {self.shape}")
        return np.asarray(a, dtype=np.float32)

    def channels(self, k: int) -> tuple[np.ndarray, np.ndarray]:
        """``(wcos2, wsin2)`` for feature ``k`` as float32 arrays."""
        return self._channel(k, "wcos2"), self._channel(k, "wsin2")

    def evidence_contribution(self, k: int) -> np.ndarray:
        """``wenergy`` for feature ``k`` as a float32 array."""
        return self._channel(k, "wenergy")

    def save_manifest(self, path: str | Path) -> Path:
        p = Path(path)
        p.write_text(json.dumps(dict(band_ids=list(self.band_ids), scales=list(self.scales),
                                     shape=list(self.shape), n_features=self._n_feat,
                                     root=str(self.root)), indent=1) + "\n")
        return p

    @classmethod
    def load(cls, manifest: str | Path) -> "EvidenceStack":
        d = json.loads(Path(manifest).read_text())
        root = d.get("root") or str(Path(manifest).parent)
        return cls(root, d["band_ids"], d["scales"], d["shape"])

    def aggregate(self, guard: np.ndarray, channel_weights: np.ndarray | None = None):
        """Sum the channels into ``(evidence, cos2, sin2, resultant)``.

        ``channel_weights`` are the axial head's learned per-feature weights; with
        ``None`` every feature carries its own confidence.
        """
        g = np.asarray(guard, bool)
        if channel_weights is None:
            wch = np.ones(len(self), np.float64)
        else:
            wch = np.asarray(channel_weights, np.float64).reshape(-1)
            if wch.size != len(self):
                raise ValueError("channel_weights must have one entry per feature")
        evidence = np.zeros(self.shape, np.float32)
        sc = np.zeros(self.shape, np.float32)
        ss = np.zeros(self.shape, np.float32)
        tot = np.zeros(self.shape, np.float32)
        for k in range(len(self)):
            evidence += (wch[k] * self.evidence_contribution(k)).astype(np.float32)
            c2, s2 = self.channels(k)
            sc += (wch[k] * c2).astype(np.float32)
            ss += (wch[k] * s2).astype(np.float32)
            tot += np.abs(c2) + np.abs(s2)
        result = np.hypot(sc, ss)
        cos2 = np.zeros(self.shape, np.float32)
        sin2 = np.zeros(self.shape, np.float32)
        nz = result > 1e-12
        cos2[nz] = (sc[nz] / result[nz]).astype(np.float32)
        sin2[nz] = (ss[nz] / result[nz]).astype(np.float32)
        half = 0.5 * (np.abs(sc) + np.abs(ss) + 1e-12)
        resultant = np.divide(result, 2.0 * half, out=np.zeros_like(result),
                              where=half > 1e-12).astype(np.float32)
        evidence[~g] = 0.0
        cos2[~g] = 0.0
        sin2[~g] = 0.0
        resultant[~g] = 0.0
        return evidence, cos2, sin2, resultant


def build_evidence(features_path: str | Path, out_dir: str | Path,
                   band_ids: tuple[int, ...] = LANE_BANDS,
                   scales: tuple[float, ...] = (1.5, 3.0),
                   center_valid: np.ndarray | None = None, progress=None) -> EvidenceStack:
    """Compute and cache the per-(band, scale) descriptor channels (float16).

    ``center_valid`` is a label-free spatial guard (an erosion of the footprint)
    restricting where a descriptor is trusted.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    shape = None
    k = 0
    for band in band_ids:
        a, valid = read_band(features_path, band)
        if shape is None:
            shape = a.shape
        guard = valid if center_valid is None else (np.asarray(center_valid, bool) & valid)
        for sigma in scales:
            jyy, jxx, jyx, en = tensor_at_scale(a, valid, sigma)
            c2, s2, coh = axial_frame(jyy, jxx, jyx)
            unit = robust_unit(en, guard)
            w = coh * unit
            np.save(out / f"{k:03d}_wcos2.npy", (w * c2).astype(np.float16))
            np.save(out / f"{k:03d}_wsin2.npy", (w * s2).astype(np.float16))
            np.save(out / f"{k:03d}_wenergy.npy", (w * en / max(float(np.max(en[guard])), 1e-30)
                                                  ).astype(np.float16))
            if progress:
                progress(f"band {band} sigma {sigma}: median coherence "
                         f"{float(np.median(coh[guard])):.3f}")
            del jyy, jxx, jyx, en, c2, s2, coh, unit, w
            k += 1
        del a, valid, guard
    stack = EvidenceStack(out, band_ids, scales, shape)
    stack.save_manifest(out / "manifest.json")
    return stack


def tangent_field(cos2: np.ndarray, sin2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unit tangent ``(t_y, t_x)`` of the axial frame."""
    theta = 0.5 * np.arctan2(sin2.astype(np.float32), cos2.astype(np.float32))
    return np.sin(theta).astype(np.float32), np.cos(theta).astype(np.float32)


def normal_field(cos2: np.ndarray, sin2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unit normal ``(n_y, n_x)`` of the axial frame (perpendicular to the tangent)."""
    ty, tx = tangent_field(cos2, sin2)
    return -tx, ty
