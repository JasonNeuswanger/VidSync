"""Isolate convergence quality: VidSync's own far-set fit against a thorough refit of the same data.

Only the left camera's distortion differs between the two arms; the right camera is held at the
document's stored parameters in both. So this is a clean A/B on how hard the plumbline objective was
optimized, with identical input data and identical downstream code.
"""
import importlib.util, math, os, re, sqlite3, sys
from collections import defaultdict
HERE='/Users/jason/Documents/VidSync/tools/pooltest'
def lm(n):
    sp=importlib.util.spec_from_file_location(n,os.path.join(HERE,n+'.py'))
    m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
fitter=lm('fitter'); dc=lm('distcal'); mt=lm('modeltest')

db=sqlite3.connect(f"file:{dc.VSD}?mode=ro",uri=True)
cams={}
for pk,clip,ah,av,fd,bd,*dp in db.execute(
    "SELECT c.Z_PK,v.ZCLIPNAME,c.ZAXISHORIZONTAL,c.ZAXISVERTICAL,c.ZPLANECOORDFRONT,c.ZPLANECOORDBACK,"
    "c.ZDISTORTIONCENTERX,c.ZDISTORTIONCENTERY,c.ZDISTORTIONK1,c.ZDISTORTIONK2,c.ZDISTORTIONK3,"
    "c.ZDISTORTIONK4,c.ZDISTORTIONK5,c.ZDISTORTIONK6,c.ZDISTORTIONK7,c.ZDISTORTIONP1,c.ZDISTORTIONP2,"
    "c.ZDISTORTIONP3,c.ZDISTORTIONP4 FROM ZVSCALIBRATION c JOIN ZVSVIDEOCLIP v ON v.Z_PK=c.ZVIDEOCLIP"):
    cams[clip]={"pk":pk,"clip":clip,"ah":ah,"av":av,"front_d":fd,"back_d":bd,"stored":list(dp),
                "front":[],"back":[]}
bypk={c["pk"]:c for c in cams.values()}
for pk,x,y,h,v in db.execute("SELECT ZCALIBRATION,ZSCREENX,ZSCREENY,ZWORLDHCOORD,ZWORLDVCOORD FROM ZVSSCREENPOINT WHERE ZCALIBRATION IS NOT NULL ORDER BY ZINDEX"):
    bypk[pk]["front"].append((x,y,h,v))
for pk,x,y,h,v in db.execute("SELECT ZCALIBRATION1,ZSCREENX,ZSCREENY,ZWORLDHCOORD,ZWORLDVCOORD FROM ZVSSCREENPOINT WHERE ZCALIBRATION1 IS NOT NULL ORDER BY ZINDEX"):
    bypk[pk]["back"].append((x,y,h,v))
clicks=defaultdict(dict)
for pt,clip,x,y in db.execute("SELECT p.ZPOINT,v.ZCLIPNAME,p.ZSCREENX,p.ZSCREENY FROM ZVSSCREENPOINT p JOIN ZVSVIDEOCLIP v ON v.Z_PK=p.ZVIDEOCLIP WHERE p.ZPOINT IS NOT NULL"):
    clicks[pt][clip]=(x,y)
events,names=defaultdict(list),{}
for name,ev,pk in db.execute("SELECT o.ZNAME2,e.Z_PK,p.Z_PK FROM ZVSVISIBLEITEM e JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS=e.Z_PK JOIN ZVSVISIBLEITEM o ON o.Z_PK=j.Z_19TRACKEDOBJECTS JOIN ZVSVISIBLEITEM t ON t.Z_PK=o.ZTYPE1 JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT=e.Z_PK WHERE e.Z_ENT=17 AND t.ZNAME3='Length Tests' ORDER BY e.Z_PK,p.ZINDEX"):
    events[ev].append(pk); names[ev]=name
db.close()

# VidSync's own far-set fit, from the export
s=open('/Users/jason/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/Exports/2015-09-04-1 Clearwater - FarDistortionSetOnly.xml',encoding='utf-8').read()
i=s.find('<videoClip name="Left Camera"')
vs=[float(re.search(k+r'="(-?[\d.eE+]+)"',s[i:i+7000]).group(1)) for k in fitter.KEYS]

# a thorough refit of the very same far set
centre,stored,sets=fitter.load(dc.VSD,'Left Camera')
cells={tc:sorted(math.dist(a,b) for L in v for a,b in zip(L,L[1:]) if 1<math.dist(a,b)<400) for tc,v in sets.items()}
far=min(cells,key=lambda t:cells[t][len(cells[t])//2])
pl=fitter.Plumblines(sets[far])
mine,rms=fitter.fit(pl,fitter.MODELS['full-13'],centre,restarts=6)
ok,md,ratio=fitter.gate(mine,pl)

print(f"same 47-line far set, both arms; right camera held at its stored parameters")
print(f"  VidSync's own solve : {pl.rms(__import__('numpy').array(vs)):.4f} px")
print(f"  thorough refit      : {rms:.4f} px   gate {'PASS' if ok else 'REJECT'} (ratio {ratio:.2f})")
print()
print(f"  {'left-camera distortion':>24} {'mean abs err':>13} {'rms':>8} {'bias':>8} {'sd':>8}")
for lab,dist in (("VidSync's own solve",vs),("thorough refit",list(mine))):
    rows,pld=mt.measure(cams,clicks,events,names,{'Left Camera':dist,'Right Camera':cams['Right Camera']['stored']})
    su=mt.summarise(rows)
    print(f"  {lab:>24} {su['mae']:13.3f} {su['rms']:8.3f} {su['bias']:+8.3f} {su['sd']:8.3f}")
