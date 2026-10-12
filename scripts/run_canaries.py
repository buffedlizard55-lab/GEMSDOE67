"""Feature-alone, two-sided AUC leakage screening on unchanged shared folds.
No AUC is a DTI or leaderboard score. No model is trained by this diagnostic.
"""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
import rasterio
from sklearn.metrics import roc_auc_score
from gems57.spatial import folds

def main():
    with rasterio.open(ROOT/'data/sample_submission.tif') as s: fp=np.isfinite(s.read(1))
    with rasterio.open(ROOT/'data/labels.tif') as s: cat=(s.read(1)>0)&fp
    result={'diagnostic':'FEATURE-ALONE AUC; NOT HOLDOUT-DTI or organizer score', 'split':'gems57.spatial.folds label-blind-quadrants-v2','buffer_px':80,'seed':67012,'folds':[],'passed':True}
    rng=np.random.default_rng(67012)
    for fold in folds(cat,fp):
        pos=np.flatnonzero(fold['truth']); neg=np.flatnonzero(fold['region']&~cat)
        neg=rng.choice(neg,min(50000,len(neg)),replace=False)
        idx=np.r_[pos,neg]; y=np.r_[np.ones(len(pos)),np.zeros(len(neg))]
        row={'fold':fold['fold'],'split_receipt':fold['receipt'],'positive_pixels':len(pos),'negative_sample_pixels':len(neg),'features':[]}
        with rasterio.open(ROOT/'data/training_features.tif') as s:
            for b in range(1,s.count+1):
                a=s.read(b).ravel()[idx]; good=np.isfinite(a)&(a>-1e30)&(a<1e30)
                auc=float(roc_auc_score(y[good],a[good])); two=max(auc,1-auc)
                row['features'].append({'band':b,'name':s.descriptions[b-1],'auc':auc,'two_sided_auc':two,'missing_pixels':int((~good).sum()),'leakage_alarm':two>.90})
                result['passed'] &= two<=.90
        result['folds'].append(row)
        (ROOT/'evidence/feature_canaries.partial.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print('Fold',fold['fold'],'max two-sided AUC',max(r['two_sided_auc'] for r in row['features']),flush=True)
    (ROOT/'evidence/feature_canaries.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
if __name__=='__main__':main()
