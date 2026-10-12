"""Small CPU research model: joint axial/tip heads and stacked segmentation.
Not the Batra CNN; no leaderboard or geological validity is implied.
"""
import numpy as np
from scipy.special import expit

class JointHeads:
    def __init__(self, channels, seed=67012, auxiliary=True):
        r=np.random.default_rng(seed); hidden=24
        self.params={'w':r.normal(0,.12,(channels,hidden)).astype('f'), 'b':np.zeros(hidden,'f'),
                     'v':r.normal(0,.12,(hidden,4)).astype('f'),'c':np.zeros(4,'f'),
                     's':r.normal(0,.12,(hidden+4,1)).astype('f'),'d':np.zeros(1,'f')}
        self.auxiliary=auxiliary

    def forward(self,x):
        p=self.params; h=np.tanh(x@p['w']+p['b']); z=h@p['v']+p['c']
        a=np.column_stack((expit(z[:,0]), np.tanh(z[:,1:3]), expit(z[:,3])))
        stacked=np.column_stack((h,a)); final=expit((stacked@p['s']+p['d'])[:,0])
        return h,a,stacked,final

    def fit(self,x,seg,axis,axis_mask,heat,steps=300,batch=512,seed=67012):
        if len(x)==0: raise ValueError('empty training set')
        r=np.random.default_rng(seed); m={k:np.zeros_like(v) for k,v in self.params.items()}; vv={k:np.zeros_like(v) for k,v in self.params.items()}
        for t in range(1,steps+1):
            ids=r.integers(0,len(x),batch); xx=x[ids]; y=seg[ids]; ax=axis[ids]; am=axis_mask[ids]; ht=heat[ids]
            h,a,s,out=self.forward(xx); dz=(out-y)[:,None]/batch
            grads={'s':s.T@dz,'d':dz.sum(0)}; ds=dz@self.params['s'].T
            dh=ds[:,:h.shape[1]]; da=ds[:,h.shape[1]:].copy()
            # Auxiliary BCE for first segmentation and endpoint/junction heatmap;
            # local unit-axial target MSE only within 3 px of visible traces.
            az=da*np.column_stack((a[:,0]*(1-a[:,0]),1-a[:,1:3]**2,a[:,3]*(1-a[:,3])))
            if self.auxiliary:
                az[:,0]+=.5*(a[:,0]-y)/batch
                az[:,1:3]+=.5*(a[:,1:3]-ax)*(1-a[:,1:3]**2)*am[:,None]/max(am.sum(),1)
                az[:,3]+=.25*(a[:,3]-ht)/batch
            grads['v']=h.T@az;grads['c']=az.sum(0)
            dh=(dh+az@self.params['v'].T)*(1-h*h)
            grads['w']=xx.T@dh;grads['b']=dh.sum(0)
            for k in self.params:
                g=np.clip(grads[k],-5,5);m[k]=.9*m[k]+.1*g;vv[k]=.999*vv[k]+.001*g*g
                self.params[k]-=.003*(m[k]/(1-.9**t))/(np.sqrt(vv[k]/(1-.999**t))+1e-8)
        return self

    def predict(self,x):
        _,a,_,p=self.forward(x)
        norm=np.linalg.norm(a[:,1:3],axis=1)
        axial=np.divide(a[:,1:3],norm[:,None],out=np.zeros_like(a[:,1:3]),where=norm[:,None]>1e-6)
        return p,axial,a[:,3],norm
