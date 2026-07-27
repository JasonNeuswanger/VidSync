# Calibration Reference Notes

Records the project files being used as reference data for validating VidSync's measurement
mathematics, and how to interpret them. Keep it updated as more reference sets are verified.

`.vsd` documents are SQLite-backed Core Data stores, so everything below can be read with
`sqlite3` without launching the application.

## Files with modernized distortion corrections

Opened and re-run through the current chessboard plumbline autodetection, and confirmed by eye
to have good detections and distortion parameters.

In `~/Library/CloudStorage/Dropbox/Drift Model Project/VidSync Projects/`:

- `2016-08-07-1 Panguingue.vsd`
- `2016-07-07-2 Panguingue.vsd`
- `2016-08-08-2 Panguingue.vsd`
- `2016-08-08-4 Panguingue.vsd`
- `2016-08-13-2 Chena.vsd` — 8 mm fisheye, murky water, poor contrast. The file that drove the
  seed-basis and run-end detector fixes. Hardest case so far.
- `2015-09-04-1 Clearwater.vsd`

## The fisheye residual in the 2016 field videos

Measured on `2016-08-13-2 Chena.vsd`, the 8 mm fisheye file, after the detector fixes.

Corner localisation noise, estimated independently of any distortion model from the four-point
centred stencil on uniformly spaced stretches of each plumbline, is **0.40 px** in both cameras.
The fit residual is **1.41 px**. So roughly 1.35 px of the residual is systematic structure that
the model is not capturing, and it is strongly radial:

| radius from distortion centre | n | residual rms |
|---|---|---|
| 0–200 px | 30 | **0.374 px** |
| 200–400 px | 104 | 0.645 |
| 400–600 px | 222 | 0.881 |
| 600–800 px | 312 | 1.500 |
| 800–1000 px | 351 | **1.768 px** |

Near the centre the residual is indistinguishable from corner noise: the model fits perfectly
where the field angle is small, and fails progressively where it is not. That is what a radial
model of the wrong shape looks like.

**But a fisheye radial model does not fix it.** Replacing the even-power series in r with the
form used for real fisheye lenses — `rho = rd/f`, `theta = rho(1 + a1 rho^2 + a2 rho^4 + a3
rho^6)`, `ru = f tan(theta)`, whose tangent is what lets a very wide field angle map to a
perspective image without diverging coefficients — gives 1.4194 px against Brown–Conrady's
1.4093, using three fewer parameters. Equally good, not better. Fitted focal length 1314 px.

So the leftover structure is radial but is not a deficiency of the radial function's algebraic
family. The leading remaining hypothesis is physical: the distortion target is a printed sign
held about 10 cm from a dome port, so a small bow in it puts real curvature into the "plumb"
lines, and the apparent non-straightness would grow toward the frame edges where the board is
most oblique and nearest. That is a hardware and protocol matter rather than a mathematical one,
and it would be tested by checking whether the residual pattern follows position on the *board*
across several frames rather than position in the *image*.

## Pool test reference set

`~/Library/CloudStorage/Dropbox/Chena Project Synced/VidSync Projects/2012-01-31_PoolTest/2012-01-31_PoolTest_2026_Reanalysis.vsd`

The validation set this project has been missing: **1010 two-point length measurements of
objects whose true length is known**, with updated distortion parameters. It is the only way to
judge a change in the mathematics on 3D measurement error rather than on a fit residual, which
has repeatedly proven misleading — an unconstrained fit can reach 0.0037 px per point while
being physically meaningless.

This is the data behind Table 1 of Neuswanger et al. (2016).

### Physical setup

The target is the same physical half-inch chessboard used for distortion calibration, but moved
around and filmed in many positions and orientations. **Its position during the length
measurements is unrelated to its position during plumbline calibration** — do not assume the two
are registered to each other.

One square is 0.5 inch = 12.7 mm exactly. World coordinates in the document are in **metres**.

### The one real trap: the `48squares` type is misnamed

Expected lengths are the square count times 12.7 mm, except for `48squares`, whose true length
is **596.9 mm = 47 squares**, not 609.6 mm. Both the object's own name (`Full Width 0.5969`) and
Table 1 of the paper give 596.9. Using the type name instead produces a spurious −9.4 mm bias,
larger than every real effect being looked for.

Where an object name embeds a number, that number is the authoritative true length in metres.

| Type | True length | Measurements |
|---|---|---|
| `4squares` | 50.8 mm | 688 |
| `12squares` | 152.4 mm | 122 |
| `30squares` | 381.0 mm | 107 |
| `48squares` | **596.9 mm** (47 squares, not 48) | 93 |

### Objects, and what each tests

| Object | Type | n | Scenario |
|---|---|---|---|
| `Ideal Distance Angle Sweep` | 4squares | 225 | Best case: near the cameras, favourable angles |
| `Flat View Distance Series` | 4squares | 433 | Target flat to the cameras, varying range |
| `Angle Distance Sweep` | 4squares | 30 | Oblique target angles |
| `12sq 0.1524m` | 12squares | 122 | Longer target |
| `Full Height 0.381` | 30squares | 107 | Longer still |
| `Full Width 0.5969` | 48squares | 93 | Longest |

### Baseline as of 2026-07-26

Measured with the distortion parameters currently stored in the file, as the 3D distance between
each event's two points. Any change to the mathematics should be judged against these.

| Object | n | mean (mm) | sd (mm) | true (mm) | bias (mm) |
|---|---|---|---|---|---|
| Ideal Distance Angle Sweep | 225 | 50.93 | 0.25 | 50.8 | +0.13 |
| Flat View Distance Series | 433 | 50.99 | 0.42 | 50.8 | +0.19 |
| Angle Distance Sweep | 30 | 52.18 | 1.23 | 50.8 | +1.38 |
| 12sq 0.1524m | 122 | 153.05 | 1.12 | 152.4 | +0.65 |
| Full Height 0.381 | 107 | 383.96 | 2.92 | 381.0 | +2.96 |
| Full Width 0.5969 | 93 | 600.20 | 3.64 | 596.9 | +3.30 |

Two things stand out. Bias is positive everywhere and grows with target length, which is the
length-dependent systematic error the paper's Discussion attributes to imperfections in the
calibration frame and its digitization. And the oblique-angle object is three to five times
worse than the two flat 4-square objects of identical true length, which the paper's Fig. 5b
reported no effect for.

### Reading it out

Tracked objects, types and events all live in the shared `ZVSVISIBLEITEM` table, distinguished by
`Z_ENT`: 17 events, 18 event types, 19 objects, 20 object types. Names sit in different columns
per entity — `ZNAME2` for objects, `ZNAME3` for types — because the shared table gives each
entity's `name` attribute its own column. Objects link to their type through `ZTYPE1`, and events
link to objects through the `Z_17TRACKEDOBJECTS` join table. 3D points are in `ZVSPOINT3D`,
joined by `ZTRACKEDEVENT`, carrying `ZMEANPLD`, `ZREPROJECTIONERRORNORM` and
`ZNEARESTCAMERADISTANCE` per point.

```sql
SELECT o.ZNAME2 AS object, t.ZNAME3 AS type, e.Z_PK AS event,
       p.ZWORLDX, p.ZWORLDY, p.ZWORLDZ,
       p.ZNEARESTCAMERADISTANCE, p.ZMEANPLD, p.ZREPROJECTIONERRORNORM
FROM ZVSVISIBLEITEM e
JOIN Z_17TRACKEDOBJECTS j ON j.Z_17TRACKEDEVENTS = e.Z_PK
JOIN ZVSVISIBLEITEM o ON o.Z_PK = j.Z_19TRACKEDOBJECTS
JOIN ZVSVISIBLEITEM t ON t.Z_PK = o.ZTYPE1
JOIN ZVSPOINT3D p ON p.ZTRACKEDEVENT = e.Z_PK
WHERE e.Z_ENT = 17
ORDER BY o.ZNAME2, e.Z_PK, p.ZINDEX;
```

Every event has exactly two points, so the measured length is the distance between them.

### The 2016 export, and what it enables

`~/Library/CloudStorage/Dropbox/Chena Project Synced/Papers/2010 3D Video Methods/2012 Pool Test - 2016 CalA.xml`

The results exported from this file in 2016 while preparing the paper, using calibration A —
the same calibration the current document uses. It holds far more than the 3D coordinates: for
every click it records the raw screen position, the undistorted position, and the projections
onto both calibration frame planes, plus both cameras' full calibrations and distortion
parameters. That makes it a self-contained testbed. Any triangulation method can be evaluated
straight from the frame-plane coordinates without reimplementing the homographies.

Points match the current document on the pair (event index, point index); neither is unique
alone. Note the event index is `ZINDEX` on the event row, not `ZINDEX1`.

### Two results measured from it, 2026-07-26

**Everything since 2016 is a small net gain.** Comparing the published coordinates against the
current document, per-point positions moved by a median of 0.26 mm, and mean absolute length
error went from 1.03 mm to 0.99 mm over all 1010 measurements — better on the four harder
objects, unchanged on the two easy ones.

Do not read that 4% as evidence that distortion correction matters little in general. It is
specific to this file, and for two reasons: the 2012 pool test was shot on a camera with only
mild radial distortion, and its chessboard was already digitized cleanly by the old detector, so
there was little on the table either way. The 2015–2016 field videos were shot on far wider
lenses with much more distortion, and it is there that the detector work pays.

The useful consequence is the opposite of what the number first suggests. Because distortion is
nearly a non-factor here, this file isolates the *geometry* — the homographies, the two-plane
sightline construction, the triangulation and the calibration frame itself. It is the right
platform for testing geometric ideas precisely because the distortion term is close to
controlled.

**The iterative reprojection refinement earns its place.** Recomputing every measurement as the
plain closest point of approach of the two sightlines, and comparing against the stored
iteratively refined result:

| | mean abs. error | sd |
|---|---|---|
| iterative refinement (as shipped) | **1.03 mm** | 1.97 |
| linear CPA only | 1.35 mm | 5.10 |

Better on every object, and far more stable — the linear method's standard deviation on the
longest target is 15.3 mm against 3.6. This confirms on real data what the paper asserts, and
means the refinement step is load-bearing rather than cosmetic. Anything that makes it valid in
cases it currently is not, such as filming through an aquarium wall, is improving a step that
demonstrably matters.

### The bias is driven by range, not by target length

Table 1 of the paper shows absolute error growing with target length, and the Discussion
attributes it to a warped reconstructed space in which a longer object accumulates
proportionally more error. Measured against range, that reading does not survive.

Correlation of the scale error (measured ÷ true − 1) with camera distance is **+0.618**; with
true target length it is **+0.084**. The apparent length effect is confounding: the longer
targets did not fit in frame close up, so they were filmed farther away. Holding length exactly
constant by using only the 688 measurements of the 50.8 mm target:

| mean camera distance | n | scale error |
|---|---|---|
| under 500 mm | 183 | **+0.006%** |
| 500–700 mm | 241 | +0.282% |
| 700–900 mm | 80 | +0.203% |
| 900–1200 mm | 30 | +0.192% |
| 1200–1600 mm | 45 | +0.717% |
| over 1600 mm | 109 | **+1.586%** |

Conversely, holding distance to a 400–900 mm band, the scale error across the four length
classes is 0.24%, 0.17%, 0.32% and 0.10% — no trend.

Inside the calibrated depth range the measurements are essentially unbiased; the bias appears
and grows as the target moves beyond the frame. That signature — error growing with range
rather than with size — is what an angular error in the lines of sight produces. A small
position error at each calibration plane, divided by the 0.439 m separation between them, is an
angular error in the sightline, and its effect on a triangulated point grows with distance. It
is not what a scale error in the reconstructed space would produce, which would be a constant
proportional error at every range.

This points at the accuracy of the two homographies, and at their consistency with each other,
as the dominant remaining error source in this file — not at the distortion model, and not at
the triangulation search.

### Three things tried against the range bias, none of which worked

All evaluated by refitting from the calibration clicks in the export and re-triangulating all
1010 measurements, so the calibration points are the training set and the measurements are an
independent test set.

**Geometric refinement of each homography: no effect.** Replacing the normalized DLT's algebraic
error with the statistically correct objective — minimizing squared error in the clicked screen
positions, where the noise actually is — moved the calibration residual from 2.320 to 2.319 px.
With well-spread points and Hartley normalization, the algebraic and geometric optima coincide
to four significant figures. Hartley and Zisserman's gold standard matters when the DLT is
poorly conditioned; here normalization has already done the work. This item can be closed.

**Estimating the frame's true node positions: actively harmful.** Both cameras' residuals are
worst at the *same* physical nodes, and the world-space displacements they imply agree across
cameras with correlations of +0.95 and +0.78 — independent click error would give roughly zero.
Estimating each node's position from that agreement, iterating with a similarity gauge so the
grid's measured overall size is preserved, cuts the calibration residual four-fold, from 2.32 to
0.58 px. It then makes every object's measurement error slightly *worse*: 3.93 to 4.18 mm on the
30-square target, 5.90 to 6.07 on the 48-square. The correlated displacements are therefore not
frame construction error but something shared between the two views — residual distortion is the
obvious candidate, since the cameras are similar and view the frame from similar angles. A
four-fold gain in calibration residual buying a small loss in measurement accuracy is worth
remembering as a caution about judging calibration changes by their own residual.

**Adjusting the assumed plane separation: negligible.** Every sightline is defined by the
0.4390 m front-to-back separation, so an error there tilts every ray. Scanning it from 0.429 to
0.464 m moves the far-field bias from +1.467% to +1.702% — a 2.3% change in the separation buys
0.07 percentage points. There is no minimum in the plausible range.

**What the bias is not.** At matched range, targets oriented along the viewing axis and across
it show the same error (+0.33% versus +0.23% in the 500–900 mm band), so the reconstructed space
is not stretched along the depth axis; it is uniformly scaled, by an amount that grows with
range. That is the signature of the two cameras' ray bundles converging slightly wrongly, which
at long range, where the convergence angle is small, turns a fixed angular error into a growing
depth error.

The remedy the paper already found for this is protocol rather than mathematics: Table 1 shows
Calibration B, taken 0.3 m farther out, giving 1.4% error at long range where Calibration A gave
2.1%. Calibrating at the intended working distance, using a larger front-to-back separation, and
widening the camera baseline all attack it. Nothing in the reconstruction mathematics, given
these inputs, appears to.

### The camera centre is doing real work, and removing it costs the whole gain

The proposal was to reformulate the iterative refinement so it does not need a camera position:
for a candidate 3D point, find the screen point whose two-plane sightline passes through it, by
fixing the depth parameter t and solving `(1-t)Hf(s) + t Hb(s) = (Px,Pz)` for s. The motive was
that a single perspective centre is wrong whenever light bends before reaching the camera —
through an aquarium wall, or an off-centre dome port — which is exactly the case VidSync's
two-plane method is otherwise built to handle.

Implemented and run over all 1010 measurements against the two existing methods:

| triangulation | mean abs. error | bias | sd |
|---|---|---|---|
| linear CPA | 1.368 mm | +1.127 | 5.18 |
| iterative, via camera centre (as shipped) | **1.036 mm** | +0.925 | 1.97 |
| iterative, camera-free | 1.372 mm | +1.127 | 5.16 |

The camera-free version lands back on the linear CPA and throws away the entire benefit of
refining. The inner Newton solve is not at fault: it converged on all 4040 calls, and at the CPA
seed its screen residual is a median 0.48 px against the camera-centre method's 1.83 px. That
gap is the explanation. The camera-free objective is nearly satisfied wherever the CPA already
is, because a screen-space residual measured along a sightline is close to the point-to-line
distance that CPA minimizes, so there is almost nothing for it to move.

The camera centre is not a convenience standing in for the true ray geometry. It is estimated
from all twenty back-node sightlines at once, and using it replaces a per-point ray direction —
derived from two homographies evaluated at a single noisy screen location — with a low-variance
global anchor. That variance reduction is the 24% gain. Removing the centre removes the
constraint that was providing it.

So the reformulation as proposed is dead. What survives is the question it raises: if the value
lies in an aggregate constraint rather than in centrality, a per-camera ray model that is
aggregate but *not* required to pass through one point would keep the variance reduction while
remaining valid under refraction. Through a flat wall or a dome port the ray bundle is not
central, but it is smooth and low-dimensional, so a regularized ray field fitted to all the
calibration sightlines is the natural successor. That is research rather than a fix, and it is
untested.

Note also that the pinhole assumption is already measurably imperfect here, with no aquarium
wall involved: the back-node sightlines miss their own fitted centre by a median of 0.65 and
0.83 mm for the two cameras, and up to 1.70 mm, against measurement errors of about 1 mm. Some
of that is calibration noise rather than genuine non-central geometry.

### Obliquity does not affect accuracy

An earlier reading of the per-object table suggested that the oblique-angle object was three to
five times worse than flat targets of the same length, contradicting Fig. 5b of the paper. That
was wrong, and it was a range confound: `Angle Distance Sweep` was filmed at a median range of
3799 mm against 556 and 656 mm for the two flat 4-square objects.

Computing the obliquity of every measurement directly, as the angle of the target segment away
from perpendicular to the line of sight, and correlating it against scale error over all 1010
measurements gives **−0.041**, and −0.231 within the 500–900 mm band, where more oblique is very
slightly *better*. At matched range the scale error across obliquity bins is 0.33%, 0.21% and
0.23%. The paper's finding of no angle effect stands.

### How to use it

Judge any change on bias and standard deviation per object, split by `ZNEARESTCAMERADISTANCE`
the way Table 1 splits by range. Report static-target accuracy separately from anything
involving moving subjects: synchronization error and motion blur do not appear here at all.

To compare two versions of the mathematics fairly, both must be applied to the same clicked
screen coordinates rather than to the stored 3D results, since the stored coordinates only
change when points are recalculated. The clicks are preserved in `ZVSSCREENPOINT` (`Z_ENT` 12,
`VSEventScreenPoint`), each tied to the video clip and calibration it belongs to.
