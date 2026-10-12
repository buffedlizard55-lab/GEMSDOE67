import hashlib,json
from pathlib import Path
import numpy as np
import pytest
from gems67.geometry import targets,decode,place_nodes
from gems67.model import JointHeads
from gems67.release import release_decision
from gems57 import metric
from gems57.evaluate_holdout import evaluate,pooled_summary
from gems57.spatial import folds

def test_template_is_unmodified():
    root=Path(__file__).resolve().parents[1]
    for f in json.loads((root/'evidence/template_pin.json').read_text())['files']:
        assert hashlib.sha256((root/f['path']).read_bytes()).hexdigest()==f['sha256']

def test_axial_horizontal_and_supervision_radius():
    v=np.zeros((31,31),bool);v[15,5:26]=True
    axis,mask,heat=targets(v,np.array([[15,15],[18,15],[19,15],[15,5]]))
    np.testing.assert_allclose(axis[:,0],1,atol=1e-6)
    np.testing.assert_allclose(axis[:,1],0,atol=1e-6)
    assert mask.tolist()==[True,True,False,True]
    assert heat[-1]==pytest.approx(1)

def test_axial_vertical():
    v=np.zeros((31,31),bool);v[5:26,15]=True
    a,m,_=targets(v,np.array([[15,15]]))
    assert m[0];np.testing.assert_allclose(a,[[-1,0]],atol=1e-6)

def test_empty_visible_has_no_invented_labels():
    a,m,h=targets(np.zeros((20,20),bool),np.array([[0,0],[5,5]]))
    assert not m.any() and not a.any() and not h.any()

def test_decode_stops_at_unsupported_gap():
    p=np.zeros((21,31));p[10,2:12]=.9;p[10,15:27]=.4
    a=np.zeros((*p.shape,2));a[...,0]=1
    d=decode(p,a,np.zeros(p.shape),np.ones(p.shape,bool))
    assert d[:,:12].sum()>0 and d[:,15:].sum()==0
    coords=np.argwhere(d)
    for i in range(len(coords)):
        for j in range(i):assert np.linalg.norm(coords[i]-coords[j])>=5

def test_normal_nms_and_no_wrapped_growth():
    p=np.zeros((20,20));p[9,1:19]=.4;p[10,1:19]=.9;p[11,1:19]=.4
    a=np.zeros((*p.shape,2));a[...,0]=1
    d=decode(p,a,np.zeros_like(p),np.ones_like(p,bool))
    assert d.sum()>0;assert (np.argwhere(d)[:,0]==10).all()

def test_visible_mask_exact():
    p=np.ones((20,20));support=np.ones_like(p,bool);support[10,10]=False
    d=place_nodes(p,support);assert d[10,10]==0

@pytest.mark.parametrize('bad',[np.nan,np.inf,-1,2])
def test_bad_probabilities_rejected(bad):
    p=np.zeros((10,10));p[5,5]=bad
    with pytest.raises(ValueError):decode(p,np.ones((10,10,2)),np.zeros((10,10)),np.ones((10,10),bool))

def test_neural_heads_finite_and_training_changes_weights():
    rng=np.random.default_rng(4);x=rng.normal(size=(100,3)).astype('f');y=(x[:,0]>0).astype('f')
    net=JointHeads(3);before=net.params['w'].copy()
    net.fit(x,y,np.tile([1,0],(100,1)),np.ones(100,bool),y,steps=20)
    assert not np.array_equal(before,net.params['w'])
    p,a,h,n=net.predict(x);assert np.isfinite(a).all();assert ((p>=0)&(p<=1)).all();assert ((h>=0)&(h<=1)).all()

def test_shared_metric_matches_bruteforce():
    rng=np.random.default_rng(9)
    for _ in range(5):
        p=rng.uniform(size=(8,9));p[p<.8]=0;g=rng.uniform(size=p.shape)>.8
        fast=metric.dti_exact(p,g);slow=metric.dti_bruteforce(p,g)
        for k in ['tp','fp','fn','dti']:assert fast[k]==pytest.approx(slow[k])

def test_pooled_not_average_and_visible_masking():
    v=np.ones((12,12),bool);g=np.zeros_like(v);g[2,2]=g[9,9]=True;k=np.zeros_like(v);k[3,3]=True
    p=g.astype(float);p[3,3]=1
    score,t=evaluate(p,dict(region=v,truth=g,visible=k),v,block_side=6)
    assert score['fp']==0 and score['n_truth']==2
    s=pooled_summary({'joint':t,'control':t},draws=20,candidate='joint')
    assert s['paired_differences']['control']['ci95']==[0,0]
    assert s['scores']['joint']['withheld_positive_pixels']==2

def test_buffered_folds_whole_components():
    cat=np.zeros((100,100),bool);cat[20,10:80]=True;cat[80,10:80]=True
    fp=np.ones_like(cat)
    for fold in folds(cat,fp,buffer_px=5):
        assert not (fold['train']&fold['held_all']).any()
        assert not (fold['visible']&fold['held_all']).any()
        assert not (fold['train']&fold['region']).any()
        assert fold['receipt']['shared_train_truth_components']==0

def test_unknown_gates_never_promote():
    assert not release_decision({})['download_enabled']
    assert release_decision({'paired_dti_ci95':[float('nan'),1]})['verdict']=='negative'

def test_uniqueness_surface_and_dots_separated():
    from gems67.uniqueness import compare
    p=np.zeros((20,20));p[2,2]=1;q=np.zeros_like(p);q[2,4]=1;fp=np.ones_like(p,bool)
    assert compare(p,q,fp,stage='surface')['candidate_dot_fraction_within_3px'] is None
    assert compare(p,q,fp,stage='dots')['duplicate']
    assert compare(p,p,fp,stage='surface')['duplicate']

def test_constant_surface_is_not_a_uniqueness_pass():
    from gems67.uniqueness import compare
    p=np.zeros((10,10));q=np.ones_like(p)
    assert not compare(p,q,np.ones_like(p,bool),stage='surface')['determinate']

def test_invalid_registry_pixels_fail_closed():
    from gems67.uniqueness import compare
    p=np.zeros((10,10));q=p.copy();q[1,1]=np.nan
    with pytest.raises(ValueError):compare(p,q,np.ones_like(p,bool),stage='surface')

@pytest.mark.parametrize('value',[np.nan,np.inf,-9999.,1.01])
def test_on_disk_validator_rejects_bad_values(tmp_path,value):
    import rasterio
    from rasterio.transform import from_origin
    from gems57.gates import format_report
    ref=tmp_path/'sample.tif';bad=tmp_path/'bad.tif'
    profile=dict(driver='GTiff',height=12,width=12,count=1,dtype='float32',crs='EPSG:32611',transform=from_origin(243350,4508550,100,100))
    a=np.zeros((12,12),'f')
    with rasterio.open(ref,'w',**profile) as s:s.write(a,1)
    a[5,5]=value
    with rasterio.open(bad,'w',**profile) as s:s.write(a,1)
    assert not format_report(bad,ref,footprint=np.ones(a.shape,bool))['ok']

def test_on_disk_validator_accepts_fixture_and_rejects_transform(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    from gems57.gates import format_report
    ref=tmp_path/'sample.tif';candidate=tmp_path/'candidate.tif'
    profile=dict(driver='GTiff',height=12,width=12,count=1,dtype='float32',crs='EPSG:32611',transform=from_origin(243350,4508550,100,100))
    a=np.zeros((12,12),'f');a[5,5]=1
    for path in (ref,candidate):
        with rasterio.open(path,'w',**profile) as s:s.write(a,1)
    assert format_report(candidate,ref,footprint=np.ones(a.shape,bool))['ok']
    profile['transform']=from_origin(243450,4508550,100,100)
    with rasterio.open(candidate,'w',**profile) as s:s.write(a,1)
    assert not format_report(candidate,ref,footprint=np.ones(a.shape,bool))['ok']

def test_writer_never_repairs_invalid_array(tmp_path):
    from gems57.submission_writer import write_submission
    p=np.zeros((12,12),'f');p[5,5]=2
    with pytest.raises(ValueError,match='normalized'):
        write_submission(tmp_path/'candidate.tif',p,tmp_path/'absent.tif',np.ones(p.shape,bool),name='test',note='unit test, not a submission')
    assert not list(tmp_path.glob('*.tif'))
