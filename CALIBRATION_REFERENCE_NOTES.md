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

## Does distortion depend on subject distance? No, to within 0.05 px

Asked because a range-dependent distortion would explain several things at once: the 1.35 px of
systematic residual in the 8 mm fisheye fits, and the range-driven measurement bias in the pool
test. It would also invalidate the premise of plumbline calibration, which assumes a straight
line in the world images to a straight line whatever its distance.

### From first principles

For a **central** camera — one where all rays pass through a single point — distortion is a
function of field angle alone, and range is irrelevant. The imaging map factors as
`X -> direction(X - O) -> pixel`, so range is quotiented out before distortion is applied. Two
points on the same ray, a centimetre and a kilometre away, land on the same pixel by
construction. This is why a pinhole-plus-radial-distortion model works at all, and it is the
right default assumption.

There are exactly three ways out of it, and only the first produces range dependence *within* a
single frame:

1. **Non-central optics.** A flat port refracts by Snell's law at the interface, and the
   backward extensions of the refracted rays do not meet in a point — they envelope a caustic on
   the optical axis. A dome port is neutral only when the entrance pupil sits at the centre of
   curvature; off-centre, it refracts. Either way the camera has no single viewpoint, so the
   apparent bearing of a point acquires a term of order (viewpoint spread)/range. Effective
   distortion becomes a surface `g(r, 1/Z)` rather than a curve `g(r)`.
2. **Focus breathing.** Refocusing moves lens elements and changes the distortion coefficients.
   This is real, but it is a property of the lens *configuration*: at a fixed focus setting, near
   and far objects on one ray still share a pixel. It invalidates reusing a calibration across
   focus settings, not within a frame.
3. **Pupil aberration** — entrance pupil position drifting with field angle, the in-air version
   of (1), usually sub-millimetre.

For a dome of radius `Rd` with the pupil decentred by `e`, the refraction at incidence
`sin a ~ (e/Rd) sin th` deviates the ray by `~0.248 a` for n = 1.33, putting the effective
viewpoint about `0.248 e sin th` off axis. At focal length `f` and range `Z` that is an image
error of `0.248 f e sin th / Z`. With f = 1300 px, e = 5 mm and th = 60 degrees, this is 1.4 px
at Z = 1 m — the same size as the residual being chased, so the mechanism was worth taking
seriously rather than dismissing. A flat port would give tens of pixels, which is one reason
these rigs must have been domes.

### The test

The 67 documents in `Drift Model Project/VidSync Projects` all used the same chessboard, so
**cell size in pixels is a proxy for 1/Z**: a bigger cell means the board was closer. Across the
folder the cell size spans 71 to 184 px, a factor of 2.6 in range. `tools/pooltest/harvest.py`
and `tools/pooltest/rangetest.py` do the work; the latter is self-contained.

Three things have to be controlled, and each one changed the answer:

**Focal length.** Two lenses were carried, an 8 mm fisheye and a 10-17 mm zoom, and they were
swapped mid-day. `TrimmedVideoSiteDetails.csv` (from the field notes) carries the focal length
per site code. Without it, 2015-07-11-1 and 2015-07-11-2 Chena look like the same camera on the
same day fitting distortion 3.7x apart; they are 17 mm and 8 mm respectively.

**Gauge.** Straightness is invariant under any homography applied after undistortion, so a
plumbline fit determines the distortion only up to that gauge, and uniform scale about the
distortion centre is the part the Brown-Conrady series absorbs most easily. The absolute radial
displacement `r*R(r^2)` therefore estimates nothing: within one camera and one season it ranged
9.9 to 35.6 px at r = 400, which is gauge wander, not distortion. Measuring instead the **rms
departure of `r_u(r)` from proportionality** — the part that actually bends lines — gives a
number that behaves:

| focal length | n | median severity | spread within the lens |
|---|---|---|---|
| 8 mm | 35 | 82.8 px | 81.1 - 90.6 |
| 10 mm | 13 | 67.1 px | 62.0 - 68.6 |
| 13 mm | 6 | 33.1 px | 29.2 - 36.5 |
| 17 mm | 20 | 18.3 px | 16.2 - 20.3 |

Monotone in focal length, as it must be, and stable to about +/-6% within a lens. Any severity
metric that does not do this is measuring gauge.

**Radial coverage.** A closer board fills more of the frame, so its fit is constrained to a
larger radius and extrapolates better. This confound points the same way as the hypothesis and
is strong enough to fake it — see below.

### Result: null

*Severity against board distance*, within focal length and camera side, gave correlations of
-0.129, -0.371, -0.269, +0.067, +0.170 and +0.779 across the six groups; pooled after demeaning,
-0.138 (t = -1.13). The signs disagree, which a physical mechanism would not do. The one strong
group (17 mm right, n = 11) drifts 17.4 to 19.4 px of severity across a 1.86x range change, but
the 17 mm *left* camera scatters by the same +/-2 px with no trend at all.

*Cross-prediction* is the better test, because straightness is exactly the gauge-invariant
quantity and no severity metric is involved: apply one session's parameters to another session's
plumblines and see how straight they come out. Both fits are evaluated on the same points, all
inside `min(rmax_i, rmax_j)`, so neither is extrapolating.

| \|cell difference\| | pairs | median degradation |
|---|---|---|
| 0-5 px | 120 | 0.260 px |
| 5-15 px | 258 | 0.453 px |
| 15-30 px | 272 | 0.453 px |
| 30-50 px | 148 | 0.430 px |
| 50+ px | 54 | 0.418 px |

Flat from 5 px upward. Slope -0.0063 px per px of cell (t = -0.47); signed slope -0.0038
(t = -0.45). **Doubling the board's distance changes how well a calibration transfers by less
than 0.05 px.** The floor of 0.26 px at matched distance is what swapping calibrations costs
anyway, from rig and detection differences.

Without the coverage control the same table reads 0.50, 0.71, 0.75, 0.86, 0.84 with a signed
slope of -0.036 (t = -2.87), which looks like a real and even directional effect. It is
extrapolation. This is the third time in this project that a calibration-side metric has
produced a confident wrong answer; see the frame-node result above for the second.

### Consequence

Range dependence is not the explanation for the 1.35 px fisheye residual, and it cannot be the
explanation for the pool test's range bias either — on shape grounds, independently of the
measurement above. A 1/Z term is *largest at short range* and saturates as Z grows, so it
predicts error that flattens out with distance. The pool test's scale error does the opposite,
growing from +0.006% under 500 mm to +1.586% beyond 1600 mm and accelerating. That is the
signature of a fixed angular error in the sightlines, which is where the earlier homography work
already pointed.

Distortion is a function of angle, not of subject distance, and for these rigs it is so to
within 0.05 px over a 2.6-fold change in range. The practical corollary is a reassuring one:
**the board's distance during plumbline calibration does not matter**, so it can be placed
wherever it is best detected — filling the frame, which improves radial coverage, is free.

### Side finding: one mislabelled record

`2016-06-16-1 Panguingue` is recorded as 8 mm in the field notes, but both its cameras fit a
severity of 18.2 px, squarely inside the 17 mm population (16.2-20.3) and nowhere near the 8 mm
one (81.1-90.6). Either the sheet's focal length is wrong for that site or the document is
carrying a calibration from a 17 mm session. Worth checking before that file is used.

## The gauge is harmless to the geometry, but the refinement's objective is in the wrong space

Asked whether the "flattened" image produced by undistortion might contain a warp that the
two-plane homographies cannot represent, over and above leftover distortion.

**It cannot, and that is a theorem.** By the fundamental theorem of projective geometry, a
bijective map of the plane that carries collinear points to collinear points is necessarily a
projective transformation. There is no third category: no line-preserving-but-non-projective
warp exists. So if undistortion genuinely straightens every straight world line, the flattened
image differs from a true perspective image by exactly a homography `G`. Then the map from
undistorted image to any world plane is `G^-1` composed with a plane back-projection — a
homography — so `Hf` and `Hb` are exact, the line joining `Hf(s)` and `Hb(s)` is the true
physical ray, and the whole two-plane construction is exact *including* the gauge. Nothing needs
to be done about the scale degeneracy in the distortion parameters; the homographies eat it.

The theorem's hypotheses are where the real failure modes live, and each is already instrumented:

* **Bijectivity.** If the undistortion folds over, the theorem does not apply. This is exactly
  what the Tier 1 acceptance gate tests with `min det J > 0` over the plumbline bounding box. The
  gate is enforcing the theorem's precondition, not just guarding against silly numbers.
* **Every direction, not only the sampled ones.** Straightness is enforced on two near-orthogonal
  families from a single board pose, so a map could straighten rows and columns while bending
  diagonals. That is what the held-out diagonal residual measures. On `2016-08-13-2 Chena` it is
  1.42 and 0.98 px against in-sample 1.33 and 1.27, so diagonals are as straight as rows and the
  map really is a collineation.
* **Only where plumblines reach.** Outside the covered radius the constraint is vacuous and gauge
  wander becomes real error. This was measured: it accounted for the entire apparent range effect
  in the section above, a fake trend of 0.50 to 0.86 px.
* **Exactness.** By the converse of the theorem, residual non-straightness is *precisely* the part
  no homography can absorb. The dichotomy is clean: gauge is free, residual is charged in full.
  All the effort belongs on the residual, none on normalizing the parameters.

### What is genuinely wrong: the refinement minimizes in undistorted pixels

`VSPoint.m` accumulates the iterative refinement's cost in *undistorted* coordinates, summed over
cameras:

```
cost += pow(reprojectedScreenPoint.x - p->undistortedScreenPoints[i].x, 2) + ...
```

Click noise is isotropic in *raw* pixels. Undistortion magnifies it by the local Jacobian, so a
given physical click error of `d` contributes `|J d|^2`, not `|d|^2`. Measured as
`sqrt(det J)` at the points where measurements were actually clicked (`tools/pooltest/gauge.py`):

| document | camera | mean magnification | range over the frame |
|---|---|---|---|
| 2012 pool test | Left | 1.0268 | 1.000 - 1.103 |
| 2012 pool test | Right | 1.0230 | 1.000 - 1.074 |
| 2016-08-13-2 Chena, 8 mm | Right | 1.4390 | 1.000 - 3.310 |
| 2016-08-13-2 Chena, 8 mm | Left | 1.2660 | 1.001 - 3.056 |

Two separate effects:

* **Within a camera**, magnification runs 1.00 at the centre to 3.31 at the corner on the 8 mm
  fisheye, so a peripheral click is weighted **11x** a central one purely for where it sits in the
  frame. This is *not* a gauge artifact — it is present with a perfect calibration, because
  distortion has a varying Jacobian by definition. It is a plain misspecification of the
  least-squares objective, and it biases the solution toward satisfying peripheral clicks.
* **Between cameras**, the ratio is 1.1366 on the fisheye file, so the right camera's residuals
  count 29% more than the left's. Part of this is real and part is arbitrary gauge.

On the pool test the ratio is 1.0036, a 0.7% weighting error — negligible, and the reason the
pool test **cannot validate a fix for this**. The files where it bites are the wide fisheye ones,
which have no ground truth.

The first-order fix is cheap: minimize `|J^-1 (reprojected - observed)|^2`, which restores the
objective to the space the noise lives in. `undistortionJacobian()` already exists, extracted for
the redistortion solver, and this costs one 2x2 solve per camera per iteration. The exact
alternative — redistorting the reprojected point and comparing in raw pixels — would put a
`redistortPoint` multiroot solve inside the optimizer loop and is far too slow.

**Not yet implemented, and deliberately so:** the effect is invisible on the only data set with
ground truth. Validating it needs a synthetic test — the pool test's geometry and known lengths,
with a fisheye-magnitude distortion imposed on the clicks — before any change is shipped.

## Known-length data on distorted video, and an exact offline triangulation harness

`tools/pooltest/jacweight.py` recomputes every measurement from the raw screen clicks, using the
homographies, camera positions and distortion parameters stored in the document. It is validated
two ways: it reproduces the app's cached front-plane projections to 8e-13 over 1840 clicks, and
its reproduction of the shipped iterative refinement matches the stored 3D coordinates to
**0.0000 mm on every point**. Any A/B on triangulation can be run through it with confidence.

### More known-length reference data

Beyond the 2012 pool test, two Drift Model documents carry objects whose names give a true
length, and both are on far more distorted video than the pool test:

| document | lens | type | n | undistortion magnification (mean, max) |
|---|---|---|---|---|
| `2015-09-04-1 Clearwater` | 8 mm fisheye | `Length Tests` | 14 | 1.31, 2.92 |
| `2015-06-22-1 Clearwater` | 13 mm | `Frame Test` | 57 | 1.10, 1.72 |
| 2012 pool test | — | — | 1010 | 1.03, 1.10 |

`2015-09-04-1 Clearwater Backup pre-VidSync1.8` holds the same 14 measurements under an earlier
calibration whose right-camera plumbline fit is better (1.12 px against 2.31), which makes it a
recalibration robustness check rather than independent evidence.

**Units differ between projects.** The pool test works in metres, the Drift Model documents in
millimetres. This is easy to get wrong in a way that manufactures a result: the pool test's
stored `cameraMeanPLD` of 0.001 looks vanishingly small next to Clearwater's 3.9 but is 1.0 mm.

### Jacobian weighting of the refinement: real but too small to ship

Weighting each reprojection residual by the inverse undistortion Jacobian, so the objective sits
in the raw-pixel space where click noise is isotropic:

| data | magnification (max) | current | weighted | wins | sign test |
|---|---|---|---|---|---|
| 8 mm, 14 lengths | 2.92 | 2.971 | **2.829** | 10/14 | p = 0.18 |
| 8 mm, recalibrated | 3.04 | 3.426 | **3.217** | 12/14 | p = 0.013 |
| 13 mm, 57 lengths | 1.72 | 3.167 | 3.176 | 34/57 | p = 0.19 |
| pool test, 1010 | 1.10 | 0.990 | 0.989 | 516/1010 | p = 0.51 |

(mean absolute error, mm)

The dose-response is right: the effect appears only where the magnification is large, and the
pool test is a clean negative control confirming the harness does not manufacture differences.
But the only clear win is on one 14-measurement set, its apparent replicate is the same clicks,
and pooled over both field files the gain is 3.128 to 3.107 mm — 0.7%. **Not implemented.** It
would need either more known-length data on wide lenses or a synthetic test.

### The finding that matters more: the refinement's benefit is not universal

The same runs compared the shipped iterative refinement against plain closest-point-of-approach,
and the direction reverses between the pool test and the field rigs:

| data | n | linear CPA | iterative (shipped) | |
|---|---|---|---|---|
| pool test | 1010 | 1.458 | **0.990** | refinement wins, p = 0.001 |
| field files pooled | 71 | **2.638** | 3.128 | linear wins, p = 0.032 |

By rms the field gap is wider still, 4.035 against 5.062. This qualifies the earlier conclusion
recorded above that "the iterative refinement earns its place" — it earns it decisively on the
pool test and appears to lose on both field documents that can be checked. The refinement is on
by default.

Camera-centre quality relative to *working distance* does not order the results: the 13 mm file
has a better centre fit than the 8 mm one (0.23% against 1.52% of median range) and shows the
same reversal. Relative to *frame separation* it does, which is the more defensible
normalization anyway, since a sightline's angular error is a node position error divided by the
separation:

| document | cameraMeanPLD | frame separation | ratio |
|---|---|---|---|
| pool test | 0.72 mm | 439 mm | **0.16%** |
| 2015-06-22-1 Clearwater | 2.32 mm | 200 mm | 1.16% |
| 2015-09-04-1 Clearwater | 4.68 mm | 196 mm | 2.39% |

The refinement is anchored on a single fitted camera centre, so it should help when that anchor
is a low-variance constraint and hurt when it is biased. A seven-to-fifteen-fold difference in
how well the pinhole model holds, relative to the geometry defining the rays, is a plausible
mechanism. **This is post hoc, fitted to two files on one side and one on the other, and should
not be acted on until tested.** The honest next step is more known-length data from field rigs
with the wide separation, or a synthetic experiment with a controlled non-central camera.

## Two-distance diagnostic: no detectable subject-distance dependence, bounded under ~4%

`2015-09-04-1 Clearwater` was temporarily given two left-camera plumbline sets four seconds
apart, with the board 1.35x closer in the earlier one (cell size 106.3 against 78.9 px, so 1/Z
differs by 25.8%). This is Step 1 of the refraction protocol: if the underwater system is
non-central, its effective distortion carries a term in 1/Z and a fit at one range cannot
straighten lines at the other.

### The test needs no fitting at all

For a central camera carrying **any** fixed distortion map, the curvature of the image of a
straight world line is a function of image position and image direction alone, independent of the
line's distance. Undistortion sends the image of a straight line to a straight line; a straight
line is fixed by one point and one direction; so two world lines whose images agree in position
and direction at some pixel have identical undistorted lines and hence identical distorted curves.
Depth cannot enter.

So distance dependence is directly observable in the raw clicks: measure signed curvature at every
interior plumbline point, bin by image radius and orientation, and compare the two sets. No
fitting, no model, no gauge freedom. `tools/pooltest/curvature.py`. The null distribution comes
from the same data by splitting one set in half — same range, so any disagreement there is corner
noise plus board pose.

This matters because the direct approach failed. A pure-Python 13-parameter Nelder-Mead refit of
each set separately did not converge reliably (the near set's "own" residual came out *worse* than
the other set's fit on the same data, which is impossible at an optimum), and no numpy or scipy is
available. Curvature sidesteps the optimizer entirely.

### Result: null, robust to window size

Pooled curvature difference, in units of 1e-6 per pixel, against typical edge curvature of
590-600 in the same units:

| local window | chord span | near vs far | same-range null |
|---|---|---|---|
| 3 points | 161-213 px | -3.58 +/- 5.24 (z = -0.68) | -2.24 +/- 8.39 (z = -0.27) |
| 5 points | 330-454 px | -2.10 +/- 3.00 (z = -0.70) | +1.95 +/- 4.81 (z = 0.41) |
| 7 points | 509-707 px | +0.56 +/- 2.92 (z = 0.19) | +3.69 +/- 3.47 (z = 1.06) |

Never significant, never larger than the same-range null, and the sign is not even consistent
across window sizes. At the longest baseline the null exceeds the signal.

**Bound.** The tightest estimate is +0.56 +/- 2.92, so a 2-sigma limit of 6.4 against curvature of
about 595 — **1.1% of total distortion curvature for a 25.8% change in 1/Z**. Dividing by 0.258,
the 1/Z-dependent share of this camera's distortion is **under about 4%**, consistent with zero.
This agrees independently with the 67-document cross-prediction result above, where transferring a
calibration across a 2.6-fold range change cost under 0.05 px.

**The limitation is leverage, not precision.** Two frames four seconds apart span only 1.35x in
range, so the bound on the absolute refraction magnitude is inflated 3.9-fold. Repeating with the
board at the two extremes of the working range — say 0.3 m and 3 m — would give ten times the
leverage and turn a 4% bound into a 0.4% one. That is the single cheapest way to settle this
properly, and it needs one clip, not a field season.

### Side observation: the stored parameters match neither set

Evaluated on the near set alone the stored left-camera parameters give 1.809 px, on the far set
1.555, and on both together 1.649, against a stored `distortionRemainingPerPoint` of 1.8035. They
are at neither set's optimum — both of the (imperfect) independent refits reached 0.83-1.03 — so
they appear to be from an earlier point set. Anything read from this file's stored left-camera
parameters while the two-set arrangement is in place should be treated as stale.

### Shape, for the flat-versus-dome question

On `2016-08-13-2 Chena`, the systematic residual field is radial-dominant but with a real
tangential component: at r = 700-1200 the radial rms is 3.78 px against 1.97 tangential. That is
what a *nearly* centred dome would give — mostly radial, with a modest asymmetric part — rather
than either a clean flat-port radial pattern or a badly decentred dome's strongly conic one.
