import math, pickle, collections, xml.etree.ElementTree as ET
from homog import dlt, apply, XML
from refine import cpa
BACK=0.439000010490417
TRUE={'4squares':50.8,'12squares':152.4,'30squares':381.0,'48squares':596.9}
base=pickle.load(open('H.pkl','rb')); clips=base['clips']
Hbase={nm:{'f':base['H'][nm]['dlt'][0],'b':base['H'][nm]['dlt'][1]} for nm in clips}
fr=pickle.load(open('Hframe.pkl','rb'))
Hframe={nm:{'f':fr['Hf'][nm],'b':fr['Hb'][nm]} for nm in clips}

meas=[]
r=ET.parse(XML).getroot()
for o in r.iter('object'):
    typ=o.get('type'); nm=o.get('name')
    for e in o.iter('event'):
        pts=[]
        for p in e.iter('point'):
            sps=[]
            for sp in p.iter('screenpoint'):
                sps.append((sp.get('videoClip'), float(sp.get('xu')), float(sp.get('yu'))))
            pts.append((sps, float(p.get('nearestCameraDistance') or 0)))
        if len(pts)==2 and all(len(p[0])==2 for p in pts):
            meas.append((typ,nm,pts))
print(f"{len(meas)} measurements loaded\n")

def evaluate(H,label):
    out=collections.defaultdict(list); bands=collections.defaultdict(list)
    for typ,nm,pts in meas:
        P=[]
        for sps,dist in pts:
            lines=[]
            for clip,xu,yu in sps:
                fh,fv=apply(H[clip]['f'],xu,yu); bh,bv=apply(H[clip]['b'],xu,yu)
                lines.append(((fh,0.0,fv),(bh,BACK,bv)))
            P.append(cpa(lines))
        L=math.dist(P[0],P[1])*1000.0
        err=L-TRUE[typ]
        out[nm].append(err)
        d=1000*0.5*(pts[0][1]+pts[1][1])
        bands[(d<500,500<=d<900,900<=d<1600,d>=1600).index(True)].append(err/TRUE[typ])
    return out,bands

res={}
for label,H in (('DLT (as shipped)',Hbase),('frame-corrected',Hframe)):
    res[label]=evaluate(H,label)
print(f"{'object':28} {'n':>4} | " + " | ".join(f"{l:>22}" for l in res))
allv={l:[] for l in res}
for nm in sorted(res['DLT (as shipped)'][0]):
    row=f"{nm:28} {len(res['DLT (as shipped)'][0][nm]):>4} | "
    cells=[]
    for l in res:
        v=res[l][0][nm]; allv[l]+=v
        m=sum(v)/len(v); a=sum(abs(q) for q in v)/len(v)
        cells.append(f"bias{m:>+7.2f} |err|{a:>6.2f}")
    print(row+" | ".join(cells))
row=f"{'ALL':28} {len(allv['DLT (as shipped)']):>4} | "
cells=[]
for l in res:
    v=allv[l]; m=sum(v)/len(v); a=sum(abs(q) for q in v)/len(v)
    sd=(sum((q-m)**2 for q in v)/len(v))**.5
    cells.append(f"bias{m:>+7.2f} |err|{a:>6.2f}")
print(row+" | ".join(cells))
print()
names=['under 500 mm','500-900 mm','900-1600 mm','over 1600 mm']
print(f"{'range band':>14} {'n':>5} | " + " | ".join(f"{l:>18}" for l in res))
for i,bn in enumerate(names):
    cells=[]
    for l in res:
        b=res[l][1].get(i,[])
        cells.append(f"scale err {100*sum(b)/len(b):>+7.3f}%" if b else " "*18)
    n=len(res['DLT (as shipped)'][1].get(i,[]))
    print(f"{bn:>14} {n:>5} | " + " | ".join(cells))
