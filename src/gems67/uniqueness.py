"""Exact, scoped registry comparison; a partial inventory never clears release."""
import numpy as np
from scipy.stats import spearmanr
from scipy.ndimage import distance_transform_edt

def compare(candidate,prior,footprint,*,stage):
    if stage not in ('surface','dots'):raise ValueError('stage must be surface or dots')
    a=np.asarray(candidate);b=np.asarray(prior);fp=np.asarray(footprint,bool)
    if a.shape!=b.shape or a.shape!=fp.shape or a.ndim!=2 or not fp.any():raise ValueError('grid/footprint mismatch')
    if not np.isfinite(a[fp]).all() or not np.isfinite(b[fp]).all():raise ValueError('missing in-footprint values')
    av,bv=a[fp],b[fp]
    agreement=float(np.mean(av==bv));same=bool(np.array_equal(av,bv))
    rho=float(spearmanr(av,bv).statistic) if np.ptp(av)>0 and np.ptp(bv)>0 else None
    overlap=None
    if stage=='dots':
        ad=(a>0)&fp;bd=(b>0)&fp
        if ad.any():overlap=float(np.mean(distance_transform_edt(~bd)[ad]<=3)) if bd.any() else 0.
    duplicate=same or (rho is not None and abs(rho)>.90) or (overlap is not None and overlap>.70)
    return {'stage':stage,'spearman':rho,'pixel_agreement':agreement,'identical_pixels':same,'candidate_dot_fraction_within_3px':overlap,'duplicate':duplicate,'determinate':rho is not None and (stage=='surface' or overlap is not None)}
