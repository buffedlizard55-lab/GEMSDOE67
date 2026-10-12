"""Raster-proxy training targets and orientation-aware decoding.
Angles measured from increasing column toward increasing row (image coordinates).
"""
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

def trace_geometry(visible):
    sk=skeletonize(np.asarray(visible,bool)); coords=np.argwhere(sk)
    neighbours=ndi.convolve(sk.astype('i2'),np.ones((3,3),'i2'),mode='constant')-sk
    special=sk&((neighbours==1)|(neighbours>=3))
    tips=sk&(neighbours==1)
    return coords,special,tips

def targets(visible, sample_yx, sigma=1.5):
    if not 1<=sigma<=2: raise ValueError('sigma must be in [1,2]')
    coords,special,tips=trace_geometry(visible)
    n=len(sample_yx); axis=np.zeros((n,2),'f'); mask=np.zeros(n,bool)
    if len(coords)>=3:
        tree=cKDTree(coords);dist,nearest=tree.query(sample_yx,k=1)
        _,inds=tree.query(coords[nearest],k=min(7,len(coords)))
        pts=coords[inds].astype(float);pts-=pts.mean(axis=1,keepdims=True)
        cov=np.einsum('nki,nkj->nij',pts,pts)
        vals,vecs=np.linalg.eigh(cov);v=vecs[:,:,-1] # row,col tangent
        axis[:,0]=v[:,1]**2-v[:,0]**2;axis[:,1]=2*v[:,0]*v[:,1]
        # Reject ambiguous local geometry rather than invent a strike at junctions.
        mask=(dist<=3)&(vals[:,1]>2*vals[:,0])&(vals[:,1]>0)
    events=np.argwhere(special)
    heat=np.zeros(n,'f')
    if len(events):
        d,_=cKDTree(events).query(sample_yx)
        heat=np.exp(-.5*(d/sigma)**2).astype('f')
    return axis,mask,heat

def decode(prob,axial,heat,valid,low=.30,high=.50,spacing=5):
    p=np.asarray(prob,float);a=np.asarray(axial,float);ht=np.asarray(heat,float);valid=np.asarray(valid,bool)
    if p.ndim!=2 or a.shape!=p.shape+(2,) or ht.shape!=p.shape or valid.shape!=p.shape:raise ValueError('shape mismatch')
    if not (0<low<high<=1) or spacing not in (4,5):raise ValueError('invalid thresholds/spacing')
    if not np.isfinite(p).all() or not np.isfinite(a).all() or not np.isfinite(ht).all() or (p<0).any() or (p>1).any() or (ht<0).any() or (ht>1).any():raise ValueError('nonfinite or out-of-range inputs')
    theta=.5*np.arctan2(a[...,1],a[...,0]);dy=np.sin(theta);dx=np.cos(theta)
    yy,xx=np.indices(p.shape,dtype=float)
    # Sample the normal, not the tangent. Zero padding never wraps edges.
    plus=ndi.map_coordinates(p,[yy+dx,xx-dy],order=1,mode='constant',cval=0)
    minus=ndi.map_coordinates(p,[yy-dx,xx+dy],order=1,mode='constant',cval=0)
    norm=np.linalg.norm(a,axis=-1)
    ridge=valid&(p>=low)&(p>=plus)&(p>=minus)&(norm>.5)
    seeds=ridge&(p>=high)
    # Only grow to neighbours aligned with BOTH local axial tangents.
    seen=seeds.copy(); queue=list(map(tuple,np.argwhere(seeds)));h,w=p.shape
    for y,x in queue:
        for j,i in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            ny,nx=y+j,x+i
            if not(0<=ny<h and 0<=nx<w) or seen[ny,nx] or not ridge[ny,nx]:continue
            length=np.hypot(j,i)
            u=abs((j*dy[y,x]+i*dx[y,x])/length);v=abs((j*dy[ny,nx]+i*dx[ny,nx])/length)
            # Strong junction heat permits a turn, never unsupported continuation.
            threshold=.35 if max(ht[y,x],ht[ny,nx])>=.5 else .70
            if min(u,v)>=threshold: seen[ny,nx]=True;queue.append((ny,nx))
    return place_nodes(p,seen,spacing)

def place_nodes(prob,support,spacing=5):
    if spacing not in (4,5):raise ValueError('spacing must be 4 or 5')
    coords=np.argwhere(support);out=np.zeros(prob.shape,'f');blocked=np.zeros(prob.shape,bool)
    if not len(coords):return out
    order=np.argsort(-prob[tuple(coords.T)],kind='stable');h,w=out.shape
    gy,gx=np.mgrid[-spacing:spacing+1,-spacing:spacing+1];disk=(gy*gy+gx*gx)<spacing**2
    for y,x in coords[order]:
        if blocked[y,x]:continue
        out[y,x]=1
        y0,y1=max(0,y-spacing),min(h,y+spacing+1);x0,x1=max(0,x-spacing),min(w,x+spacing+1)
        blocked[y0:y1,x0:x1]|=disk[y0-y+spacing:y1-y+spacing,x0-x+spacing:x1-x+spacing]
    return out
