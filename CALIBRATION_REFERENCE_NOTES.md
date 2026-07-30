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

### Revisited with VidSync's own fits: a real but unattributed 0.32 px inconsistency

Three exports were produced holding VidSync's own solver output for the near set, the far set and
both combined (`tools/pooltest/twodistance2.py`). Two of the three are the same fit: the
"NearDistortionSetOnly" and "FarDistortionSetOnly" files differ only in the eleventh significant
figure and report a bit-identical `distortionRemainingPerPoint` of 0.917252988615399, which only
happens with identical input. Evaluating each exported fit against each candidate training set
identifies them unambiguously:

| export | app-reported residual | near set | far set | both sets |
|---|---|---|---|---|
| "near-only" | 0.917253 | 1.124585 | **0.917253** | 0.995638 |
| "far-only" | 0.917253 | 1.124585 | **0.917253** | 0.995638 |
| "both" | 0.999429 | 1.077459 | 0.953927 | **0.999429** |

So the near-only fit does not exist yet; the export labelled that way carries the far-set fit.

**What can still be concluded.** The near-only optimum must be at or below the 1.077459 the
combined fit already achieves on the near set, because the near-only fit minimizes exactly that
quantity. The far-set fit gives 1.124585 there. So the penalty for transferring the far fit to the
near lines is **at least sqrt(1.124585^2 - 1.077459^2) = 0.32 px**, against a corner-noise floor of
0.200 px on that set. That is above noise, and coverage is not the explanation this time: both sets
reach r98 = 994 and 989 px, because field practice is to fill the frame at any distance.

The combined fit also shows the two sets pulling against each other — including the near set
degrades the far set from 0.9173 to 0.9539 — which is what one map failing to serve both ranges
looks like. But adding 351 points to 640 shifts a 13-parameter optimum anyway, so this is not by
itself evidence of a systematic difference.

**This reconciles with the curvature null rather than contradicting it.** A 0.32 px straightness
excess over lines spanning about 1000 px implies a curvature difference of roughly
8 x 0.32 / 1000^2 = 2.6 in the 1e-6/px units used above. The curvature test's 2-sigma sensitivity
was 3 to 6 in those units. So both measurements agree: there is something at the 0.3 px level, and
the curvature test was just short of resolving it.

**What it is remains open.** The 0.32 px could be range dependence, or board pose, or board
non-flatness presenting differently, or detection differences between two frames. Nothing here
separates them.

### The protocol correction that matters

Testing at 0.3 m and 3 m is not possible: with these wide lenses a frame-filling board at 3 m
would have to be enormous, and frame-filling coverage is more important than range spread. Field
practice was always to fill the frame. **This has a consequence for the harmonic-mean
recommendation: the calibration distance is not a free parameter.** It is fixed by the board size
and the lens, given the coverage constraint. The actionable version is therefore about board
sizing, not board placement — a board sized so that frame-filling occurs near the harmonic mean of
the working range — and that only matters if the effect proves real.

**The right control is free and was not run.** To separate range from frame-to-frame variability,
take two plumbline sets at the *same* board distance but different times and poses, from the same
clip. If those disagree by about 0.32 px as well, the whole effect is frame-to-frame variability
and range dependence is bounded below it. If they agree closely, the near/far disagreement is
range. This costs one more detection in an already-open document and is the single measurement that
would resolve the question.

### The completed 2x2, and what it costs in millimetres

A corrected near-set export completes the cross-fit. Each exported fit was identified by matching
its app-reported residual against straightness computed on each candidate training set, so the
labels are verified rather than trusted:

| | near fit | far fit |
|---|---|---|
| **near lines** | **1.0303** | 1.1246 |
| **far lines** | 1.0349 | **0.9173** |

Transfer penalty **0.451 px** onto the near lines (corner noise 0.200) and **0.479 px** onto the
far lines (corner noise 0.150). The symmetry matters: a one-sided penalty would point at coverage
or extrapolation, and a symmetric one is what a genuine model-versus-data mismatch looks like.
Coverage is independently excluded here, both sets reaching r98 near 990 px because field practice
fills the frame at every distance.

**In millimetres.** `tools/pooltest/distcal.py` rebuilds the entire downstream calibration under
each distortion model -- undistorting the frame's 20 front and 27 back node clicks, refitting both
homographies by normalized DLT, re-estimating the camera position from the back-node sightlines --
and re-triangulates the 14 known lengths. Refraction correction of the back-plane nodes is not
replicated, which is harmless because the quantity of interest is a difference between two models
and a common approximation cancels; as a fidelity check, the document's own stored distortion run
through this rebuild gives 2.879 mm mean absolute error against the exact harness's 2.971 mm.

Paired per-measurement difference between the near-set and far-set calibrations: **mean -0.244 mm,
sd 0.934 mm, largest 2.867 mm**, against a measurement error of about 4.77 mm. So the choice of
calibration distance is worth roughly a fifth of this rig's error budget -- real, and not
negligible, but not dominant either.

**The attribution caveat is unchanged and is the whole ballgame.** These numbers establish that
*which plumbline set you fit to* matters. They do not establish that *distance* is why. Two frames
four seconds apart differ in board pose, in board flatness presentation, and in detection noise as
well as in range. The same-distance control -- two sets at the same board distance, different poses
-- remains the one measurement that separates them, and it has not been run.

**A caution that emerged from this.** Both new single-timecode fits produce *worse* measurements
than the document's older stored parameters, 4.26 and 4.77 mm against 2.88, despite far better
plumbline residuals (1.03 and 0.92 against 1.55 to 1.81). The likely mechanism is that each new fit
uses one timecode's lines only, 33 or 47 of them, so it is less constrained outside their image
footprint, and the length targets sit at 209 to 609 mm while the frame planes are at 0 and 196 mm,
so sightlines are extrapolated well beyond the calibrated volume. With n = 14 this could be noise,
but it is the third time in this project that a better calibration residual has accompanied worse
measurements. Fitting distortion to all available plumbline sets at once looks safer than fitting
to any single one.

### Radial-leverage confound tested and refuted; the penalty's shape now points at refraction

A symmetric transfer penalty proves only that the model is **misspecified**. If Brown-Conrady could
represent the true map exactly, both fits would recover the same parameters up to gauge and neither
would lose on the other's data. Given misspecification, two differently-weighted samples settle at
different compromises and each looks worse under the other's weighting -- no range dependence
required. Since the far set has more lines (47 against 33) and a fisheye compresses the extra board
area toward the frame edge, differential radial leverage was the leading alternative explanation.

**It is not what happened.** The two sets' radial distributions are proportionally almost identical:

| radius band | near, share | far, share | ratio |
|---|---|---|---|
| 0-300 | 6.8% | 5.9% | 0.87 |
| 300-500 | 14.2% | 14.1% | 0.99 |
| 500-700 | 22.8% | 24.1% | 1.06 |
| 700-900 | 35.0% | 35.0% | 1.00 |
| 900-1100 | 21.1% | 20.9% | 0.99 |

The far set has uniformly more points (640 against 351), not points redistributed outward. Because
the objective is an unweighted sum over points, matched proportions mean matched effective radial
weighting, so differential leverage cannot be the mechanism.

**And the penalty has the right shape for refraction.** Broken down by radius, the excess of the
foreign fit over the own fit, in both directions:

| radius band | near lines | far lines |
|---|---|---|
| 0-300 | 0.347 | 0.000 |
| 300-500 | 0.578 | 0.139 |
| 500-700 | 0.000 | 0.212 |
| 700-900 | 0.334 | 0.576 |
| 900-1100 | **0.728** | **0.692** |

Noisy in the inner bands, but the two outermost bands show a large penalty in *both* directions and
the trend is upward. A refractive term scales as sin(theta) and is radial, so it should grow toward
the edge and be symmetric -- which is what this is.

Also confirmed from the same table: own-fit residuals grow from 0.42-0.44 px at the centre to
0.89-1.13 px at the edge, against a corner-noise floor of 0.15-0.20 px. The edge residual is
therefore model misspecification, not noise, and because the objective is an unweighted sum of
squares **the fit is dominated by the frame edge**, where it fits worst. That is a design
consequence worth knowing, though inverse-variance weighting would amount to down-weighting the
model's own failure and is not obviously an improvement.

### The decisive control, and it needs no new footage

With coverage and radial sampling both excluded, the surviving alternatives are board pose and board
non-flatness presenting differently at the two distances. The control that removes both:

**Split one set's lines into two disjoint halves, fit each in VidSync, and cross-evaluate.** The far
set's 47 lines split 23/24 gives roughly 320 points per half, closely matching the near set's 351.
Same range, same frame, same pose, same flatness, same lighting, same detection pass -- only the
line subset differs, and it differs *less* than near-versus-far does. This measures the null
distribution of the transfer penalty directly.

- Penalty near 0.45 px -> the effect is subset-to-subset disagreement in a misspecified model, and
  distance dependence is bounded below it. The recommendation becomes "fit to all lines available."
- Penalty much smaller, say under 0.15 px -> the near-versus-far 0.45 px is attributable to
  distance, and this rig has a measured refraction budget of about 0.9 mm rms in its working range.

Two extra solves in an already-open document, and it settles a question three rounds of analysis
have not.

## Residual structure: what is solid, and a correction

### Correction: the plumbline objective is NOT gauge-invariant

Earlier in this work it was asserted that straightness is invariant under any homography applied
after undistortion, and therefore that the plumbline fit's gauge freedom is free. **The first half
is wrong and needs retracting.** A homography maps straight lines to straight lines, so it preserves
the *property* of exact straightness. It does not preserve the *residual value*, because the
plumbline points are not straight -- they carry the residual -- and a homography rescales those
deviations along with everything else. Shrinking the undistorted image by a factor lambda scales
every residual by lambda and the objective by lambda squared.

So the objective has an unbounded downhill direction that improves nothing. The only thing
preventing a runaway is that Brown-Conrady pins the scale through the leading 1 in its radial
series, and with seven radial coefficients the series can *approximately* imitate a constant over
the covered annulus. That is precisely the mechanism behind the unconstrained fits that reached
0.0037 px per point while being physically degenerate, and it is why the acceptance gate is
load-bearing rather than cosmetic.

What survives from the earlier argument is the part that rests on the fundamental theorem of
projective geometry: if a map straightens every line *exactly*, it differs from the truth by a
homography, and the two-plane homographies absorb that downstream. The geometry is still fine. The
claim that the objective cannot see the gauge is not.

### Solid: radius and line length both matter, independently

Far set, its own fit, residual binned two ways at once (rms px, n in parentheses):

| radius | short lines | medium | long lines |
|---|---|---|---|
| 0-400 | 0.447 (38) | - | 0.360 (38) |
| 400-600 | 0.582 (31) | 1.076 (30) | 0.626 (61) |
| 600-800 | 0.814 (10) | 1.214 (97) | 0.679 (82) |
| 800-1200 | 0.566 (47) | 1.036 (71) | 1.149 (135) |

Reading down the long-line column holds length roughly fixed: residual grows 0.360 to 1.149, a
factor of 3.2 with radius. Reading across the bottom row holds radius fixed: residual grows 0.566 to
1.149 with length. **Both effects are real and neither is an artifact of the other.** So the visual
impression that outer lines fit worse is partly a length illusion, as suspected -- a longer line
shows the same curvature as a bigger sagitta -- but a genuine radial effect survives at matched
length. The middle column runs anomalously high and the small cells are noisy, so this table
supports the direction of both effects but not precise magnitudes.

### Solid: the existing 13 parameters are exhausted

Correlation of the residual with each parameter's displacement direction, in VidSync's own
unnormalized metric: 0.0001 to 0.0683, largest for x0. The solve is genuinely at its optimum and no
retuning of the current parameter set can help. Whatever is left needs different basis functions,
not better optimization.

### NOT established: what a richer model would buy

`tools/pooltest/expressiveness.py` attempts a score test -- at a converged optimum, the reduction
available from a candidate basis is the residual variance it explains once the existing directions
are controlled for, which is linear algebra rather than nonlinear refitting. **It is not trustworthy
yet and its numbers should not be quoted.** Two genuine bugs were found and fixed:

1. The parameter-direction columns span some forty-five orders of magnitude, because the k7
   derivative carries s^7 and s reaches 1e6 at the frame corner. Orthogonalizing a small candidate
   against a huge one destroyed every significant digit.
2. Affine displacement fields are pure gauge but do *not* produce zero columns, for the reason in
   the correction above: they rescale the residual. The isotropic-scale column comes out exactly
   parallel to the residual vector and "explains" 100% of it by shrinking the image.

A third symptom remains unexplained: adding 42 independent de-gauged directions to the 13 model
directions changes the residual by nothing to ten decimal places, and the answer is identical
whichever order the columns are supplied. Orthogonal projection onto a larger subspace cannot do
that. Until that is understood the tool proves nothing.

**The clean path instead.** Rather than a score test with this much gauge machinery, fit candidate
models directly and score them on **held-out lines**. Held-out straightness on lines the fit never
saw is unambiguous, needs no gauge bookkeeping, and cannot be won by shrinking the image, because
the scale is pinned by the model's own leading term and the held-out lines are measured in the same
units. That requires a reliable 13-plus-parameter optimizer, which pure Python could not deliver
here; a C implementation with multi-start Nelder-Mead is the enabling step, and `tools/pooltest/`
already contains C precedent in `fisheye.c` and `order.c`.

## Only four of the seven radial terms are load-bearing, and dropping the rest fixes the conditioning

`tools/pooltest/loadbearing.py`. Measured on the left camera's far plumbline set (47 lines, 640
points, 8 mm fisheye, the most distorted case available), against its own VidSync fit. Neither
measurement needs a nonlinear solver.

**Spectrum.** The Jacobian of the straightness residual with respect to the 13 parameters, in the
solver's own scaled units, has a condition number of **2.6e8**. Only about five eigen-directions move
the residual by more than the corner noise per unit step -- the image centre (two), one direction
dominated by k1, one by k7, and one by p4. The remaining eight, including k2 through k6 and p1 to p3
individually, are far below noise. The radial series runs in powers of s = r^2, so s through s^7 form
a Vandermonde-like basis over the covered radius range and are nearly collinear as functions on the
data. (The exact count depends on the arbitrary `SCALE_FACTOR_*` normalization, so lean on the
penalties below, which do not.)

**Cost of dropping terms**, linearized about the converged fit, each dropped parameter forced to zero
and the survivors re-optimized. The baseline is the linearized re-optimum of all 13, 0.8749 px, which
is the like-for-like comparison; corner noise on this set is 0.150 px.

| model | params | rms | excess | condition number |
|---|---|---|---|---|
| all 13 | 13 | 0.8749 | — | 2.64e8 |
| k1-k6 + p1-p4 | 12 | 0.8766 | 0.055 | 3.74e7 |
| k1-k5 + p1-p4 | 11 | 0.8779 | 0.072 | 3.33e6 |
| **k1-k4 + p1-p4** | **10** | **0.8781** | **0.075** | **2.11e5** |
| k1-k3 + p1-p4 | 9 | 0.9406 | 0.346 | 1.46e5 |
| k1-k4 + p1,p2 | 8 | 0.9205 | 0.286 | 2.09e5 |
| k1-k4 + p1,p2,p4 | 9 | 0.8816 | 0.109 | 2.10e5 |
| k1-k7, no tangential | 9 | 1.4221 | 1.121 | — |

**Dropping k5, k6 and k7 costs 0.075 px, half the corner noise, and improves the conditioning
1250-fold.** Dropping k4 as well costs 0.346 px, above noise, so four radial terms is the sweet spot.
All four tangential terms earn their place: removing the tangential block entirely costs 1.12 px, and
even p3 and p4 individually contribute more than a tenth of a pixel.

So the minimal well-supported model here is **x0, y0, k1-k4, p1-p4 -- ten parameters**.

### Why this matters more than the parameter count

The obstacle to fitting in pure Python was never dimension; 13 against 10 is marginal for
Nelder-Mead. It was **conditioning**. A simplex method degrades badly at a condition number of 2.6e8
because the simplex collapses along the flat directions, which is exactly the failure seen earlier
when a pure-Python refit produced an "own fit" worse than a foreign fit on the same data. At 2.1e5
the problem is ordinary. A 640-point cost evaluation is around a millisecond, so tens of thousands of
evaluations are seconds, not hours: **the reduced model should be fittable in plain Python, with no C
and no scipy** (neither numpy nor scipy is installed on any interpreter here, though pip is
available).

### Why it may matter for the shipped software

The high-order radial terms are also the mechanism behind the degenerate fits. A runaway needs them
to imitate a constant scale factor over the covered annulus, which is how an unconstrained fit
reached 0.0037 px per point, and it is why the acceptance gate has to exist. Removing k5 to k7 would
cost less than the noise, cut the condition number by three orders of magnitude, make the solve
faster and more reproducible, and probably remove the failure mode the gate currently catches.

**Not yet a recommendation.** Two things must come first, and the project's own history says so
plainly, since a better calibration residual has three times now accompanied worse measurements.
One: run this spectrum across the 67-document corpus, since this is one camera on the most extreme
lens, and the answer may differ at 17 mm. Two: fit the ten-parameter model and judge it on the known
lengths through `distcal.py`, not on residuals. The Python fitter is the prerequisite for both, and
is now within reach.

## A working fitter, and held-out model comparison

`tools/pooltest/fitter.py` fits the plumbline objective with any subset of the 13 parameters active,
and scores candidates on **held-out lines**. It needs numpy and scipy from `~/.venvs/vidsync`; see
the README in that folder. Whole lines are held out, never points within a line, because a line's
residual is defined relative to its own fit.

Two implementation notes that mattered. The per-line loop was replaced by `reduceat`/`repeat` so all
47 lines are reduced at once, which took a full 13-parameter fit from 213 s to about 5 s and made
cross-validation possible at all. And a trust-region least-squares pass on the residual vector,
followed by Nelder-Mead as an independent check, converges from 7 of 8 random restarts to the same
optimum.

### The fitter beats VidSync's own solver, and that is a problem before it is a benefit

Fitting all 13 parameters to the far set reaches **0.8208 px against VidSync's 0.9173** -- but that
solution **fails the acceptance gate** on scale ratio (4.23 against the 4.0 limit). The extra
reduction is bought by shrinking the undistorted image, exactly the degeneracy documented above.
Every flexible model behaved this way, so comparing models at unconstrained optima compares
solutions the application would refuse to store. The fitter therefore appends penalty residuals that
are zero on the feasible side, keeping the search inside the gate. Gated, the 13-parameter fit
reaches 0.8438 px -- still 8% better than the shipped solver, within the feasible region.

### Held-out comparison, gate enforced throughout

Left camera, far set, 47 lines, 640 points, 6-fold cross-validation over lines:

| model | params | in-sample | **held-out** | condition |
|---|---|---|---|---|
| full 13 | 13 | **0.8438** | 0.9984 | 3.18e8 |
| k1-k6 + p1-p4 | 12 | 0.8484 | 0.9947 | 4.86e7 |
| k1-k5 + p1-p4 | 11 | 0.8550 | 1.0360 | 4.41e6 |
| **k1-k4 + p1-p4** | **10** | 0.8556 | **0.9806** | **3.38e5** |
| k1-k3 + p1-p4 | 9 | 0.9705 | 1.1610 | 1.21e5 |
| k1-k4 + p1,p2 | 8 | 0.9278 | 1.1177 | 1.98e5 |
| k1-k4 only | 6 | 1.0902 | 1.2508 | 1.99e5 |
| k1-k7 only | 9 | 1.0683 | 1.2705 | 2.32e8 |

**The ten-parameter model generalizes best.** It beats the full 13 by 1.8% on held-out lines while
using three fewer parameters and improving the conditioning 940-fold. The in-sample column runs the
other way -- the full model wins there -- which is textbook overfitting and is exactly why held-out
scoring was needed. This corroborates the linearized identifiability result above by an independent
route: that analysis said dropping k5-k7 costs 0.075 px, half the noise floor, and this one says it
costs nothing at all out of sample.

Dropping further is clearly wrong. k1-k3 loses 18% held-out, and the tangential terms are load-bearing
in generalization too: p3 and p4 are worth 14% and the whole tangential block 28%.

### What is not yet established

The 1.8% held-out margin between 13 and 10 parameters is small, from one camera on one plumbline set
with 47 lines, and it is not obviously outside cross-validation noise on its own. It is believable
mainly because a completely different method agreed. Two things remain before changing the shipped
model, and this project's history insists on both, a better residual having three times accompanied
worse measurements:

1. Run the comparison across the 67-document corpus. This is the 8 mm fisheye, the most extreme lens;
   at 17 mm distortion is 4.5 times smaller and the answer may differ.
2. Judge the ten-parameter model on the **known lengths** through `distcal.py`, not on residuals.

There is also a second, independent candidate improvement: the shipped Nelder-Mead leaves about 8%
of the achievable residual on the table even within the gate, because it stalls on a problem
conditioned at 3e8. Reducing to ten parameters fixes the conditioning, so the two changes reinforce
each other. Both still need the known-length test.

## Known-length verdict: the ten-parameter model is measurement-neutral, not a win

`tools/pooltest/modeltest.py` refits both cameras' distortion from their own plumblines under each
candidate model, gate enforced, rebuilds the whole downstream calibration on top (both homographies
from the frame node clicks, camera position from the back-node sightlines) and re-triangulates the 14
`Length Tests`.

| model | plumbline px, L / R | mean abs err | rms | bias | sd |
|---|---|---|---|---|---|
| document as-is | (stored) | **2.879** | 4.027 | +0.876 | 4.079 |
| full 13 | 0.901 / 2.394 | 4.238 | 6.740 | +1.262 | 6.871 |
| k1-k5 + p1-p4 | 0.912 / 2.588 | 4.147 | 6.633 | +1.466 | 6.713 |
| k1-k4 + p1-p4 | 0.921 / 2.572 | 4.156 | 6.592 | +1.460 | 6.671 |
| k1-k3 + p1-p4 | 1.039 / 2.595 | 4.090 | 6.375 | +1.365 | 6.463 |

**Reducing the radial order is worth about 2% here, which n = 14 cannot resolve.** k1-k4 is closer to
truth than the full model on 8 of 14 measurements. So the ten-parameter model does not earn a change
on measurement evidence, and it does not hurt either; its case rests on the 940-fold conditioning
improvement and the held-out plumbline result, both of which are real but neither of which is
accuracy.

### The apparent "worse than the document" result is a data confound, not an objective failure

Every refit measures worse than the parameters already in the document, 4.1-4.2 mm against 2.879. It
is tempting to read that as the plumbline objective punishing thorough optimization -- and a
plausible mechanism was available, that VidSync's under-converged Nelder-Mead stops short of the
degenerate boundary and so acts as accidental regularization. **That reading is wrong, and testing it
was worth the effort.** `tools/pooltest/convtest.py` isolates convergence quality by fitting the
*same* 47-line far set two ways and holding the right camera fixed:

| left-camera distortion | plumbline | mean abs err | rms |
|---|---|---|---|
| VidSync's own solve | 0.9173 px | 4.768 mm | 7.627 |
| thorough refit, gated | 0.8438 px | **4.303 mm** | 6.896 |

On identical data the better-converged fit measures **10% better**. Optimizing the objective harder
helps. So the document's advantage comes from its plumbline *data*, not from how it was fitted: those
parameters were fitted to an older detection, whereas every refit here used the current two-set
arrangement. That also fits the earlier finding that a combined near-plus-far fit degrades each set
relative to fitting one alone -- mixing two board distances into one solve appears to cost more than
it gains.

### Where this leaves a possible change

Two candidate improvements survive, and neither is ready:

* **Reduce to ten parameters.** Measurement-neutral at n = 14, better on held-out lines, 940-fold
  better conditioned. Needs the corpus and the pool test's 1010 measurements before shipping.
* **Optimize the objective properly.** Worth 10% on the one clean A/B available, also n = 14. Cheap
  to do -- a trust-region pass on the residual vector, which is the natural method for a sum of
  squares -- but it moves the solution toward the degenerate boundary, so it must ship together with
  the gate as a hard constraint rather than a post-hoc check. Every gated fit here landed exactly on
  the scale-ratio limit of 3.80, meaning the constraint and not the data is setting the answer, which
  is its own argument that the objective needs a better-specified scale rather than a better solver.

The high-power test not yet run is the 2012 pool test: 1010 known lengths rather than 14. Its camera
has mild distortion, so it is a weak test of radial order specifically, but it is by far the best
test of whether either change does harm.

## Pinning the scale: the diagnosis was wrong, and the real answer is simpler

The observation that started this was sound -- every gated fit landed exactly on the acceptance
gate's scale-ratio limit, so the constraint rather than the data was setting the answer. The
diagnosis attached to it was not. Three iterations were needed to get there, and the dead ends are
worth recording because each is a plausible thing to try again.

**Attempt 1, adding a constraint R(s_ref) = 1: wrong, and it made the fit five times worse.** The
shipped form r*(1 + k1 s + ...) *already* fixes the scale gauge, because it forces u'(0) = 1. Adding
a second condition at r_ref over-constrains the radial map rather than re-gauging it: the true map's
scale representative with unit slope at the origin does not also fix r_ref, so the polynomial is
forced to wiggle. Residual went from 0.90 to 4.37 px.

**Attempt 2, moving the fixed point instead of adding one.** Reparameterizing as
`u(r) = r*(1 + sum k_i (s^i - s_ref^i))` keeps seven degrees of freedom, makes u(r_ref) = r_ref, and
frees the slope at the origin. This is a genuine re-gauging, and it does block a uniform rescale over
an annulus containing r_ref. Residual fell from 0.8438 to 0.6161 px -- which looked like progress and
was not. Checked directly: the best uniform scale relating the two fitted maps is lambda = 0.7323,
and the pinned map departs from lambda times the shipped map by 13.8 px out of a 2049 px extent, or
0.67%. **The two fits are the same geometry in different gauges**, and the entire residual change is
that rescale, predicted 1/B(r_ref) = 0.7318 against 0.7301 observed. Relocating the gauge
representative changes the reported number without changing anything real.

**Attempt 3, making the objective scale-invariant -- the principled fix, which turns out not to
matter here.** Dividing the residual by the map's own spread (rms extent of the undistorted cloud
about its centroid, relative to the raw) gives an objective no rescaling can improve.

| objective | normalized rms | spread | scale ratio | gate |
|---|---|---|---|---|
| plain, penalty gate | 0.5495 | 1.5356 | 3.80 | PASS |
| scale-invariant, penalty gate | 0.5480 | 1.5440 | 3.80 | PASS |
| scale-invariant, no penalty | 0.5352 | 1.5405 | **4.18** | REJECT |

**The scale degeneracy is not being exploited.** Making the objective scale-invariant changes the
answer by 0.3%. And the fitted map's spread is 1.54, an *expansion*: undistorting barrel distortion
necessarily magnifies, and with the leading 1 holding the centre at unit magnification the map cannot
shrink overall. The runaway is available in principle and is not what is happening in practice.

### What is actually binding: the gate's scale-ratio bound is too tight for the 8 mm fisheye

Removing the penalty, the fit wants a centre-to-edge magnification ratio of **4.18**, against
`kMaxAcceptableScaleRatio = 4.0`. That is not degeneracy -- undistorting a fisheye to rectilinear
genuinely stretches the corners several-fold, and the minimum Jacobian determinant stays comfortably
positive (+1.00) throughout, so the map remains a clean bijection. The gate is clipping a legitimate
solution.

The min-determinant test is the principled half of the gate: it enforces bijectivity, which is the
hypothesis the projective-geometry argument needs. The scale-ratio band was an ad hoc sanity check,
and it is now demonstrably binding on the widest lens in the corpus. Loosening it -- to 6, say, or
making it depend on fitted distortion magnitude -- is justified.

**Practical scope is narrow.** VidSync's current under-converged Nelder-Mead lands at ratios of
3.1 to 3.7 on the 8 mm files and passes comfortably. The bound only bites once the solver is
improved, so this is a prerequisite for that change rather than an independent fix.

### Net effect on the shipping question

The "objective needs a better-specified scale" hypothesis is **withdrawn**. What survives from this
line is one concrete, small change -- loosen the scale-ratio bound before improving the solver -- and
a reusable capability in `fitter.py`: an optional scale-invariant objective and an optional radial
gauge, both off by default, either of which can be re-tested on other lenses where the degeneracy may
actually bite.

## RETRACTION 2026-07-28: the offline gate measured the wrong quantity, and two recurring bugs

Two bugs are recorded here first because both are the kind that silently manufacture a result, and
both have already done so once.

### Bug 1: the offline gate was not the production gate

`fitter.py`'s `gate()` computed `max_g sqrt|det J(g)| / min_g sqrt|det J(g)|` -- the *spread of local
area scale* across the domain -- and compared it against production's 4.0 bound. Production
(`reasonToRejectSolvedDistortion:overPlumblineBox:warning:`, VSCalibration.mm:2243) brackets an
entirely different quantity:

```
R_scale = sum_g ||U(g) - c||  /  sum_g ||g - c||
```

the **mean radial magnification about the distortion centre**, on a 25x25 grid over the plumbline
bounding box. The two are not monotonically related. On the 8 mm fisheye's M1 fit the area spread is
4.80 while the true production ratio is 1.43.

**Every claim in this document and in the analysis scripts that a fit "fails the gate", or that the
4.0 bound binds, is retracted.** Specifically retracted:

* "the 13-parameter fit **fails the acceptance gate** on scale ratio (4.23 against the 4.0 limit)"
  (section "The fitter beats VidSync's own solver"). The quantity 4.23 is the area spread. That fit's
  production ratio is inside the bracket.
* the whole section "**What is actually binding: the gate's scale-ratio bound is too tight for the
  8 mm fisheye**", including the 4.18-versus-4.0 comparison, the recommendation to loosen the bound
  to 6, and the claim that the bound is "demonstrably binding on the widest lens in the corpus". The
  bound is not binding anywhere in this corpus.
* the table rows labelled "scale ratio" reporting 3.80 / 4.18 with PASS/REJECT verdicts, and the
  associated claim that "the constraint and not the data is setting the answer".
* the claim that penalty-constrained fits in `modeltest.py` / `convtest.py` represented the
  production constraint. They constrained the area spread, so those "gated" fits are not the fits
  production would accept or refuse.
* the round-9 claim that the free-axis Tokina model was rejected by the production gate. Its
  production ratio is 1.334 and it passes; that model's rejection rests only on its held-out
  straightness loss and bootstrap instability.
* the round-9 known-length claim that "the gate is the blocking problem" and that enforcing it
  destroys the fisheye fit. That experiment capped the area spread, a quantity production does not
  constrain, so it says nothing about the gate.

Measured production ratios for all 16 suite fits: 1.0216 to 1.4303, minimum determinants 0.9984 to
1.0010. Nothing is close to either bound. **The production bracket of 0.25 to 4.0 stands unmodified
and is not implicated in any observed problem.**

`fitter.py` now implements `radial_scale_ratio()` (production), `area_scale_spread()` (diagnostic,
explicitly not a rejection criterion), and `gate_report()` reproducing all four production checks
including the whole-frame determinant as a warning only. `test_gate.py` checks it against an
independent transcription of the Objective-C++ on all 16 real calibrations plus synthetic collapse and
expansion cases; 30/30 pass, agreement better than 1e-10 relative.

### Bug 2: seed contamination across nested models

In `fit(g, free, seed)`, parameters outside `free` retain whatever the seed gave them. Seeding a
ten-parameter model from a thirteen-parameter solution therefore leaves k5..k7 and p3,p4 at nonzero
values, so the "ten-parameter" fit is not ten parameters and the nesting is broken. This produced a
spurious eta win on the pool test (-0.0465 mm at t = -7.72) that vanished once seeds were zeroed on
every held parameter. **Any script that seeds one model from another must zero the complement of the
free set.** A related trap: multistart that seeds only from previous-round solutions can miss the
true basin -- on the pool test that cost 0.035 px of plumbline RMS and flipped the sign of the eta
effect.

### Consequence for the known-length work

The round-9 known-length numbers were computed with a calibration rebuild that omitted refraction
correction of the back calibration nodes, omitted production's 4-iteration back-surface fixed-point
loop, and used an h33 = 1 normal-equation homography where production uses the smallest right
singular vector of the 9-parameter homogeneous system. That rebuild produced a pool-test baseline of
0.856 mm where production gives 0.990 mm. **Those model rankings are provisional and are not to be
quoted.** Refraction correction is enabled in all six cameras of all three known-length documents,
so the omission was material.

Triangulation parity has since been established exactly (`parity.py`): taking the stored calibration
as given, a port of VSPoint.m's linear-CPA seed plus reprojection refinement reproduces the stored 3D
coordinates to a median of 6.4e-4 mm on the pool test and 1.2e-5 mm on the Drift documents, and
reproduces the stored known-length errors to four decimals -- 0.9900, 3.1669 and 2.9712 mm, matching
both the app and the exact `jacweight.py` harness. **The 0.856 vs 0.990 discrepancy is therefore
entirely in the calibration rebuild, not in triangulation.** Rebuilding the calibration with
production fidelity (SVD homography, refraction-corrected back nodes, 4-iteration loop) is the
remaining prerequisite before any model recommendation.

### Bug 3: the front and back calibration-node relations are the opposite of their names

`ZVSSCREENPOINT.ZCALIBRATION` holds the **back** surface nodes and `ZCALIBRATION1` holds the **front**
surface nodes, not the reverse. Verified on all six cameras of the three known-length documents by
asking which stored homography reproduces which node set: on the pool test, ZCALIBRATION nodes go
through the stored screen-to-quadrat-**back** matrix at 0.0009 mm rms and through screen-to-front at
0.128 mm, while ZCALIBRATION1 nodes go through screen-to-**front** at 0.0006 mm and screen-to-back at
0.253 mm. On the 8 mm fisheye the wrong pairing is off by 200 to 500 mm.

`distcal.py`'s `build()` and `modeltest.py` both had these swapped. That is a second independent
defect in the old calibration rebuild, alongside the missing refraction correction, and together they
explain the retracted 0.856 mm pool-test baseline.

Once corrected, the C++ oracle (`oracle.cpp`, driven by `stage2.py`) reproduces the stored
calibration **exactly** on all six cameras: front homographies agree by induced mapping to 4e-13 to
1.1e-12 mm at the nodes and to 6e-12 mm at frame-corner extrapolation points, back homographies to
1.5e-11 to 1.6e-07 mm, camera positions to 6e-12 to 7.4e-08 mm, and `cameraMeanPLD` to every printed
digit (0.626070, 0.814234, 2.526598, 2.110769, 3.913489, 5.446812 mm). **Current production code
rerun from stored inputs reproduces the stored historical calibration; there is no version drift.**
The oracle calls Accelerate's dgesvd, dgetrf, dgetri and cblas, and GSL's hybrids multiroot solver --
the same routines production calls -- rather than reimplementing them.

Refraction correction of the back nodes is material: apparent-position shifts have medians of 0.37 mm
on the pool test, 0.53 to 0.63 mm on the 13 mm document and 0.99 to 1.07 mm on the fisheye, with a
maximum of 5.47 mm. That brackets appendix A of Neuswanger et al. (2016). The four-iteration loop
converges monotonically, with the camera position stable to six decimals by iteration 2.

## Known-length annotations in `2015-09-04-1 Clearwater.vsd` (Rokinon 8 mm fisheye)

Snapshot taken 2026-07-28, document mtime 2026-07-28 12:50. Counts will grow as more annotations are
added; treat them as provenance, not as schema requirements.

**Authoritative loader: `tools/pooltest/knownlength.py`.** Do not re-derive these conventions in a
one-off script. Run it directly on a document for a validation and exclusion report.

Both families live in the shared `ZVSVISIBLEITEM` table -- `Z_ENT` 17 events, 19 objects, 20 object
types -- with the object type's name in `ZNAME3` and the object's own name in `ZNAME2`. Events reach
objects through `Z_17TRACKEDOBJECTS`; 3D points are `ZVSPOINT3D` joined by `ZTRACKEDEVENT`; screen
clicks are `ZVSSCREENPOINT` rows whose `ZPOINT` references the 3D point.

### Conventional two-point measurements

Object type `Length Tests` (the 13 mm document uses `Frame Test`). Object name encodes the true
length: `10 cm`, `19.6 cm`, `30 cm`, `50 cm`, `100 cm`. Exactly two points per event. True length
comes from `jacweight.true_length_mm()`, where a number embedded in the object name is authoritative
-- see the `48squares` trap recorded for the pool test. Current snapshot: **42 valid measurements**,
13 at 100 mm, 4 at 196 mm, 13 at 300 mm, 6 at 500 mm, 6 at 1000 mm. This supersedes the 14
measurements analysed previously, which were the 10 cm, 19.6 cm and 30 cm classes only.

### Point-cloud annotations

Object type `Length Point Cloud`, object names `Cloud A` through `Cloud D`. **Exactly one point per
event.** The event's `ZNOTES` field holds comma-separated numeric local coordinates with no spaces,
for example `10,0`. Dimensionality is verified per cloud rather than assumed; in this document the
notes are **two-dimensional**.

* **Units: the notes are in CENTIMETRES.** Multiply by 10 for millimetres.
* **Scope: coordinates are meaningful only within one cloud object.** Absolute translation and
  orientation between clouds are not supplied and must not be inferred. **Never construct a distance
  between points belonging to different clouds**, even when their note coordinates coincide -- they
  do coincide, because every cloud starts from `0,0`.
* **Geometry: each cloud is the front face of the physical calibration frame at one placement**, so
  all points within a cloud are coplanar. That is a property of the test data, not a licence to
  reconstruct them by a different algorithm; use the normal production pipeline.
* Every cloud point must be clicked in **both** cameras. All 63 currently are.

Pairs: every unordered within-cloud pair (i, j) with i < j, exactly once. True length is the
Euclidean distance between the millimetre-converted note coordinates.

Current snapshot: **4 clouds, 63 valid points, 471 derived pairs, zero exclusions.** Cloud A 18
points and 153 pairs, true lengths 100.0 to 761.6 mm; Cloud B 16 and 120, 100.0 to 1118.0 mm;
Cloud C 13 and 78, 100.0 to 728.0 mm; Cloud D 16 and 120, 100.0 to 824.6 mm. **Each cloud sits at
exactly one timecode**, and the four timecodes are distinct -- 0:04:55:22.15, :24.2, :30.29 and
:39.3 -- so the clouds are four separate frame placements within about seventeen seconds.

### Dependence: pair count is not a sample size

A cloud of n points yields n(n-1)/2 distances that are **not independent**. Each point appears in
n-1 pairs, so one badly clicked point corrupts n-1 distances. The 471 pairs carry the information of
63 points at 4 placements, not 471 measurements. **Do not report independent-pair t-tests, sign
tests, or confidence intervals over pairs.** Use cloud-level summaries, cloud-equal aggregation,
leave-one-point-out jackknife within clouds, and leave-one-cloud-out for the combined effect. Cloud,
placement and timecode are the same thing here and are the natural replication unit -- there are four
of them.

Beyond pairwise lengths, each cloud is a known planar configuration and supports a direct shape
analysis: rigid alignment of the note coordinates to the reconstructed points, pointwise residuals,
best-fit plane and out-of-plane scatter, and separately-reported similarity scale as a diagnostic
only. That can reveal coherent warping which many pairwise lengths would average away.

### Validation performed by the loader

Missing or empty notes; nonnumeric or nonfinite coordinate components; fewer than two components;
inconsistent dimensionality within a cloud; duplicate note coordinates within a cloud; events with
other than one point for clouds or other than two for conventional; missing camera clicks; clouds
with fewer than two valid points; zero true separation; true length not encoded in the object name.
Nothing is silently discarded -- every rejection is returned in an exclusion table with its reason.
An assertion guards against cross-cloud pairing.

### Reconstruction

Use the production-faithful pipeline established in this project: `oracle.cpp` driven by `stage2.py`
for the refractive calibration rebuild, and `parity.triangulate` for endpoints, with calibration-node
access via `nodes.py`. Do not use `distcal.build`.

## Expanded fisheye evidence: scalar eta earns its place on shape, tails and a node jackknife

`tools/pooltest/fisheye_knownlength_analysis.py`, run 2026-07-28 against the expanded annotations in
`2015-09-04-1 Clearwater.vsd` (Rokinon 8 mm fisheye). This supersedes the 14-measurement fisheye
result recorded above.

### How to rerun

```
~/.venvs/vidsync/bin/python tools/pooltest/fisheye_knownlength_analysis.py
~/.venvs/vidsync/bin/python tools/pooltest/test_knownlength.py     # 90 loader checks
```

Prerequisite smoke tests, all of which passed before analysis: `test_gate.py` (30/30), `nodes.py`
(node-orientation invariant on all six cameras), `parity.py` (triangulation reproduces stored 3D
coordinates to a median 1.4e-5 mm on this document), `stage2.py` (oracle rebuild reproduces the
stored calibration to 1e-13 mm at the nodes).

Outputs land in `tools/pooltest/analysis-output/`: `fisheye_points.csv` (per point per model, with
raw clicks, radii, edge margins, support distances, meanPLD, reprojection error, stereo angle, CPA
conditioning), `fisheye_conventional.csv`, `fisheye_cloud_pairs.csv`, `fisheye_cloud_shape.csv`,
`fisheye_cloud_residuals.csv`, `fisheye_node_jackknife.csv`, `fisheye_model_summary.csv`,
`fisheye_validation.json`. Nothing is transcribed by hand; the loader is the only source.

### Data, and a repair the shape analysis caught

Loader: `knownlength.py`. **42 conventional** measurements (13 at 100 mm, 4 at 196, 13 at 300, 6 at
500, 6 at 1000) across **4 timecode placements**, and **4 clouds / 65 points / 504 within-cloud
pairs**, zero exclusions. Cloud A 18 pts, B 16, C 13, D 18.

Two structural facts that govern every summary:

* The 28 newly added conventional measurements **all sit at one timecode**. Tripling the
  conventional sample added one placement, not 28. Conventional replication is 4, not 42.
* There are **8 independent placements** in total (4 conventional timecodes + 4 clouds), sharing
  **one** calibration per camera.

**Cloud D initially reconstructed with a rigid-alignment RMS of 131 mm and a maximum of 359 mm under
all four models.** Model-independence identified it immediately as a data fault rather than a
pipeline or model effect; some points were mis-placed and mis-labelled, and were corrected (16 -> 18
points). Worth recording as method: the rigid-shape analysis is a **data-integrity check**, because a
mislabelled point corrupts a cloud's shape unmistakably while pairwise-length MAE partly averages it
away. Run shape first.

### Models, gate, and exact nesting

| model | free | plumbline px L / R | eta L / R | R_scale L / R | gate |
|---|---|---|---|---|---|
| stored | — | (stored) | 0 | 1.4425 / 1.4310 | pass |
| conv-13 | 13 | 0.8622 / 2.0797 | 0 | 1.3914 / 1.3873 | pass |
| M0 | 8 = centre, k1–k4, p1,p2 | 0.9793 / 2.2538 | 0 | 1.4272 / 1.4284 | pass |
| M1 | 9 = M0 + eta | **0.5338 / 1.1317** | +0.008087 / +0.010882 | 1.4302 / 1.4303 | pass |

All pass the **production** gate (mean radial magnification over the plumbline box, bracket 0.25–4.0)
with minimum determinants 0.957–1.001. Nothing is near either bound, consistent with the retraction
recorded above.

Nesting at eta = 0 verified downstream, not asserted: the undistortion map agrees with the pure
13-parameter port to **4.5e-13 px** over 4000 random frame points, rebuilt homographies and camera
positions agree to **0**, and all 149 measured points reconstruct to **4.8e-6 mm**. `oracle.cpp:60-62`
applies `A = diag(e^eta, e^-eta)`, and `exp(0) = 1.0` exactly in IEEE754, so the conjugation is a
bit-exact identity. Held parameters were zeroed on every seed; the script asserts it.

### Conventional measurements: the earlier benefit reproduces and holds up

| subset | n | stored | conv-13 | M0 | M1 |
|---|---|---|---|---|---|
| original 14 | 14 | **2.9712** | 5.3516 | 4.3075 | 3.3912 |
| new 28 (one placement) | 28 | 4.8722 | 9.0136 | 5.3536 | 4.5841 |
| all 42 | 42 | 4.2385 | 7.7929 | 5.0049 | **4.1865** |

(mean absolute error, mm.) The original-14 row reproduces the historical numbers to four decimals,
which pins the loader's event selection.

**M0 -> M1 on all 42: -0.8184 mm mean, -0.2903 median, better on 28 of 42.** On the original 14 it
was -0.9163 mean but -0.0059 median with 7/14 — the mean-driven, median-neutral pattern recorded
earlier. On the 28 new measurements the median moves too (-0.5918, 21/28 better), so **the effect is
no longer only two large-radius outliers**. It reproduces at 500 and 1000 mm (-0.95 and -1.04 mm).

### Cloud shape is the strongest evidence: M1 improves all four placements

Optimal **proper rigid** alignment of the known planar configuration to the reconstruction — rotation
and translation, **no reflection, no fitted scale**. Similarity scale reported separately as a
diagnostic, because a free scale absorbs the distortion under test. (Caveat: for a planar source an
in-plane reflection is realisable by a proper 3D rotation, so forbidding reflection does not pin
handedness; it only excludes improper ambient maps.)

Rigid RMS, mm:

| cloud | stored | conv-13 | M0 | M1 | M1-M0 |
|---|---|---|---|---|---|
| A | 4.977 | 7.261 | 6.326 | 5.106 | **-1.220** |
| B | 11.486 | 16.680 | 12.734 | 11.517 | **-1.217** |
| C | 5.287 | 8.548 | 5.219 | 4.964 | **-0.255** |
| D | 7.956 | 13.981 | 12.016 | 7.854 | **-4.161** |

**4 of 4 placements improve**, and leave-one-point-out held-out residuals agree (-1.42, -1.47, -0.23,
-4.48 mm RMS). M1 also reduces out-of-plane scatter in 3 of 4 clouds (M0 -> M1: 3.62 -> 2.23,
6.74 -> 5.44, 2.40 -> 2.61, 4.14 -> 2.75 mm), and reduces the diagnostic in-plane **anisotropy ratio
in all four** (1.0174 -> 1.0138, 1.0502 -> 1.0488, 1.0499 -> 1.0460, 1.0414 -> 1.0367) and |shear| in
all four. Mean scale moves toward 1 in three of four.

### Weighting schemes all agree, which is the point of reporting four

| scheme | M0 | M1 | M1-M0 |
|---|---|---|---|
| equal pair weight (504 pairs, descriptive only) | 8.031 | 6.428 | -1.602 |
| equal cloud weight (4 clouds, primary) | 7.622 | 6.238 | -1.384 |
| conventional, flat over 42 | 5.005 | 4.187 | -0.818 |
| conventional, equal over 7 object x timecode groups | 5.125 | 4.273 | -0.853 |
| conventional, equal over 4 placements | 4.633 | 3.747 | -0.887 |
| source-balanced over 8 placements | 6.128 | 4.992 | -1.135 |

The conclusion does not depend on the weighting. Equal-pair weighting overstates the effect by about
2x relative to placement weighting, exactly as combinatorial domination predicts — so quote the
placement-weighted figure.

### Mechanism: the gain is at large radius, long range and outside calibration support

M1-minus-M0 on cloud pairs, by stratum (mm):

| max image radius | n | mean change |
|---|---|---|
| 0–500 px | 93 | -0.396 |
| 500–700 | 44 | -0.382 |
| 700–850 | 148 | -0.079 |
| **850–1000** | **219** | **-3.390** |

Correlations: distance outside the calibration-node image hull **-0.594**, outside plumbline support
-0.445, max image radius -0.323, min screen-edge margin +0.355. By true length the gain peaks at
600–800 mm (-4.28). Pairs more than 75 mm outside the calibrated volume gain -2.58 against +0.10
inside. There is a real orientation dependence (-2.01 and -3.12 in the 0–30 and 150–180 degree
bins against +0.46 at 60–90), consistent with an anisotropic radius map.

So eta acts exactly where a scalar anisotropy of the radial argument should: **at the frame edge and
beyond the region the calibration constrains**.

### Tails: a genuine tail improvement, partly carried by influential endpoints

M0's own worst cases, re-evaluated under M1 (fixed baseline):

| cloud pairs | n | M0 mean \|e\| | M1 | improved |
|---|---|---|---|---|
| worst 10% | 51 | 27.50 | 19.24 | 50/51 |
| worst 5% | 26 | 33.38 | 24.36 | 26/26 |
| worst 1% | 6 | 41.37 | 27.27 | 6/6 |

Conventional worst 10% goes 20.09 -> 14.87 mm, 5/5 improved. Percent-error p99 falls 12.73 -> 7.52
on pairs and 7.87 -> 5.12 on conventional.

**But influence is concentrated**: of the 26 largest M1-vs-M0 changes, Cloud D's (900,100) endpoint
appears in 14 and (800,300) in 11. That is one far-corner region of one placement, not 26 independent
successes, and it should be described that way. It is not the whole effect: leave-one-point-out keeps
M1-M0 negative across **all 18** single-point removals in Cloud D (-4.23 to -3.00) and across all
removals in A and C. Cloud B is the exception, sign-unstable under point removal (-0.87 to +0.04).
The recurring degradation is Cloud A's (700,300) corner, where M1 is 5–8 mm worse on several pairs.

### The calibration-node jackknife was required, and the ranking survives

The M1-M0 effect (1.38 mm) is **below** the back-node calibration residual (4.47 mm), and all four
clouds share one calibration — so sign consistency across clouds could equally be one shared
calibration bias. That is exactly the case the handoff reserved the jackknife for.

Five folds, each dropping physical nodes — identified by world (h,v) coordinate, so the same physical
node leaves **both** cameras and both surfaces — then rebuilding the front homography, the
four-iteration refractive back surface and the camera position, and re-measuring everything:

| fold | M0 pair MAE | M1 | change | M0 rigid | M1 | change | M0 conv42 | M1 | change |
|---|---|---|---|---|---|---|---|---|
| 0 | 7.797 | 6.804 | -0.993 | 9.134 | 7.726 | -1.408 | 4.177 | 3.578 | -0.599 |
| 1 | 6.415 | 5.199 | -1.217 | 7.836 | 6.188 | -1.647 | 3.944 | 2.969 | -0.975 |
| 2 | 9.377 | 8.490 | -0.887 | 10.604 | 9.302 | -1.302 | 5.955 | 5.096 | -0.859 |
| 3 | 9.685 | 8.157 | -1.527 | 11.533 | 9.508 | -2.025 | 7.070 | 5.766 | -1.304 |
| 4 | 7.717 | 6.318 | -1.399 | 9.070 | 7.393 | -1.677 | 5.028 | 4.260 | -0.768 |

**Sign-stable on all three metrics in all five folds.** M1 improves rigid shape in 3–4 of 4 clouds in
every fold. The spread across folds — 0.72 mm on rigid RMS, 0.64 mm on pair MAE — is the honest scale
of calibration-induced uncertainty on this contrast, and it is smaller than the effect.

### The awkward part: a fresh refit still loses to the parameters already in the file

| | conventional 42 | cloud-equal pairs | cloud rigid RMS | source-balanced |
|---|---|---|---|---|
| stored | 4.2385 | 6.4402 | 7.4267 | 4.9623 |
| conv-13 | 7.7929 | 9.6581 | 11.6173 | 8.0129 |
| M0 | 5.0049 | 7.6216 | 9.0736 | 6.1275 |
| M1 | **4.1865** | **6.2378** | **7.3604** | 4.9922 |

**conv-13 and M0 are both clearly worse than the document's stored parameters; M1 roughly ties
them.** This is the fourth appearance of the pattern recorded above — the stored parameters were
fitted to an older detection, and this document currently carries a two-set left-camera plumbline
arrangement (80 lines over 2 timecodes on the left, 51 on the right) which the notes above already
flag as stale and as mixing two board distances. So the defensible claim is **not** "M1 beats
production". It is:

* **M1 beats M0 decisively** — same data, same fitter, exactly nested, jackknife-stable. This is the
  clean contrast and it is the one the eta question turns on.
* **M1 recovers what a fresh truncated refit throws away**, returning to stored-parameter accuracy
  while halving the plumbline residual.
* **Radial truncation alone (M0) is not supported on measurement here**: it is 0.77 mm worse than
  stored on conventional and 1.65 mm worse on cloud rigid shape. The earlier "measurement-neutral"
  verdict for the ten-parameter model does not extend to this eight-parameter one on the fisheye.
* **conv-13 is the worst model on every metric**, reinforcing that thorough optimization of the
  existing 13 parameters is not the answer.

### What this does and does not license

It does support **including scalar eta when the truncated radial model is used on high-distortion
systems**, which is where the mechanism predicts it should matter and where it is now measured
across 8 placements, 4 independently-jackknifed calibrations and both annotation families.

It does not yet license a production default change, for three reasons:

1. **One document, one lens, one calibration.** Eight placements inside seventeen seconds of one
   clip is not eight calibrations. The jackknife perturbs one calibration; it does not replicate it.
2. **The stale plumbline arrangement in this file.** The two-set left-camera configuration is flagged
   above as not at either set's optimum, and every refit here inherits it.
3. **No corpus or pool-test check.** The pool test has 1010 known lengths and near-zero distortion,
   so it is the right harm-check for eta and has not been run with the corrected pipeline. The
   earlier pool-test eta win was retracted as seed contamination.

The next measurements worth taking, in order: eta on the pool test through this same pipeline as a
negative control; eta across the 67-document corpus at 10, 13 and 17 mm; and a second fisheye
document with known lengths and an independent calibration.

### Control: the ninth parameter has to be eta, not more radial order

`tools/pooltest/fisheye_eta_vs_radial_control.py`. M1 beats M0 by adding one parameter, so the
obvious confound is parameter count. Restoring a dropped radial term costs exactly one parameter and
stays inside Brown-Conrady, giving a like-for-like nine-parameter control.

| model | free | plumbline px L / R | conv 42 MAE | cloud-equal pair MAE | cloud rigid RMS |
|---|---|---|---|---|---|
| M0 | 8 | 0.9793 / 2.2538 | 5.0049 | 7.6216 | 9.0736 |
| M0+k5 | **9** | 0.9751 / 2.2526 | 4.9062 | 7.5882 | 8.9821 |
| M1 (M0+eta) | **9** | **0.5338 / 1.1317** | **4.1865** | **6.2378** | **7.3604** |

**At identical parameter count the extra radial term buys essentially nothing** — 0.09 mm of rigid
RMS and 0.10 mm of conventional MAE, against eta's 1.71 and 0.82 mm — and it barely moves the
plumbline objective (0.004 and 0.001 px). So the M1 result is **not** a degrees-of-freedom artifact,
and it independently confirms the earlier finding that the radial series is exhausted at four terms:
the fifth radial coefficient is inert on measurement as well as on straightness. The anisotropy is
capturing structure the radial family cannot reach at any order.

This is the strongest single argument in the fisheye evidence, because it is the one comparison that
holds parameter count, model family, fitter, data and pipeline all fixed.

## Solver-parity audit of the in-app 13-parameter distortion fit (2026-07-28)

The document `2015-09-04-1 Clearwater.vsd` was re-solved for distortion inside VidSync on
2026-07-28 (sha256 `5118cb07e2da6096…`, mtime 14:32:36). Call the resulting coefficients **APP13**,
never "stored" or "production calibration": the historical stored values this project's earlier
fisheye rounds used are a *different* solution, and conflating them caused real confusion.

Scripts: `parity_step1.py` (freeze and anchor), `plumb_oracle.cpp` + `parity_step2.py` (map and
objective parity), `parity_step3.py` (replay, restart, multistart), `parity_step4.py` (timecode
composition), `parity_step5.py` (downstream), `parity_step6.py` (basin and direction analysis).
Logs and JSON in `analysis-output/parity_step*.{log,json}`.

### What the application actually fits

`calculateDistortionCorrection` (VSCalibration.mm:2308) minimizes the plain sum of squared
orthogonal-regression residuals over **every** line of the calibration, with no weighting, no
normalization, no bounds and no penalty. There is **no timecode filter** — `[self.distortionLines
allObjects]` — so the Left clip's two plumbline captures are fitted **jointly**, which the audit
confirmed independently by reproducing the stored per-point residual exactly. Lines with fewer than
three points contribute zero and are excluded from the point count. Clicks are read through
`-floatValue`; every coordinate in these documents is exactly float-representable, verified, so that
cast is lossless here. Solver: GSL `nmsimplex2` from centre `(w/2, h/2)` with all coefficients zero,
step sizes 0.001 for the centre and 25 for the rest, stopping when the simplex size falls below
1e-10, capped at 10000 iterations, **no restarts**. The acceptance gate is applied afterwards as an
accept/reject and never shapes the search.

`calculateDistortionCorrection` does **not** call `calculateCalibration`. Recomputing distortion
leaves the homographies, refractive back-surface correction, camera position and stored 3D
coordinates untouched. Any model comparison must rebuild them from raw frame-node clicks, for every
candidate including APP13.

### Parity established

`plumb_oracle.cpp` transcribes `orthogonalRegressionLineCostFunction`, `undistortPoint`,
`undistortionJacobian`, `reasonToRejectSolvedDistortion:` and the Nelder-Mead driver verbatim.
At APP13 it agrees with the offline evaluator to **1.2e-14 relative on total SSE**, 1e-11 px² per
line, 9e-13 px per point, and its per-point residual reproduces the document's stored
`distortionRemainingPerPoint` **to the last bit**. The maps agree to **1e-12 px** on every plumbline
point, every calibration node, all 1042 measurement clicks and a 61×61 full-frame grid; the gate's
minimum determinant and radial scale ratio agree to 1e-16.

**GSL version is load-bearing.** The app links its own bundled `gsl-2.6-universal/libgsl.a`; the
system GSL at `/usr/local` is 2.7.1. Built against 2.7.1 the replay missed APP13 by 5 px in the map
and looked like a solver disagreement. Built against the bundled 2.6 it reproduces APP13 to
**1e-14 px** per-point residual and **9e-6 px** anywhere in the frame. Link the bundled 2.6, or the
replay is not a replay.

### APP13 is not a converged optimum, and is not reproducible on the Left clip

* **Not stationary.** Gradient of SSE at APP13 is 6.9e3 (Left) and 1.0e4 (Right) in production's own
  scaled units; the Gauss-Newton step from it has norm ~1e5. Restarting production's *own* solver at
  APP13 descends 4.8% (Left) and 8.7% (Right).
* **Chaotic.** Nudging the start's centre by a **relative 1e-12** moves the Left endpoint by 5.5 px
  over the frame and 9.6 px² in SSE; at 1e-6 the spread reaches 62.7 px² and 60 px. APP13 sits
  *inside* the spread the solver produces from indistinguishable starts. The Right clip is stable to
  1e-9 and only moves at 1e-6.
* **Confirmed by the user's own recompute.** The Right clip's new coefficients reproduce the previous
  stored ones to 3e-9 in radial scale ratio. The Left clip's do not (1.44246 -> 1.43395). Same code,
  same data, same start: one camera reproducible, the other not.
* **Robust optimization of the identical objective descends materially:** Left 989.87 -> 736.62 px²
  (RMS 0.9994 -> 0.8622), Right 4271.37 -> 3441.58 (2.3092 -> 2.0728). Every endpoint passes the
  production gate, so the gate is not what binds.

### The cause is weak-model degeneracy, not convergence, coverage, or arithmetic

`parity_step6.py`. The APP13 -> POLISH13 step lies **91% (Left) and 98% (Right) in the single
weakest singular direction** of the residual Jacobian, and 99.4%/99.98% in the four weakest; the four
best-determined directions carry 0.17%/0.004%. Jacobian condition is 9.4e7/1.5e8. The straight
segment between them crosses a barrier of ~1e10 px², so they are **separate basins** — separated
along a direction the objective can barely see. The excursion is the classic high-order runaway with
cancellation: k5 and k6 move by ±1e4 in scaled units and nearly cancel, p1/p2 move by four orders of
magnitude, and the whole thing still passes the gate.

The difference is **not** confined to extrapolation: on the plumbline points themselves the two maps
differ by a median of 34.5 px (Left) and 37.9 px (Right), maxima 225 and 250 px.

### Timecode composition is not the explanation

Left capture 1 alone fits to 0.8295 px, capture 2 alone to 0.8208 px, both jointly to 0.8622 px.
Cross-evaluated, capture 1's fit scores 0.9407 on capture 2 and capture 2's scores 1.0227 on capture
1 — mildly asymmetric, not incompatible. Yet the two capture solutions' **maps differ by a median of
40 px and a maximum of 125 px**. The Right clip, having one capture, is the control and gives
**exactly 0.000** difference between "subset" and "joint", which validates the harness.

### Downstream: better plumbline residual, worse measurement — the fifth appearance

All candidates rebuilt from raw frame-node clicks through `oracle.cpp`. Nothing reuses stored
matrices, including APP13.

| candidate | plumb px L / R | conv42 MAE | conv42 median | cloud-equal pair | cloud rigid RMS | source-balanced |
|---|---|---|---|---|---|---|
| APP13 | 0.9994 / 2.3092 | 4.9432 | 2.9412 | 7.6707 | 8.8373 | 6.1135 |
| POLISH13 | **0.8622 / 2.0728** | 7.6849 | 3.8864 | 9.6541 | 11.6000 | 7.9701 |
| M0 | 0.9793 / 2.2538 | 5.0049 | 2.6850 | 7.6216 | 9.0736 | 6.1275 |
| M1 | 0.5338 / 1.1317 | 4.1865 | 2.1637 | **6.2378** | **7.3604** | 4.9922 |
| APP13+eta | 0.4680 / 1.1119 | 4.0539 | 2.1505 | 6.3006 | 7.4200 | 4.9438 |
| POLISH13+eta | **0.4680 / 1.1132** | **4.0247** | **1.9074** | 6.2755 | 7.3649 | **4.9283** |

**Changing only the solver, APP13 -> POLISH13, degrades every measurement metric** — conventional MAE
+2.74 mm, cloud-equal pair +1.98, rigid shape +2.76, source-balanced +1.86 — while lowering the
plumbline residual by 14% and 10%. Thorough optimization of the 13-parameter model on its own
objective is measurably harmful.

**The solver's irreproducibility is larger than the effects earlier rounds were built on.** Against
the previous stored solution under the same pipeline, APP13 alone moved conventional MAE from 4.2385
to 4.9432 mm (+0.70), cloud-equal pair 6.4402 -> 7.6707 (+1.23), rigid RMS 7.4267 -> 8.8373 (+1.41),
source-balanced 4.9623 -> 6.1135 (+1.15). The Right camera barely changed, so essentially all of that
came from re-running the Left solve. Those swings equal or exceed the entire M1-vs-M0 effect
(-0.82 conventional, -1.38 pair/rigid). **Any comparison of a candidate model against "what the
document happens to contain" is therefore uninterpretable at the precision this project cares about.**

M1's own numbers reproduce the earlier round to four decimals (4.1865 / 6.2378 / 7.3604 / 4.9922),
confirming the recompute did not disturb the model fits, which depend only on the plumblines.

### eta survives the audit, and now stands on the full model too

eta had only been tested after k5–k7 and p3,p4 were removed. Added to the **complete** 13-parameter
model it still helps, and the fitted value barely moves: **+0.00825 / +0.01100** (APP13+eta) and
**+0.00825 / +0.01086** (POLISH13+eta) against M1's +0.00809 / +0.01088. On the Left clip APP13+eta
and POLISH13+eta converge to the **same** solution (SSE 217.058 to six digits), i.e. adding eta
substantially removes the multi-basin degeneracy that makes the 13-parameter fit irreproducible.
Nesting against the eta = 0 parents holds in all six cases, bit-exactly by construction.

Still not a licence to change defaults: one document, one lens, one calibration, the stale two-set
Left plumbline arrangement, and no pool-test negative control. But the audit removes one specific
objection — eta is not an artefact of first truncating the radial series.

## Model-stability and projective-gauge round (2026-07-28, same frozen document)

Same anchor as the solver-parity audit: `2015-09-04-1 Clearwater.vsd`, sha256 `5118cb07e2da6096…`,
opened read-only, unchanged. Scripts: `stab_fits.py` (seed battery), `stab_gauge.py` (projective
decomposition and conditioning), `stab_metrics.py` (measurement stability), `stab_degeneracy.py`
(gate blind spot), `stab_etaprofile.py` (eta profile). `plumb_oracle.cpp` gained a free-parameter mask
and an eta term; the 13-parameter no-eta path is unchanged and still replays APP13 bit-for-bit at the
same iteration counts (3902 / 3646), which is the regression check that licenses the extension.

Models, as free index sets over the 14-vector (0,1 centre; 2..8 k1..k7; 9..12 p1..p4; 13 eta):
M0 = [0,1,2,3,4,5,9,10]; M1 = M0 + [13]; FULL13 = [0..12]; F13eta = [0..13].

### Two corrections to the solver-parity round

1. **"Adding eta substantially removes the multi-basin degeneracy" is WITHDRAWN.** That was inferred
   from APP13+eta and POLISH13+eta reaching the same SSE, which the round itself flagged as
   suggestive-not-sufficient. It is wrong. F13eta's residual-Jacobian condition number is 7.5e7 to
   1.0e8 against FULL13's 1.1e8 to 2.9e8 -- a factor of 1.5 to 3, not orders. Its weakest singular
   direction is still k5 (0.71 to 0.72) plus k6 (0.28), and the high-order near-cancellation is fully
   intact: k5 and k6 come out at -29122 and +15109 in scaled units on the Left, -158710 and +92884 on
   the Right. What buys conditioning is TRUNCATION, not eta: M0 and M1 sit at 1.9e5 to 2.8e5, three
   orders better, with full effective rank at a 1e-6 threshold where FULL13 and F13eta lose three or
   four directions.
2. **eta is exactly nested but not exactly bounded.** The nesting is bit-exact (below). The problem is
   that nothing bounds eta, and the shipped gate cannot supply the bound.

### The eta gate hole, which is the round's most consequential finding

The seed battery found nine endpoints that are not lens corrections. Four are collapses with
per-point residuals of 7e-5 to 2e-4 px, four orders below the click-noise floor. Five have entirely
plausible residuals. The worst is on M1 / Right Camera: **eta = -1.9827, per-point residual 0.4636 px
-- BETTER than the near-isotropic optimum's 1.1317 px -- and the SHIPPED PRODUCTION GATE ACCEPTS IT**,
reporting a radial scale ratio of 1.3403 and a minimum determinant of +0.5267. It is reached from the
POLISH13-projected seed by production's own Nelder-Mead. The gate accepts 4 of the 9, all four in M1.

The gate misses them because `reasonToRejectSolvedDistortion:` inspects the thirteen Brown-Conrady
parameters only; eta is not among them.

State the Jacobian algebra carefully, because the tempting version is wrong. J_U(x) = A^-1 J_B(A(x-c))
A, so POINTWISE det J_U = det J_B: eta adds no local area change of its own, confirmed to 4e-2
relative (finite-difference accuracy). But the gate minimizes over a FIXED box and A relocates where
the core is sampled, so the box minimum is NOT invariant -- unchanged to 1e-5 for |eta| < 0.05, and
moving by up to 5.9e7 for |eta| >= 0.05.

Which tests can separate the branches, measured over the 130 converged physical-branch endpoints:

* shipped gate on the 13-parameter core -- accepts 4 of 9. **No.**
* the existing (0.25, 4.0) bracket recomputed on the full eta-aware map -- off-branch ratios include
  0.3051, 0.3044, 0.3306 and 0.4518, all inside the bracket. **No.**
* plumbline residual alone -- five off-branch endpoints sit inside the physical range and one fits
  better than its model's optimum. **No.**
* total local map anisotropy -- useless: a fisheye correction is genuinely anisotropic and measures
  3.54 to 4.58 at eta ~ 0.01. **No.** (A wrong turn taken and corrected.)
* **minimum determinant recomputed on the full eta-aware map -- every off-branch endpoint is
  NEGATIVE, every converged physical-branch endpoint is above +0.9313. YES.**
* exp(2|eta|) -- off-branch 1.898 to 52.74, physical-branch 1.0000 to 1.0222; any cut in the empty
  gap (1.22, 1.90) gives the same partition. **YES.**

So a one-line change would close the hole: evaluate the existing minimum-determinant test on the
eta-aware map rather than the Brown-Conrady core. **Not implemented -- no production code was touched
this round.** But eta must not ship before it is.

### Exact nesting, verified numerically

M1 at eta = 0 reproduces M0's residuals to **0.0e+00** on both cameras. F13eta at eta = 0 reproduces
the full-13 residuals to **0.0e+00** and the full-13 map to **0.0e+00**. This is by construction: at
eta == 0 the eta-aware map delegates to the Step-2-verified `fitter.undistort` rather than relying on
exp(0) == 1, because the conjugated spelling accumulates terms in a different order and differs in the
last bits (4.5e-13 px). Every optimized superset beat its embedded parent.

### Reproducibility, from 8 to 12 seeds per model per camera, two solvers each

| model | robust solver | production Nelder-Mead | alternative basin with LOWER SSE? |
|---|---|---|---|
| M0 | 8/8 identical both cameras | Right 8/8; Left 6/8 (one stall at 1104.68, one large-perturbation failure) | none |
| M1 | 11/11 on the near-isotropic branch | 12/12 Left; Right 9 endpoints 1025.93-1097.07 | **YES -- eta -1.98 at SSE 172.2, gate-accepted** |
| FULL13 | Left 736.62-936.67 (two basins); Right 3441.58-3764.50 | Left up to 2334; Right up to 16818 | n/a |
| F13eta | Left 217.06-217.95; Right 990.31 plus scatter | Left up to 4584; Right up to 1479 | **YES -- collapses at eta +0.63 and +0.50** |

M0 is the only model with no alternative basin at all. M1 is highly reproducible **on the branch** and
not reproducible off it.

### Projective-gauge decomposition

The plumbline zero set is invariant under a homography of the corrected output, so an 8-DOF H was
fitted (Hartley-normalized DLT then geometric refinement) on ~5000 dense in-hull samples, both
directions, per pair. Fraction of raw squared displacement absorbed, and the non-projective remainder
as rms over the dense in-hull set:

| pair | absorbed | non-projective remainder |
|---|---|---|
| APP13 vs POLISH13, Left / Right | 99.12% / 98.42% | 4.64 px / 5.76 px |
| FULL13 most separated, Left / Right | 99.11% / 97.94% | 4.66 px / 6.66 px |
| M0 most separated (Left only) | 99.36% | 0.90 px |
| M1 most separated (Right only) | 99.30% | 0.85 px |
| F13eta most separated, Left / Right | 99.72% / 99.35% | 0.80 px / 2.87 px |
| **best M0 vs best M1**, Left / Right | **80.24% / 89.43%** | **4.67 px / 2.85 px** |
| best M1 vs best F13eta, Left / Right | 93.65% / 98.18% | 0.64 px / 0.52 px |

Reversing the reference direction changes the absorbed fraction by less than 0.01, so the numbers are
not an artifact of which map was called the reference.

Reading: **most of the full-13 solver wander is gauge, but not all of it.** 99% absorbed still leaves
4.6 to 6.7 px of genuinely non-projective disagreement, and that is the part the metrics see. M0, M1
and F13eta leave 0.5 to 2.9 px -- an order of magnitude less. **The M0-to-M1 difference is the one
thing here that is substantially NON-projective (only 80 to 89% absorbed), which is exactly what eta
being real structure rather than gauge should look like.** M1-to-F13eta is 94 to 98% projective,
i.e. the five extra Brown-Conrady terms add almost nothing a homography could not mimic.

Do NOT read the high absorbed fractions as "gauge is harmless". The front homography is refitted
downstream, but the back surface is refraction-corrected and the camera position is triangulated, so
absorption is not automatic -- and the metrics below show it is not complete.

### eta identifiability

Profile over eta with every other free parameter reoptimized at each grid point (`stab_etaprofile.py`;
the first attempt was flat because holding eta by omitting it from the free set ran through a helper
that zeroes held parameters -- artifact, fixed).

* eta is **sharply determined locally**: a 1% rise in the profile needs only +/-0.0005 to +/-0.0010,
  i.e. 5 to 10% of eta's own value. Local curvature 2.4e7 to 4.8e7.
* dSSE at eta = 0 is **237% (M1 Left), 297% (M1 Right), 332% (F13eta Left), 280% (F13eta Right)** of
  each profile's own minimum. eta is nowhere near a marginal parameter on this objective.
* Single well on the +/-0.02 grid. That is a LOCAL statement: the degenerate branch sits at eta near
  -1.6 to -2.0, far outside it.
* eta is **not aligned with the weak directions**: its share of the weakest 1, 2 and 3 singular
  directions is 0.0000 in every model and camera. eta is identifiable; the k5/k6 pair is not.
* Fitted eta is stable across every physical-branch endpoint and both models: +0.00809 to +0.00825
  (Left), +0.01086 to +0.01099 (Right).

### Measurement stability across solver endpoints

Admissibility, one rule: on the physical branch, passing the shipped gate, and within 2x of the
model's best admissible SSE (which keeps genuine alternative basins at 1.09x to 1.27x and drops gross
convergence failures). Every exclusion is logged. Range across admissible endpoints, in mm:

| metric | M0 (n=2) | M1 (n=2) | F13eta (n=14) | FULL13 (n=14) | FULL13 + historical (n=15) |
|---|---|---|---|---|---|
| conventional 42 MAE | 4.9131 (0.18) | 4.1786 (0.02) | 4.0247 (0.03) | 7.1635 (1.05) | 7.1462 (3.45) |
| conventional 42 median | 2.5782 (0.21) | 2.0971 (0.13) | 1.9074 (0.31) | 3.6782 (0.70) | 3.6293 (0.74) |
| original 14 MAE | 4.1880 (0.24) | 3.4374 (0.09) | 3.2394 (0.01) | 5.1582 (0.40) | 5.1576 (2.33) |
| cloud-equal pair MAE | 7.5973 (0.05) | 6.2068 (0.06) | 6.2755 (0.04) | 9.3313 (0.96) | 9.3291 (3.22) |
| equal-cloud rigid RMS | 8.9920 (0.16) | 7.3634 (0.01) | 7.3649 (0.08) | 11.1869 (1.10) | 11.1843 (4.18) |
| source-balanced | 6.0614 (0.13) | 4.9912 (0.002) | 4.9283 (0.03) | 7.6595 (0.80) | 7.6577 (3.01) |

(median, with range in parentheses.) **M1's metric spread is 20 to 400 times smaller than the full-13
envelope's** -- 0.002 to 0.13 mm against 0.70 to 1.10 mm, or 3.0 to 4.2 mm once the historical
endpoint is included. F13eta is comparably tight on n=14 candidates, which is stronger evidence of
stability than M1's n=2, though part of that is simply that F13eta's admissible SSE range is 3.7%
wide against FULL13's 27%.

Within FULL13 and F13eta, lower plumbline SSE goes with HIGHER measurement error: Pearson -0.78 to
-0.95, Spearman -0.71 to -0.92 across five of six metrics. Descriptive only on 14 deliberately chosen
endpoints, but it is the same anticorrelation the project keeps meeting, now visible inside a single
model at fixed parameterization.

Against the full-13 envelope (best / median / worst), by median: M1 beats the envelope BEST on
conventional MAE, conventional median, cloud pair and rigid RMS, and essentially ties it on
source-balanced (+0.03) and loses on the original 14 (+0.47, against an envelope best of 2.9712 that
is the historical endpoint). F13eta is similar, winning conventional by a further 0.15 mm and losing
cloud pair by 0.07 mm.

### F13eta versus M1

F13eta's advantage over M1 is not consistent across metric families: better on conventional 42 MAE
(4.0247 against 4.1786), conventional median (1.9074 against 2.0971) and the original 14 (3.2394
against 3.4374); worse on cloud-equal pair error (6.2755 against 6.2068); tied on rigid shape (7.3649
against 7.3634) and source-balanced (4.9283 against 4.9912). Differences of 0.02 to 0.20 mm, against
per-model spreads of 0.01 to 0.31 mm. It also costs five more parameters, keeps the k5/k6 null
direction, keeps a condition number three orders worse than M1's, and adds its own collapse branch.
**No repeatable metric advantage large enough to justify the extra terms.**

## New distortion objectives, offline round 1 (2026-07-28, same frozen document)

Same anchor, unchanged: `2015-09-04-1 Clearwater.vsd`, sha256 `5118cb07e2da6096…`, read-only. No
production code, defaults, or document touched. Full 13-parameter fitting is retired; only M0 (centre,
k1..k4, p1, p2) and M1 (M0 plus scalar eta, conjugated, bounded to |eta| <= 0.05) appear.

New files: `lattice.py` (unique observations, indices, quadrature, map with analytic Jacobian and
inverse), `objectives.py` (B, SD, ED, PD on one interface), `obj_synth.py` (synthetic validation),
`obj_round1.py` (real fits and diagnostics). Reproduce with
`~/.venvs/vidsync/bin/python tools/pooltest/lattice.py`, then `obj_synth.py`, then `obj_round1.py`.

### What the stored plumbline representation actually is

Measured, not assumed. A shared corner is stored with **bit-identical** coordinates in both of its
lines, multiplicities are only 1 or 2, and every multiplicity-2 is cross-family, so unique
observations come from **exact coordinate equality with no tolerance**; the nearest DISTINCT pair is
18.9 to 28.2 px, which is the evidence that exact matching cannot merge two different corners.

Within a stored line, consecutive points ARE adjacent corners: each gap's ratio to its neighbouring
gaps on the same line is within 0.2 of 1.0 for 93 to 100 percent of gaps. **Line-to-line offsets are
NOT a usable index source** -- the legacy detector fragments one physical row into several line records
(local offset-gap ratios down to 0.19) and once joins unrelated segments (a 1649 px within-line jump on
a Right-camera line). Ranking lines by perpendicular offset and calling the rank an index is therefore
wrong on this data. Indices come from the **within-line adjacency graph** instead, which merges
fragments automatically wherever a crossing line ties them together.

Result per capture: Left 0:04:56:37.8 209 of 212 reliably indexed, Left 0:04:56:41.0 378 of 378, Right
408 of 412; **zero index contradictions** after breadth-first propagation and re-checking every edge;
5, 0 and 14 non-unit adjacency edges dropped rather than guessed at. Lattice occupancy is 0.46 to 0.77
of the bounding index rectangle, so missing corners are the norm, as expected.

**Index labels are only comparable within a connected component.** Every component's search starts at
its own (0, 0). Two consequences, both found the hard way:

* Diagonal holdout families must be grouped by component as well as by k. Pooling across components
  gave a meaningless holdout residual of about 260 px for every candidate map.
* One homography per capture can only describe one lattice, so PD must be restricted to a single
  component per capture. On this document the doubly-constrained indexed subset already lies entirely
  in the largest component (398 of Left, 387 of Right), so the restriction costs nothing in the primary
  comparison; it drops 47 and 77 singly-constrained observations from the Left ED secondary set.

### Quadrature weights

Pooled Delaunay mass lumping, a_i = (1/3) sum of incident triangle areas, normalized to mean 1, over
the pooled raw locations of all a camera's captures. Triangles are dropped when their longest edge
exceeds kappa times the **local lattice edge scale** measured from the observed within-line gaps -- not
from any residual-correlation length. Coincident observations from different captures are clustered,
triangulated once, and their mass divided, so overlapping captures divide local area rather than
multiplying influence. kappa = 3 keeps 737 of 758 triangles (Left) and 717 of 736 (Right); kappa 2 and
4 change the largest weight by 6 to 28 percent, which is reported rather than tuned away.

### Two implementation traps worth remembering

1. **The default parameter start must put the distortion centre at the frame centre**, as production
   does. A base of all zeros puts it at the image ORIGIN, and from there even the production objective
   B fails to converge on exactly consistent synthetic data -- it stalled with the centre at (323, 542)
   against a truth of (955, 535). Every objective was verified to be exactly zero at the truth
   throughout, so the symptom was purely the starting point.
2. **`inv_U`'s Newton tolerance must not be tighter than about 1e-10 px.** Coordinates are of order
   1e3, so 1e-13 is unreachable in double precision and the break test never fires, silently running
   the full iteration cap on every evaluation. That cost a factor of ten in every exact-objective
   evaluation.

Also: holding eta at a fixed nonzero value for a profile must not go through a helper that zeroes held
parameters. That produced a perfectly flat eta profile twice in this project, once here and once in the
model-stability round.

### Synthetic validation, all passing

Recovery from a known central model with irregular missing corners (gauge-removed map error 1.3e-13
px); recovery of a known eta = 0.022 to 1e-6; **exact** invariance of SD, ED and PD to duplicated line
storage (0.00e+00 map difference, after deduplicating identical line records, which is also what keeps
the Sampson constraint blocks full rank) against B's loss doubling; two captures with different
homographies and one shared distortion (1.1e-13 px); a capture-specific 20 px centre perturbation
producing one pooled compromise at (962.9, 520.4) between the two truths rather than a per-capture
correction; analytic Jacobian against central differences to 2e-10; forward/inverse round trip to
7e-13 px for M0 and for eta = +-0.05.

The decisive test is the **separable nonprojective warp**. Building corrected coordinates as
(f(c), g(r)) with quadratic f and g keeps every row and column exactly straight (verified to 5.5e-13
px) while being non-projective. SD and ED cannot see it at all -- loss 1.9e-24 warped against 2.3e-24
clean. PD's loss goes from 1.0e-22 to 483, and the diagonal holdout from 1.2e-13 px to 16.9 px. That is
the finite-incidence weakness of any row/column objective, demonstrated rather than argued.

### SD versus ED: the Sampson approximation is adequate here

Synthetic, as noise grows: map difference 0.0003 px at 0.1 px noise, 0.0028 px at 0.5 px, 0.019 px at
1 px, 0.025 px at 4 px. The project's measured plumbline localization scatter is about 0.40 px, so the
realistic regime is the flat part.

On real data the two are practically the same estimator: losses 110.531 against 110.591 and 18.2252
against 18.2259 (Left), 222.099 against 222.493 and 29.1358 against 29.1091 (Right); eta +0.0081016
against +0.0081015 and +0.0102942 against +0.0102982; **map differences of median 0.000 to 0.008 px,
maximum 0.071 px**. ED costs 3 to 17 times the runtime. SD is the practical choice and ED is the
exactness check.

### Real fits, both clips, common reliably-indexed doubly-constrained subset

Left 398 observations from 2 captures over 67 lines; Right 387 from 1 capture over 50 lines. eta was
interior to its bound in every fit, and every M1 fit beat its own embedded M0 solution under its own
objective (nesting verified, gains 92 to 3043).

Common external diagnostics, Left then Right, as stored-line RMS / raw-line RMS / lattice RMS /
**zero-weight diagonal holdout RMS**, all px:

* B M0 0.979 / 0.809 / 1.250 / 0.585  and  2.254 / 1.260 / 1.696 / 0.985
* B M1 0.534 / 0.358 / 0.715 / 0.452  and  1.132 / 0.499 / 0.963 / 0.631
* SD M0 1.675 / 0.657 / 0.819 / 0.484  and  2.436 / 1.016 / 1.071 / 1.131
* SD M1 0.715 / 0.264 / 0.456 / 0.280  and  1.218 / 0.392 / 0.468 / 0.492
* ED M1 0.715 / 0.264 / 0.456 / 0.280  and  1.218 / 0.392 / 0.468 / 0.492
* PD M1 0.722 / 0.273 / 0.420 / 0.267  and  1.225 / 0.399 / 0.447 / 0.492

The pattern that matters: **B/M1 wins on B's own metric (0.534 against 0.715) and loses on every
cross-objective measure**, including the zero-weight diagonal holdout by 40 percent on the Left and 22
percent on the Right. Judging a map by the residual its own objective defines would invert the ranking.
One honest exception: for **M0 on the Right camera the new objectives are WORSE on the diagonal
holdout** (1.13 against B's 0.985), so the unique-point and quadrature change is not uniformly
beneficial when the model is the more misspecified one.

eta is sharply identified under every objective: dLoss at eta = 0 is 668 (B), 92.3 (SD), 92.4 (ED) and
114.4 (PD) on the Left, and 3043, 193.0, 193.4 and 208.8 on the Right, with a single symmetric well and
the free optimum interior. Fitted eta agrees across objectives to about 1e-4: +0.00809 to +0.00823
(Left), +0.01011 to +0.01088 (Right).

Projected conditioning after the nuisance line or homography directions are removed is comparable
across objectives: 1.9e5 to 2.8e5 for B, 3.3e5 to 3.5e5 for SD and ED, 3.0e5 to 3.3e5 for PD. The new
objectives are not better conditioned; they are differently weighted.

Runtime per fit: B 0.14 to 0.23 s, SD 1.9 to 38 s, ED 5.4 to 93 s, **PD 198 to 214 s and still hitting
its iteration cap**. PD's convergence is the outstanding practical problem; it was warm-started from ED
because starting from B left it moving after 3000 evaluations.

### Capture agreement on the Left camera

The shared map does form a visible compromise but a mild one. Per-capture raw-line residual RMS is
0.729 and 0.616 px for SD/M0 and 0.315 and 0.233 px for SD/M1, so the 137-observation capture is
consistently about 30 percent worse than the 261-observation one. Diagonal holdout per capture is much
closer, 0.263 against 0.288 px for SD/M1. Nothing here indicates a capture-specific distortion is being
smuggled into a shared map.

### Not established by this round

No known-length or point-cloud validation was run, no refraction pipeline was involved, and no
objective or model is promoted. The plumbline target is a separate planar target from the two-plane 3D
frame, and calibration-frame refraction is deliberately absent from all four objectives. Sigma_i = I
throughout; no detector-based covariance.

## Production-faithful downstream validation of the exact-PD fits (2026-07-29, same frozen document)

Reproduce with `~/.venvs/vidsync/bin/python tools/pooltest/fisheye_pd_downstream.py`. Runs in 1.3 s.
Six paired Left/Right candidates: the stored parameters as a historical anchor, B/M0, B/M1, PD-D/M0,
PD-D/M1, PD-U/M1. Every candidate, the anchor included, rebuilds the **entire** downstream calibration
from the raw node clicks through the parity oracle: front homography, four-iteration refracted back
nodes, back homography, and camera position recomputed on every refraction iteration. No stored
homography, camera position, or apparent back-node position is reused anywhere.

### The path was verified before any model was compared

Measurement sightlines really do use the eta-aware map: `fisheye_knownlength_analysis.py:84`
monkeypatches `parity.undistort` to `nodes.undistort13`, and zeroing eta moves a test sightline by
0.707 mm, so eta propagates into measurement geometry rather than only into calibration. Without that
patch `parity.undistort` (parity.py:60) silently drops eta, which would corrupt every M1 result — worth
knowing, because the patch is a module-level side effect of import.

`nodes.undistort13`, `lattice.U` and `objectives.u_kernel` agree to 5.7e-13 px over 400 random pixels on
three candidates, and `oracle.cpp:58-73` is the same conjugated expression term for term. M1 at eta = 0
reduces to M0 through the full rebuild **exactly**: camera position and front homography both differ by
0.000e+00.

Production does refine triangulation on this document — `ZUSEITERATIVETRIANGULATION = 1`, so
`VSPoint.m:147-215` runs GSL `nmsimplex2` on summed squared reprojection error from the linear CPA seed,
simplex size tolerance 1e-6, cap 500. The harness minimizes the same cost from the same seed with
scipy `lm` at 1e-15. No refinement is added that production does not perform. Refraction: 4 outer
iterations, per-node root solve tolerance 1e-7 (worst observed residual 9.96e-08, zero status failures),
camera drift falling 1.98 mm then 1.6e-2 then 1.4e-4 mm across iterations.

### Measurement inventory, verified from the file

Conventional: **42** two-point measurements, 13 at 100 mm, 4 at 196, 13 at 300, 6 at 500, 6 at 1000 —
matching expectation exactly, across 4 placements.

Clouds: **65 points and 504 within-cloud pairs**, not the 63 and 471 previously quoted. Cloud A 18,
B 16, C 13, D 18; zero loader exclusions; all 65 clicked in both cameras with unique note coordinates.
471 pairs is exactly Cloud D at 16 points, so two Cloud D points were added since that count was taken.
The replication unit is the placement: 4 conventional + 4 cloud, never 504.

### Conventional two-point results (MAE / RMSE / p90 / signed bias, mm)

| candidate | MAE | RMSE | p90 | max | bias |
|---|---|---|---|---|---|
| stored | 4.943 | 7.199 | 12.428 | 22.223 | +0.721 |
| B/M0 | 5.005 | 8.042 | 16.001 | 28.275 | +2.100 |
| B/M1 | 4.186 | 6.382 | 11.454 | 23.341 | +1.416 |
| PD-D/M0 | 4.119 | 5.914 | 9.107 | 19.849 | +0.349 |
| PD-D/M1 | **3.915** | **5.730** | 8.622 | 19.714 | +0.602 |
| PD-U/M1 | 3.907 | 5.759 | 8.521 | 19.924 | +0.683 |

### Cloud shape, rigid alignment with NO fitted scale (primary measure, mm)

Mean rigid RMS over the four clouds: stored 8.837, B/M0 9.074, B/M1 7.360, PD-D/M0 7.226,
PD-D/M1 **6.944**, PD-U/M1 6.941. Cloud D carries most of the movement, 12.016 under B/M0 to 6.480
under PD-D/M1. Fitted similarity scales, reported for diagnosis only and never substituted for the
no-scale fit, fall from 1.0285 to 1.0139 on Cloud D and from 1.0125 to 1.0048 on Cloud A, so part of
the legacy error was a genuine global scale inflation of up to 2.8 percent.

In-plane handedness of the note coordinates is **unidentifiable, not ambiguous**: a 2-D mirror of
coordinates embedded at z = 0 is itself a proper 3-D rotation about the in-plane axis, so both
conventions give identical residuals (agreement to 0.00e+00 mm on every cloud). No reflection is being
admitted to lower a residual.

### Paired contrasts, conventional and cloud kept separate

Mean change in absolute error, negative meaning improvement:

| contrast | conventional | improved | cloud pairs | all 4 clouds agree |
|---|---|---|---|---|
| B/M1 − B/M0 (eta, legacy) | −0.818 | 28/42 | −1.602 | yes |
| PD-D/M1 − PD-D/M0 (eta, projective) | −0.205 | 26/42 | −0.255 | no |
| PD-D/M0 − B/M0 (objective at M0) | −0.886 | 28/42 | −1.656 | yes |
| PD-D/M1 − B/M1 (objective at M1) | −0.272 | 28/42 | −0.309 | no |
| PD-U/M1 − PD-D/M1 (weighting) | −0.008 | 21/42 | −0.013 | no |
| PD-D/M1 − stored | −1.029 | 32/42 | −1.867 | yes |

### Upper tails, fixed baseline

The worst 10 and 20 percent under B/M0 are identified once and every candidate measured on those same
measurements. Conventional worst 10 percent: baseline 20.988 mm, PD-D/M1 12.644, PD-D/M0 12.701,
B/M1 15.703. Cloud pairs worst 10 percent: baseline 27.657, PD-D/M1 16.192, B/M1 19.466. Both changes
repair the tails rather than trading the tail for the median.

### Where the improvement sits, and the confounding

Prespecified strata from baseline geometry only. Conventional MAE at the top image-radius quartile falls
from 9.352 (B/M0) to 6.082 (PD-D/M1); nearest-screen-edge quartile 5.307 to 3.303; top camera-distance
quartile 9.209 to 7.782. Cloud pairs at the top radius quartile fall 11.225 to 5.909 and at the closest
edge quartile 12.384 to 6.004. So the gain is concentrated in peripheral and edge-proximate geometry,
which is where a distortion-model change should act.

**The covariates are badly confounded in this document and the strata cannot separate them.** Baseline
Spearman among conventional covariates: true length against camera distance +0.507, against
outside-calibration-hull +0.524; image radius against screen edge −0.661. For cloud pairs camera
distance against image radius is −0.853 and radius against edge −0.876. Continuous |error| trends
against true length are the strongest single association (+0.46 to +0.62 across candidates) and grow
slightly under PD, so length-dependent error is not removed.

### Geometric decomposition

Median endpoint movement, PD-D/M1 against B/M1: common-mode 0.602 mm, differential 1.142, of which
along-object 0.257 and perpendicular 0.792 mm. Common-mode cancels from a length and only the
along-object differential changes a scalar length to first order, which is why 3-D positions move about
1 mm while lengths change by a few tenths. Cloud shape change is largely rigid-plus-scale: for Cloud D,
total move 2.004 mm falls to 1.637 after removing a rigid map, 1.133 after similarity and 0.714 after a
full affine, so roughly two thirds of the change is gauge and scale rather than non-affine warp.

### Calibration residual quality does track downstream accuracy, weakly evidenced

Across the six candidates, front-node RMS against conventional MAE has Spearman +0.968 and against
cloud rigid RMS +0.957, while cameraMeanPLD is nearly uninformative (+0.247 and +0.230). Six candidates
is far too few for this to be more than suggestive, but the direction is that front-node residual is the
better of the two available proxies. Every candidate passed the full-domain admissibility and
round-trip audit; worst frame round trip 4.55e-13 px, minimum Jacobian determinant 0.9992.

### Not established by this round

One document, one lens, four conventional and four cloud placements. No refraction-setting sensitivity,
no other documents, no non-lattice line objective was tested downstream at all, and no production
default is changed. PD-U versus PD-D is measurement-neutral here (0.008 mm on 42 measurements), so the
weighting choice is not resolved by metric evidence and rests on the argument about what the estimand
should be.

## Cross-document objective comparison and harness hardening (2026-07-29)

Reproduce with `~/.venvs/vidsync/bin/python tools/pooltest/downstream_parity.py` (3 s) and
`~/.venvs/vidsync/bin/python tools/pooltest/xdoc_objectives.py` (222 s).

### The eta monkeypatch is gone, and the injection path reproduces it

`downstream.py` now carries the distortion candidate as an explicit `DistortionMap` bound to its camera
at calibration-build time. Against the old path, which depended on
`fisheye_knownlength_analysis.py:84` reassigning `parity.undistort`, the deterministic stages agree to
**9.1e-13** (undistorted pixels, both induced homography mappings, camera positions all at 0.000e+00 for
the homographies and camera) and the iterative stage to **4.3e-6 mm** in 3-D points and lengths, which is
LM convergence noise present on both paths. M1 at eta = 0 reproduces the explicit 13-parameter map at
0.000e+00 through the whole rebuild, and nonzero eta moves undistorted coordinates by 1.78 px, the camera
by 0.43 mm and a sightline by 0.40 mm, so eta demonstrably reaches measurement geometry.

A design error found and fixed while doing this: the map must travel **with the camera**, not as a
separate argument. Passing one camera's map to undistort both cameras' clicks moved reconstructed points
by up to **48 mm** — larger than any model contrast being studied.

### Production Nelder-Mead and the harness LM solve agree to 1e-5 mm

`tri_oracle.cpp` replays `VSPoint.m:147-215` exactly: GSL `nmsimplex2`, CPA seed, initial step sizes 1,
simplex size tolerance 1e-6, 500-iteration cap, on the same reprojection cost. Over 149 points x 6
candidates on the 2015 document: zero failures, median 100-103 iterations (max 159), median 3-D
difference **6.5e-7 mm**, p95 2.5e-6, **worst 9.6e-6 mm**, worst length difference **2.9e-6 mm**. LM
reached the lower cost on 434 of 894 point-candidate pairs and NM on 12, so LM does converge tighter, but
the difference is 5 orders of magnitude below the 0.1-1 mm model contrasts. **LM is retained for offline
work with production-NM parity documented.**

### No document stores lens or focal length

`ZVSVIDEOCLIP` carries only `ZCLIPNAME`, `ZFILENAME`, `ZSYNCOFFSET`, `ZWINDOWFRAME`. The "13 mm" label on
`2015-06-22-1 Clearwater.vsd` appears only in harness script comments and **cannot be verified from the
file**. Distortion regime is therefore characterised empirically, as the stored map's displacement of the
far image corner: pool test **35-47 px**, `2015-06-22-1` **456-556 px**, `2015-09-04-1` **1333-1452 px**.

### `2015-06-22-1 Clearwater` has no valid lattice

Both cameras: one component covering 100% of unique observations, but **32 (Left) and 36 (Right) index
contradictions after propagation and zero reliably indexed observations**, so the indexed subset is empty
and exact PD-D is inadmissible. PD-D was **not** fitted there; SD-D fell back to the unique-point set
(340 Left / 365 Right observations, `require_indexed=False`, `min_inc=1`). This is a real instance of
"expected lattice fails validation" on real data.

### Pool test (mild distortion, 1010 measurements, 63 timecode clusters)

Cal A in the 2016 XML is the **same node set as the stored placement, merely reordered** (verified
order-insensitively), so it is not an independent placement and reproduces it exactly. Cal B is genuinely
different: 20 front nodes against 15.

Cluster-level mean change in absolute error, mm, negative meaning improvement, with a 95% CI over 63
clusters:

| contrast | Cal A / stored nodes | Cal B |
|---|---|---|
| B/M1 − B/M0 | +0.133 [−0.001, +0.268] | +0.025 [−0.007, +0.057] |
| PD-D/M0 − B/M0 | +0.360 [−0.026, +0.745] | **−0.033 [−0.085, +0.019]** |
| PD-D/M1 − PD-D/M0 | +0.114 [−0.019, +0.248] | +0.015 [−0.012, +0.041] |
| PD-D/M1 − B/M1 | +0.341 [−0.048, +0.730] | **−0.044 [−0.098, +0.010]** |
| SD-D/M0 − B/M0 | +0.021 [−0.010, +0.053] | +0.013 [−0.002, +0.028] |
| SD-D/M1 − SD-D/M0 | +0.124 [−0.001, +0.249] | +0.020 [−0.008, +0.049] |

MAE under Cal B: B/M0 0.669, **PD-D/M0 0.654 (best)**, PD-D/M1 0.658, SD-D/M0 0.676, B/M1 0.680,
SD-D/M1 0.685, stored 0.750. PD-D also gives the best fixed-baseline tails under Cal B: worst decile
2.737 mm against B/M0's 3.030. Under the stored placement PD-D is instead the **worst** candidate
(MAE 1.056), so the objective's benefit on mild distortion is contingent on node placement.

**eta remains harmful under mild distortion under every objective**, and PD-D reduces but does not
remove the harm: +0.025 under B, +0.015 under PD-D, +0.020 under SD-D on Cal B. Fitted eta on the pool
test is large and inconsistent between cameras (Left +0.0347 B, +0.0242 PD-D; Right +0.0050 B,
−0.0067 PD-D) — larger than on the 8 mm fisheye, where it is stable at +0.008 to +0.011 across all three
objectives. So eta magnitude does **not** track distortion strength; on mild distortion it is absorbing
something else.

### 8 mm fisheye (42 measurements, 4 clusters)

MAE: **SD-D/M1 3.860**, PD-D/M1 3.915, PD-D/M0 4.119, SD-D/M0 4.164, B/M1 4.187, stored 4.943,
B/M0 5.005. Cluster means: PD-D/M0 − B/M0 **−1.222 [−2.308, −0.136]**, PD-D/M1 − B/M1
**−0.384 [−0.733, −0.036]**, SD-D/M0 − B/M0 −1.092 [−2.034, −0.149]; PD-D/M1 − PD-D/M0
−0.049 [−0.252, +0.153] and SD-D/M1 − PD-D/M1 −0.016 [−0.064, +0.032], both indistinguishable from zero.
With only 4 clusters these intervals are wide. **SD-D and PD-D are statistically indistinguishable here**,
and both clearly beat legacy B.

### `2015-06-22-1` intermediate document (57 measurements, 5 clusters)

No PD-D possible. MAE: stored 3.167, SD-D/M0 3.378, B/M0 3.434, SD-D/M1 3.445, B/M1 3.480. SD-D/M0 − B/M0
−0.046 [−0.133, +0.042]; eta harmful again, SD-D/M1 − SD-D/M0 **+0.051 [+0.006, +0.097]**, the only
interval in this round excluding zero. The rebuilt stored anchor beats every refit here, which is worth
noting rather than explaining away.

### What this does and does not establish

PD-D beats legacy B convincingly on high distortion, marginally and placement-dependently on mild
distortion, and is untestable on the one intermediate document because its lattice is invalid. SD-D
tracks B closely on mild distortion and tracks PD-D closely on high distortion, so as a fallback it is
adequate but is not independently validated on genuinely non-lattice data — all three documents
originated from lattices, and SD-D was given the same indexed subset as PD-D wherever the lattice was
valid. SD-D/M1 hit the 1200-nfev cap on several fits (about 10-13 s each) and its reported optimum is
therefore not fully converged. No production default is changed.

---

## 2026-07-29 — Independent audit corrections (supersedes parts of the section above)

An independent ChatGPT audit of the offline harness found two code-integrity defects and one reporting
defect. The numbers immediately above were produced *before* those defects were fixed. Nothing above has
been edited, so its provenance stays visible; this section states which of its claims no longer hold and
what replaces them. Every figure below comes from
`analysis-output/xdoc_objectives_full.json` (`complete: true`, document scope `full`, runtime 211 s,
git `3dd84b5` with a dirty tree), regenerated after the fixes. No model was promoted, no production
default was touched, and no broader model comparison was rerun.

### The three defects

**1. Camera identity was documented but never enforced.** `downstream.py` bound each distortion map to
a camera by convention and said so in a docstring, but nothing checked it. The audit deliberately swapped
the Left and Right maps on `2015-09-04-1 Clearwater.vsd`; the run completed with no error, no warning and
no diagnostic, and moved conventional MAE from 3.9146 mm to 4.2777 mm. A wrong-camera result was
indistinguishable from a real one. Fixed: a map now carries a `CameraIdentity` of
`(document SHA-256, ZVSCALIBRATION.Z_PK)` and `build_calibration` refuses any map not bound to the camera
it is calibrating. Clip labels are deliberately excluded from the identity, because "Left Camera" is
`Z_PK 2` on the pool test but `Z_PK 1` on both 2015 documents — the label-to-key mapping is *inverted*
between documents, so neither the label nor the key identifies a camera on its own.

**2. A partial run destroyed the full cross-document artifact.** A `--docs pool` run wrote
`analysis-output/xdoc_objectives.json`, the same path the three-document run uses, replacing the complete
artifact with a pool-only one that carried no indication of being partial. Any summary quoting that file
between then and now was reading one document's worth of a three-document claim. Fixed: the filename now
carries the document scope (`xdoc_objectives_full.json` versus `xdoc_objectives_pool.json`), writes are
atomic, and `complete` is derived from whether every requested document and candidate actually finished.
The stale pool-only file has been left in place as historical evidence and is described in
`analysis-output/README-STALE-ARTIFACT.md`.

**3. Capped SD-D fits entered the headline tables.** `hit_nfev_cap` was recorded in the diagnostics and
then ignored by every table. SciPy's `status = 0` means "maximum number of function evaluations reached";
it is not a convergence code. Fixed: `fitvalidity.py` is now the single authority, invalid fits are
excluded from every reported number by default, and their cells read `invalid_fit`.

### Corrections to the 8 mm fisheye section

- **"MAE: SD-D/M1 3.860" is withdrawn as a ranking.** That fit reached its 1200-evaluation ceiling with
  status 0 on the Right camera. Its regenerated value is **3.8596 mm**, retained as a diagnostic and
  **invalid for ranking**.
- **Do not state that PD-D/M1 is uniquely best on the 2015 conventional measurements.** The regenerated
  values are:

  | candidate | conventional MAE, mm (n = 42) | status |
  |---|---|---|
  | SD-D/M1 | 3.8596 | **invalid** — fit capped at 1200 nfev, status 0 |
  | PD-U/M1 | 3.9066 | valid |
  | PD-D/M1 | 3.9146 | valid |

- **PD-U/M1 and PD-D/M1 are practically tied at the observed scale.** They differ by 0.008 mm on 42
  measurements in 4 clusters, against a cluster-level standard error of roughly 0.1 mm. Nothing in this
  corpus separates them.
- **PD-D remains preferred only provisionally, and on its area-uniform estimand — not on metric
  superiority.** The metric evidence does not distinguish it from PD-U, and its advantage over legacy B
  is what is actually established here.
- **The eta improvement under PD-D is not established.** The observed change was **−0.2047 mm** in mean
  paired |error|, but the cluster-level interval over the 4 available clusters was
  **[−0.2522, +0.1534]**, which crosses zero. With 4 clusters this is not a detection.
- Every paired contrast involving SD-D on this document is now **unavailable** rather than reported:
  `SD-D/M0 − B/M0`, `SD-D/M1 − SD-D/M0` and `SD-D/M1 − PD-D/M1`. A contrast whose member did not
  converge is not a number.

### Corrections to the pool test and intermediate document sections

- Pool test: `SD-D/M0` (both cameras) and `SD-D/M1` (Right camera) were capped at 1200 nfev with
  status 0. **The SD-D rows in the pool tables are withdrawn**, including `SD-D/M0 0.676` and
  `SD-D/M1 0.685` under Cal B and the `SD-D/M0 − B/M0` and `SD-D/M1 − SD-D/M0` contrasts in both
  placement columns. The valid regenerated picture is unchanged for the other candidates: best valid
  fitted candidate is **B/M0 at 0.9540 mm** under the stored placement and **PD-D/M0 at 0.6535 mm**
  under Cal B.
- `2015-06-22-1` intermediate document: `SD-D/M0` and `SD-D/M1` (Left camera) and `SD-D/M1` (Right
  camera) were capped. **The whole SD-D line here is withdrawn**, which removes `SD-D/M0 3.378`,
  `SD-D/M1 3.445`, the `SD-D/M0 − B/M0` contrast, and — importantly — the claim that
  `SD-D/M1 − SD-D/M0` was **+0.051 [+0.006, +0.097]**, "the only interval in this round excluding
  zero". That interval was computed from two fits neither of which converged, and it is retracted. The
  valid regenerated picture: stored 3.1669, **B/M0 3.4341 (best valid fitted)**, B/M1 3.4799; PD-D is
  correctly recorded as *not fitted* because the lattice does not validate.
- **Every SD-D downstream conclusion that rests on a capped fit is now marked invalid or provisional.**
  Across all three documents, eight candidate-camera fits were capped: pool Left SD-D/M0; pool Right
  SD-D/M0 and SD-D/M1; 2015-09-04-1 Right SD-D/M0 and SD-D/M1; 2015-06-22-1 Left SD-D/M0 and SD-D/M1;
  2015-06-22-1 Right SD-D/M1. Convergence was **not** attempted in this round.
- **The conclusion that SD-D is not production-ready stands, and is strengthened.** It was previously
  qualified by "its reported optimum is therefore not fully converged"; the correct statement is that on
  this corpus SD-D failed to converge within its budget on at least one camera of every one of the three
  documents, so it currently has no valid downstream result on any of them.

### What did not change

The pool test remains the negative control on which fitted eta is harmful, and PD-D still beats legacy B
convincingly on high distortion, marginally and placement-dependently on mild distortion, and remains
untestable on the intermediate document. The camera-binding fix does not alter any correctly-bound
result: `downstream_parity.py` reproduces the previous injection parity at 9.1e-13 px on the
deterministic stages and 4.3e-6 mm on the iterative stage, and eta-aware results are now proven
bit-identical across six import orders.

### Regression tests added

| file | covers |
|---|---|
| `test_binding.py` | 47 checks: correct Left/Right binding, the audit's exact swap, cross-document maps, M0 and M1, stored historical maps, eta = 0 equivalence through the full rebuild, nonzero-eta sightline propagation, and refusal to degrade a map to a 13-vector |
| `test_artifacts.py` | 48 checks: full versus pool-only naming, manifest completeness, simulated interruption leaving the prior artifact byte-identical, failed documents producing `complete: false`, filename/manifest scope agreement, and stale candidate records not surviving |
| `test_fitvalidity.py` | 49 checks: synthetic valid and capped records, every failure mode, rankings and contrasts ignoring invalid candidates, and a replay of the real recorded fit statuses |
| `test_import_order.py` | 40 checks: bit-identical eta-aware output under six import orders, including importing the historical monkeypatching module first |

### `plumb_oracle` GSL 2.6 provenance: RESOLVED

Recorded in full in `tools/pooltest/ORACLE_PROVENANCE.md`. The build comment was not self-verifying, so
identity was established from the object code: GSL restructured `multimin/simplex2.c` between 2.6 and
2.7.1, and the four symbols `_compute_center`, `_compute_size`, `_contract_by_best` and `_ran_unif`
exist only in 2.7.1. `nm -arch arm64 plumb_oracle` contains none of them, contains `_update_point` and
`___sincos_stret` as 2.6 does, and links no `libgsl` at all — consistent with static linking against the
vendored `gsl-2.6-universal/libgsl.a` that `project.pbxproj` also links into the app. So exact production
plumbline-trajectory parity is **resolved**, and the legacy-B conclusions that depend on it are supported.

**New finding, previously unrecorded:** `tri_oracle` and `oracle` link `/usr/local/lib/libgsl.27.dylib`,
i.e. **GSL 2.7.1**, not the bundled 2.6. By this document's own stated criterion that GSL version is
load-bearing for `nmsimplex2` trajectories, the triangulation replay is therefore *not* linked the way
`plumb_oracle` is. This does not overturn the measured NM-versus-LM agreement (worst 3D difference
9.6e-6 mm over 149 points and 6 candidates, four orders of magnitude below the 0.1-1 mm contrasts), but
that agreement is with 2.7.1's `nmsimplex2`. Metric agreement with production triangulation is
established; bit-level trajectory identity is not. Do not describe `/usr/local` GSL as
production-identical merely because it runs.
