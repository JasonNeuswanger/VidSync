import math, collections, xml.etree.ElementTree as ET
from homog import dlt, apply, load, XML
BACK=0.439000010490417
TRUE={'4squares':50.8,'12squares':152.4,'30squares':381.0,'48squares':596.9}

def inv3(H):
    a,b,c=H[0]; d,e,f=H[1]; g,h,i=H[2]
    A=e*i-f*h; B=-(d*i-f*g); C=d*h-e*g
    det=a*A+b*B+c*C
    return [[A/det,(c*h-b*i)/det,(b*f-c*e)/det],
            [B/det,(a*i-c*g)/det,(c*d-a*f)/det],
            [C/det,(b*g-a*h)/det,(a*e-b*d)/det]]

def screen_resid(H, pts):
    """residual vector: clicked undistorted screen minus H^-1(world). Noise lives in the clicks."""
    Hi=inv3(H); r=[]
    for su,sv,wx,wy in pts:
        px,py=apply(Hi,wx,wy)
        r.append(px-su); r.append(py-sv)
    return r

def refine_geometric(H0, pts, iters=200):
    """Levenberg-Marquardt on the 8 free parameters of H (h22 fixed at 1)."""
    p=[H0[i][j]/H0[2][2] for i in range(3) for j in range(3)][:8]
    def build(p): return [[p[0],p[1],p[2]],[p[3],p[4],p[5]],[p[6],p[7],1.0]]
    def cost(p):
        r=screen_resid(build(p),pts); return sum(v*v for v in r)
    lam=1e-3; c=cost(p)
    for _ in range(iters):
        r=screen_resid(build(p),pts); m=len(r)
        J=[[0.0]*8 for _ in range(m)]
        for k in range(8):
            step=max(abs(p[k]),1e-8)*1e-6
            q=p[:]; q[k]+=step
            rk=screen_resid(build(q),pts)
            for i in range(m): J[i][k]=(rk[i]-r[i])/step
        A=[[sum(J[i][a]*J[i][b] for i in range(m)) for b in range(8)] for a in range(8)]
        g=[-sum(J[i][a]*r[i] for i in range(m)) for a in range(8)]
        improved=False
        for _try in range(12):
            M=[A[i][:] for i in range(8)]
            for i in range(8): M[i][i]*=(1.0+lam)
            aug=[M[i]+[g[i]] for i in range(8)]
            ok=True
            for col in range(8):
                piv=max(range(col,8),key=lambda rr:abs(aug[rr][col]))
                if abs(aug[piv][col])<1e-20: ok=False; break
                aug[col],aug[piv]=aug[piv],aug[col]
                for rr in range(8):
                    if rr==col: continue
                    f=aug[rr][col]/aug[col][col]
                    for cc in range(col,9): aug[rr][cc]-=f*aug[col][cc]
            if not ok: lam*=10; continue
            d=[aug[i][8]/aug[i][i] for i in range(8)]
            q=[p[i]+d[i] for i in range(8)]
            cq=cost(q)
            if cq<c: p=q; c=cq; lam=max(lam*0.3,1e-12); improved=True; break
            lam*=10
        if not improved: break
    return build(p)

def cpa(lines):
    A=[[0.0]*3 for _ in range(3)]; b=[0.0]*3
    for P,Q in lines:
        d=[Q[i]-P[i] for i in range(3)]; L=math.sqrt(sum(v*v for v in d))
        v=[x/L for x in d]
        for i in range(3):
            for j in range(3): A[i][j]+=(1.0 if i==j else 0.0)-v[i]*v[j]
            b[i]+=sum(((1.0 if i==k else 0.0)-v[i]*v[k])*P[k] for k in range(3))
    M=[A[i][:]+[b[i]] for i in range(3)]
    for c in range(3):
        piv=max(range(c,3),key=lambda r:abs(M[r][c]))
        M[c],M[piv]=M[piv],M[c]
        for r in range(3):
            if r==c: continue
            f=M[r][c]/M[c][c]
            for k in range(c,4): M[r][k]-=f*M[c][k]
    return [M[i][3]/M[i][i] for i in range(3)]

clips=load()
H={}
for nm,d in clips.items():
    Hf0=dlt(d['front']); Hb0=dlt(d['back'])
    H[nm]={'dlt':(Hf0,Hb0),
           'geo':(refine_geometric(Hf0,d['front']), refine_geometric(Hb0,d['back']))}
    for tag,(hf,hb) in H[nm].items():
        rf=screen_resid(hf,d['front']); rb=screen_resid(hb,d['back'])
        pf=math.sqrt(sum(v*v for v in rf)/(len(rf)//2)); pb=math.sqrt(sum(v*v for v in rb)/(len(rb)//2))
        print(f"{nm:13} {tag:4}  screen reprojection RMS: front {pf:6.3f} px   back {pb:6.3f} px")
import pickle
pickle.dump({'H':H,'clips':clips}, open('H.pkl','wb'))
