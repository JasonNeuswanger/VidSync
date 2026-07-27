import math, pickle, collections, xml.etree.ElementTree as ET
from homog import dlt, apply, XML
from refine import inv3, cpa
BACK=0.439000010490417
TRUE={'4squares':50.8,'12squares':152.4,'30squares':381.0,'48squares':596.9}
d=pickle.load(open('H.pkl','rb')); clips=d['clips']

def similarity_to_nominal(est, nom):
    """Best translation+rotation+uniform scale taking est onto nom. Fixes the gauge: the grid's
       overall size and orientation are measured quantities, only local placement is uncertain."""
    n=len(est)
    ex=sum(p[0] for p in est)/n; ey=sum(p[1] for p in est)/n
    nx=sum(p[0] for p in nom)/n; ny=sum(p[1] for p in nom)/n
    Sxx=sum((e[0]-ex)*(o[0]-nx)+(e[1]-ey)*(o[1]-ny) for e,o in zip(est,nom))
    Sxy=sum((e[0]-ex)*(o[1]-ny)-(e[1]-ey)*(o[0]-nx) for e,o in zip(est,nom))
    den=sum((e[0]-ex)**2+(e[1]-ey)**2 for e in est)
    a=Sxx/den; b=Sxy/den
    return [(nx+a*(e[0]-ex)-b*(e[1]-ey), ny+b*(e[0]-ex)+a*(e[1]-ey)) for e in est]

def solve_frame(key, rounds=8):
    """Iteratively estimate the true node positions from cross-camera agreement, refitting each
       camera's homography each round. Nothing here assumes a pinhole camera: the cameras are
       coupled only through agreeing on where a physical node is."""
    nodes=sorted({(p[2],p[3]) for nm in clips for p in clips[nm][key]})
    cur={k:k for k in nodes}
    H={nm: dlt(clips[nm][key]) for nm in clips}
    for _ in range(rounds):
        acc=collections.defaultdict(list)
        for nm in clips:
            for su,sv,wx,wy in clips[nm][key]:
                acc[(wx,wy)].append(apply(H[nm],su,sv))
        est=[]
        for k in nodes:
            v=acc[k]; est.append((sum(p[0] for p in v)/len(v), sum(p[1] for p in v)/len(v)))
        est=similarity_to_nominal(est, nodes)
        cur=dict(zip(nodes,est))
        for nm in clips:
            H[nm]=dlt([(su,sv)+cur[(wx,wy)] for su,sv,wx,wy in clips[nm][key]])
    return H, cur

Hf_new={}; Hb_new={}
for key,store in (('front',Hf_new),('back',Hb_new)):
    H,cur=solve_frame(key)
    for nm in clips: store[nm]=H[nm]
    sh=[math.hypot(cur[k][0]-k[0], cur[k][1]-k[1])*1000 for k in cur]
    sh.sort()
    print(f"{key:5}: node corrections (mm) median {sh[len(sh)//2]:.2f}  max {sh[-1]:.2f}")
    for nm in clips:
        Hi=inv3(H[nm]); r=[]
        for su,sv,wx,wy in clips[nm][key]:
            px,py=apply(Hi,*cur[(wx,wy)]); r.append(math.hypot(px-su,py-sv))
        print(f"        {nm:13} screen RMS {math.sqrt(sum(v*v for v in r)/len(r)):.3f} px")
pickle.dump({'Hf':Hf_new,'Hb':Hb_new}, open('Hframe.pkl','wb'))
