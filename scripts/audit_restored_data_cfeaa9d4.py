#!/usr/bin/env python3
# Preserved verbatim from PR #1 (lane cfeaa9d4); it was `scripts/prepare_data.py`. Renamed on merge because
# the OVTR lane ships a different prepare_data.py. It audits data/*.tif and writes evidence/data_audit.json.
"""Audit restored files without treating sample values as predictive features."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
import rasterio
from gems57.grid import _check

def main():
    reports={}
    for name in ('sample_submission.tif','labels.tif','training_features.tif'):
        with rasterio.open(ROOT/'data'/name) as s:
            _check(s,name)
            reports[name]={'shape':list(s.shape),'crs':str(s.crs),'transform':list(s.transform)[:6],'bands':s.count,'dtypes':list(s.dtypes)}
            if name=='training_features.tif':
                if s.count!=19:raise ValueError('expected 19 cached bands')
                reports[name]['band_descriptions']=list(s.descriptions)
            else:
                a=s.read(1)
                if name=='sample_submission.tif':fp=np.isfinite(a)
                else:cat=(a>0)&fp
    reports['footprint_pixels']=int(fp.sum());reports['catalogue_pixels']=int(cat.sum())
    reports['provenance']='Owner-mirrored bytes; official authenticity not independently established'
    (ROOT/'evidence/data_audit.json').write_text(json.dumps(reports,indent=2,allow_nan=False)+'\n')
if __name__=='__main__':main()
