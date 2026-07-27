import math, xml.etree.ElementTree as ET
XML='/Users/jason/Library/CloudStorage/Dropbox/Chena Project Synced/Papers/2010 3D Video Methods/2012 Pool Test - 2016 CalA.xml'
def svd_null(A):
    """Right singular vector of smallest singular value, via Jacobi eigen of A^T A."""
    n=len(A[0]); M=[[sum(A[r][i]*A[r][j] for r in range(len(A))) for j in range(n)] for i in range(n)]
    V=[[1.0 if i==j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(100):
        off=0.0; p=q=0; best=0.0
        for i in range(n):
            for j in range(i+1,n):
                off+=M[i][j]**2
                if abs(M[i][j])>best: best=abs(M[i][j]); p,q=i,j
        if off<1e-30: break
        app,aqq,apq=M[p][p],M[q][q],M[p][q]
        th=0.5*math.atan2(2*apq,aqq-app); c,s=math.cos(th),math.sin(th)
        for k in range(n):
            mkp,mkq=M[k][p],M[k][q]
            M[k][p]=c*mkp-s*mkq; M[k][q]=s*mkp+c*mkq
        for k in range(n):
            mpk,mqk=M[p][k],M[q][k]
            M[p][k]=c*mpk-s*mqk; M[q][k]=s*mpk+c*mqk
        for k in range(n):
            vkp,vkq=V[k][p],V[k][q]
            V[k][p]=c*vkp-s*vkq; V[k][q]=s*vkp+c*vkq
    idx=min(range(n), key=lambda i: M[i][i])
    return [V[r][idx] for r in range(n)]
def dlt(pairs):
    """pairs: [(su,sv,wx,wy)] undistorted screen -> world plane. Normalized DLT, H maps screen->world."""
    n=len(pairs)
    scx=sum(p[0] for p in pairs)/n; scy=sum(p[1] for p in pairs)/n
    wcx=sum(p[2] for p in pairs)/n; wcy=sum(p[3] for p in pairs)/n
    sN=sum(math.hypot(p[0]-scx,p[1]-scy) for p in pairs)/n
    wN=sum(math.hypot(p[2]-wcx,p[3]-wcy) for p in pairs)/n
    ss=math.sqrt(2)/sN; ws=math.sqrt(2)/wN
    A=[]
    for su,sv,wx,wy in pairs:
        X=(su-scx)*ss; Z=(sv-scy)*ss; x=(wx-wcx)*ws; z=(wy-wcy)*ws
        A.append([X,Z,1,0,0,0,-x*X,-x*Z,-x])
        A.append([0,0,0,X,Z,1,-z*X,-z*Z,-z])
    h=svd_null(A)
    if h[8]<0: h=[-v for v in h]
    H=[h[0:3],h[3:6],h[6:9]]
    Nrm=[[ss,0,-ss*scx],[0,ss,-ss*scy],[0,0,1]]
    Den=[[1/ws,0,wcx],[0,1/ws,wcy],[0,0,1]]
    def mm(A,B): return [[sum(A[i][k]*B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mm(Den,mm(H,Nrm))
def apply(H,u,v):
    d=H[2][0]*u+H[2][1]*v+H[2][2]
    return ((H[0][0]*u+H[0][1]*v+H[0][2])/d,(H[1][0]*u+H[1][1]*v+H[1][2])/d)
def parse_matrix(s):
    s=s.replace('{','').replace('}','')
    v=[float(x) for x in s.split(',')]
    return [v[0:3],v[3:6],v[6:9]]
def load():
    r=ET.parse(XML).getroot()
    clips={}
    for vc in r.iter('videoClip'):
        c=vc.find('calibration')
        d={'name':vc.get('name'),
           'Hf_exported':parse_matrix(c.get('matrixScreenToQuadratFront')),
           'Hb_exported':parse_matrix(c.get('matrixScreenToQuadratBack')),
           'cam':(float(c.get('cameraX')),float(c.get('cameraY')),float(c.get('cameraZ')))}
        for tag,key in (('frontCalibrationPoints','front'),('backCalibrationPoints','back')):
            pts=[]
            for sp in c.find(tag):
                pts.append((float(sp.get('xu')),float(sp.get('yu')),
                            float(sp.get('worldHcoord')),float(sp.get('worldVcoord'))))
            d[key]=pts
        clips[vc.get('name')]=d
    return clips
if __name__=='__main__':
    clips=load()
    for nm,d in clips.items():
        print(f"=== {nm} ===")
        for key,exp in (('front','Hf_exported'),('back','Hb_exported')):
            H=dlt(d[key]); E=d[exp]
            sc=E[2][2]/H[2][2]
            rel=max(abs(H[i][j]*sc-E[i][j])/max(abs(E[i][j]),1e-9) for i in range(3) for j in range(3))
            resid=sum(math.dist(apply(E,p[0],p[1]),(p[2],p[3])) for p in d[key])/len(d[key])
            print(f"  {key:5} n={len(d[key]):2}  my DLT vs exported: max rel diff {rel:.2e}   exported world residual {resid*1000:.3f} mm")
