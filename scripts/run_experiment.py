"""One pre-registered CPU ablation experiment, never a release or slot selector."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'vendor'),str(ROOT/'src')]
import numpy as np
import rasterio
from scipy import ndimage as ndi
from gems57.spatial import folds
from gems57.evaluate_holdout import evaluate,pooled_summary
from gems67.geometry import targets,trace_geometry,decode,place_nodes
from gems67.model import JointHeads

def main():
    start=time.monotonic()
    canary=json.loads((ROOT/'evidence/feature_canaries.json').read_text())
    if not canary['passed']:raise RuntimeError('feature leakage alarm: stop')
    with rasterio.open(ROOT/'data/sample_submission.tif') as s:fp=np.isfinite(s.read(1));shape=fp.shape
    with rasterio.open(ROOT/'data/labels.tif') as s:cat=(s.read(1)>0)&fp
    # Transcode the restored cached stack, not a new feature-engineering pipeline.
    cache=ROOT/'data/raw_stack.npy'
    if not cache.exists():
        tmp=cache.with_suffix('.partial.npy')
        with rasterio.open(ROOT/'data/training_features.tif') as s:
            x=np.lib.format.open_memmap(tmp,mode='w+',dtype='float32',shape=(*shape,s.count))
            for i in range(s.count):x[:,:,i]=s.read(i+1)
            x.flush();del x
        tmp.replace(cache)
    x=np.load(cache,mmap_mode='r');channels=x.shape[-1]
    result={'experiment_id':'H67-A-01','experiment_count':1,'model':'CPU shared-trunk stacked heads; raster-proxy geometry, not Batra CNN','seed':67012,'training_steps':300,'folds':[],'production_raster_written':False}
    allterms={'joint':None,'segmentation_control':None};tip_sums={n:[0.,0] for n in allterms}
    _,_,fulltips=trace_geometry(cat) # evaluation-only labels; never passed into model
    tipzone=ndi.distance_transform_edt(~fulltips)<=3 if fulltips.any() else np.zeros(shape,bool)
    for fold in folds(cat,fp):
        if time.monotonic()-start>5400:raise RuntimeError('research budget guard')
        f=fold['fold'];rng=np.random.default_rng(67012+f)
        tr=fold['train'];visible=fold['visible']
        # Fixed balanced sample: this is not calibrated posterior probability.
        positive=np.flatnonzero(tr&visible);negative=np.flatnonzero(tr&~visible)
        pos=rng.choice(positive,min(20000,len(positive)),replace=False)
        neg=rng.choice(negative,min(60000,len(negative)),replace=False)
        ids=np.r_[pos,neg];yx=np.column_stack(np.unravel_index(ids,shape));raw=np.array(x[yx[:,0],yx[:,1]])
        good=np.isfinite(raw)&(abs(raw)<1e30)
        med=np.nanmedian(np.where(good,raw,np.nan),axis=0)
        if not np.isfinite(med).all():raise ValueError('feature absent in training')
        raw=np.where(good,raw,med);scale=np.maximum(np.std(raw,axis=0),1e-5)
        trainx=np.clip((raw-med)/scale,-8,8).astype('f')
        axis,am,heat=targets(visible,yx);seg=visible[yx[:,0],yx[:,1]].astype('f')
        # Evaluation uses a fixed, footprint-derived crop, not withheld geometry.
        ry,rx=np.nonzero(fold['region']);sl=(slice(max(0,ry.min()-4),min(shape[0],ry.max()+5)),slice(max(0,rx.min()-4),min(shape[1],rx.max()+5)))
        crop_shape=fp[sl].shape;pred_idx=np.flatnonzero(fp[sl]);cy,cx=np.unravel_index(pred_idx,crop_shape)
        foldsmall={k:fold[k][sl] for k in ['region','truth','visible']}
        active=fp[sl]&foldsmall['region']&~foldsmall['visible']; row={'fold':f,'split_receipt':fold['receipt'],'train_samples':len(ids),'orientation_supervised_samples':int(am.sum()),'arms':{}}
        for name,aux in [('segmentation_control',False),('joint',True)]:
            model=JointHeads(channels,seed=67012+f,auxiliary=aux).fit(trainx,seg,axis,am,heat,seed=67012+f)
            p=np.zeros(crop_shape,'f');a=np.zeros((*crop_shape,2),'f');ht=np.zeros(crop_shape,'f')
            for lo in range(0,len(cy),32768):
                yy,xx=cy[lo:lo+32768],cx[lo:lo+32768];v=np.array(x[yy+sl[0].start,xx+sl[1].start]);good=np.isfinite(v)&(abs(v)<1e30)
                v=np.clip((np.where(good,v,med)-med)/scale,-8,8).astype('f')
                pp,aa,hh,nn=model.predict(v);p[yy,xx]=pp;a[yy,xx]=aa;ht[yy,xx]=hh
            # Holdout diagnostics only; no production surface, download or promotion.
            dots=decode(p,a,ht,active) if aux else place_nodes(p,active&(p>=.5))
            score,terms=evaluate(dots,foldsmall,fp[sl],origin=(sl[0].start,sl[1].start),global_shape=shape)
            allterms[name]=terms if allterms[name] is None else allterms[name]+terms
            tiptruth=foldsmall['truth']&tipzone[sl]&active
            if dots.any():credit=np.maximum(1-ndi.distance_transform_edt(dots==0)/3,0)
            else:credit=np.zeros(crop_shape)
            tip_sums[name][0]+=float(credit[tiptruth].sum());tip_sums[name][1]+=int(tiptruth.sum())
            row['arms'][name]={'emitted_pixels':int(dots.sum()),'tip_kernel_credit_sum':float(credit[tiptruth].sum()),'tip_positive_pixels':int(tiptruth.sum())}
            print('Fold',f,name,'dots',int(dots.sum()),flush=True)
        result['folds'].append(row)
    summary=pooled_summary(allterms,candidate='joint',draws=1000,seed=67012)
    result['holdout']=summary
    result['tip_recovery']={n:{'kernel_recall':v[0]/v[1] if v[1] else None,'withheld_tip_adjacent_pixels':v[1],'evidence_class':'HOLDOUT-DIAGNOSTIC, not DTI'} for n,v in tip_sums.items()}
    result['positive_paired_dti_ci']=summary['paired_differences']['segmentation_control']['ci95'][0]>0
    result['tip_improved']=tip_sums['joint'][1]>0 and tip_sums['joint'][0]>tip_sums['segmentation_control'][0]
    result['seconds']=time.monotonic()-start
    result['verdict']='negative'
    result['limitations']=['No established current holdout-best baseline available in starting repository.','Raster skeleton endpoint/junction supervision is a proxy, not original polylines.','No production candidate: global registry checks and TIFF validator not run.','CPU pixelwise input model is not a spatial stacked CNN.','Fixed class-balanced thresholds are not calibrated probabilities.']
    (ROOT/'evidence/experiment.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Finished; research evidence saved; no submission raster exported',flush=True)
if __name__=='__main__':main()
