import math, pickle, collections, xml.etree.ElementTree as ET
from homog import apply, XML
from refine import cpa, inv3
D=0.439000010490417
TRUE={'4squares':50.8,'12squares':152.4,'30squares':381.0,'48squares':596.9}
base=pickle.load(open('H.pkl','rb')); clips=base['clips']
H={nm:{'f':base['H'][nm]['dlt'][0],'b':base['H'][nm]['dlt'][1]} for nm in clips}

# camera centres, as VidSync computes them: CPA of the back-node sightlines
CAM={}
for nm in clips:
    lines=[]
    for su,sv,wx,wy in clips[nm]['back']:
        fh,fv=apply(H[nm]['f'],su,sv); bh,bv=apply(H[nm]['b'],su,sv)
        lines.append(((fh,0.0,fv),(bh,D,bv)))
    CAM[nm]=cpa(lines)

def reproject_via_camera(nm,P):
    """VidSync's method: line from the camera centre through P, hit the front plane, map to screen."""
    C=CAM[nm]
    dy=P[1]-C[1]
    if abs(dy)<1e-12: return None
    t=(0.0-C[1])/dy
    fx=C[0]+t*(P[0]-C[0]); fz=C[2]+t*(P[2]-C[2])
    return apply(inv3(H[nm]['f']),fx,fz)

def reproject_camera_free(nm,P,seed):
    """No camera centre. Find the screen point whose two-plane sightline passes through P.
       Along that sightline the depth is linear, so t is fixed by P's depth, and the remaining
       two equations (1-t)Hf(s) + t Hb(s) = (Px,Pz) are solved for s by Newton from the click."""
    t=P[1]/D
    Hf=H[nm]['f']; Hb=H[nm]['b']
    def F(s):
        fx,fz=apply(Hf,s[0],s[1]); bx,bz=apply(Hb,s[0],s[1])
        return ((1-t)*fx+t*bx-P[0], (1-t)*fz+t*bz-P[2])
    s=list(seed)
    for _ in range(30):
        f=F(s)
        if abs(f[0])<1e-12 and abs(f[1])<1e-12: break
        h=1e-3
        fa=F([s[0]+h,s[1]]); fb=F([s[0],s[1]+h])
        J=[[(fa[0]-f[0])/h,(fb[0]-f[0])/h],[(fa[1]-f[1])/h,(fb[1]-f[1])/h]]
        det=J[0][0]*J[1][1]-J[0][1]*J[1][0]
        if abs(det)<1e-20: return None
        dx=(-f[0]*J[1][1]+f[1]*J[0][1])/det
        dy=(-f[1]*J[0][0]+f[0]*J[1][0])/det
        s=[s[0]+dx,s[1]+dy]
        if abs(dx)<1e-9 and abs(dy)<1e-9: break
    if math.hypot(s[0]-seed[0],s[1]-seed[1])>400: return None   # reject a runaway/spurious root
    return (s[0],s[1])

def nelder_mead(cost,x0,step=0.002,iters=400):
    n=3; simp=[list(x0)]
    for i in range(n):
        p=list(x0); p[i]+=step; simp.append(p)
    val=[cost(p) for p in simp]
    for _ in range(iters):
        order=sorted(range(n+1),key=lambda i:val[i])
        simp=[simp[i] for i in order]; val=[val[i] for i in order]
        if abs(val[-1]-val[0])<1e-18: break
        cen=[sum(simp[i][k] for i in range(n))/n for k in range(n)]
        ref=[cen[k]+1.0*(cen[k]-simp[-1][k]) for k in range(n)]; fr=cost(ref)
        if fr<val[0]:
            exp=[cen[k]+2.0*(cen[k]-simp[-1][k]) for k in range(n)]; fe=cost(exp)
            simp[-1],val[-1]=(exp,fe) if fe<fr else (ref,fr)
        elif fr<val[-2]: simp[-1],val[-1]=ref,fr
        else:
            con=[cen[k]+0.5*(simp[-1][k]-cen[k]) for k in range(n)]; fc=cost(con)
            if fc<val[-1]: simp[-1],val[-1]=con,fc
            else:
                for i in range(1,n+1):
                    simp[i]=[(simp[i][k]+simp[0][k])/2 for k in range(n)]; val[i]=cost(simp[i])
    return simp[0]

meas=[]
r=ET.parse(XML).getroot()
for o in r.iter('object'):
    for e in o.iter('event'):
        pts=[]
        for p in e.iter('point'):
            sps=[(sp.get('videoClip'),float(sp.get('xu')),float(sp.get('yu'))) for sp in p.iter('screenpoint')]
            pts.append((sps,float(p.get('nearestCameraDistance') or 0)))
        if len(pts)==2 and all(len(x[0])==2 for x in pts): meas.append((o.get('type'),pts))

def solve_point(sps, mode):
    lines=[]
    for clip,xu,yu in sps:
        fh,fv=apply(H[clip]['f'],xu,yu); bh,bv=apply(H[clip]['b'],xu,yu)
        lines.append(((fh,0.0,fv),(bh,D,bv)))
    P0=cpa(lines)
    if mode=='cpa': return P0
    def cost(P):
        tot=0.0
        for clip,xu,yu in sps:
            s = reproject_via_camera(clip,P) if mode=='camera' else reproject_camera_free(clip,P,(xu,yu))
            if s is None: return 1e12
            tot+=(s[0]-xu)**2+(s[1]-yu)**2
        return tot
    return nelder_mead(cost,P0)

res={}
for mode,label in (('cpa','linear CPA'),('camera','iterative, camera centre'),('free','iterative, camera-free')):
    per=collections.defaultdict(list); bands=collections.defaultdict(list)
    for typ,pts in meas:
        P=[solve_point(sps,mode) for sps,_ in pts]
        L=math.dist(P[0],P[1])*1000.0; err=L-TRUE[typ]
        per[typ].append(err)
        d=1000*0.5*(pts[0][1]+pts[1][1])
        bands[0 if d<500 else 1 if d<900 else 2 if d<1600 else 3].append(err/TRUE[typ])
    allv=[v for k in per for v in per[k]]
    m=sum(allv)/len(allv); a=sum(abs(q) for q in allv)/len(allv)
    sd=(sum((q-m)**2 for q in allv)/len(allv))**.5
    res[label]=(a,m,sd,bands,per)
    print(f"{label:28} mean|err| {a:6.3f} mm   bias {m:+6.3f}   sd {sd:6.3f}")
print()
print(f"{'range band':>14} " + " ".join(f"{l:>22}" for l in res))
for i,bn in enumerate(('<500mm','500-900','900-1600','>1600')):
    cells=[]
    for l in res:
        b=res[l][3].get(i,[])
        cells.append(f"{100*sum(b)/len(b):>+21.3f}%" if b else " "*22)
    print(f"{bn:>14} " + " ".join(cells))
pickle.dump(res,open('cf.pkl','wb'))
