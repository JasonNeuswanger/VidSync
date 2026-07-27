import math, pickle, collections, xml.etree.ElementTree as ET
from homog import apply, XML
from refine import cpa
TRUE={'4squares':50.8,'12squares':152.4,'30squares':381.0,'48squares':596.9}
base=pickle.load(open('H.pkl','rb')); clips=base['clips']
H={nm:{'f':base['H'][nm]['dlt'][0],'b':base['H'][nm]['dlt'][1]} for nm in clips}
meas=[]
r=ET.parse(XML).getroot()
for o in r.iter('object'):
    for e in o.iter('event'):
        pts=[]
        for p in e.iter('point'):
            sps=[(sp.get('videoClip'),float(sp.get('xu')),float(sp.get('yu'))) for sp in p.iter('screenpoint')]
            pts.append((sps,float(p.get('nearestCameraDistance') or 0)))
        if len(pts)==2 and all(len(x[0])==2 for x in pts): meas.append((o.get('type'),pts))
def run(D):
    errs=[]; bands=collections.defaultdict(list)
    for typ,pts in meas:
        P=[]
        for sps,dist in pts:
            lines=[]
            for clip,xu,yu in sps:
                fh,fv=apply(H[clip]['f'],xu,yu); bh,bv=apply(H[clip]['b'],xu,yu)
                lines.append(((fh,0.0,fv),(bh,D,bv)))
            P.append(cpa(lines))
        L=math.dist(P[0],P[1])*1000.0; e=L-TRUE[typ]
        errs.append(abs(e))
        d=1000*0.5*(pts[0][1]+pts[1][1])
        b=0 if d<500 else 1 if d<900 else 2 if d<1600 else 3
        bands[b].append(e/TRUE[typ])
    return sum(errs)/len(errs), {k:100*sum(v)/len(v) for k,v in bands.items()}
print("Scanning the assumed front-to-back plane separation.")
print("The nominal value is 0.4390 m; every sightline is defined by it, so an error here tilts")
print("every ray and its effect on a triangulated point grows with range.\n")
print(f"{'separation (m)':>15} {'mean |err| mm':>14} | {'<500mm':>9} {'500-900':>9} {'900-1600':>9} {'>1600':>9}")
best=None
for D in [0.4290,0.4340,0.4390,0.4440,0.4490,0.4540,0.4640]:
    a,b=run(D)
    mark=""
    if best is None or a<best[1]: best=(D,a); 
    print(f"{D:>15.4f} {a:>14.3f} | " + " ".join(f"{b.get(i,float('nan')):>+9.3f}" for i in range(4)))
print(f"\nbest of those scanned: {best[0]:.4f} m at {best[1]:.3f} mm mean absolute error")
