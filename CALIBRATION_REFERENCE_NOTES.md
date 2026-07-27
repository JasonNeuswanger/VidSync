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

### How to use it

Judge any change on bias and standard deviation per object, split by `ZNEARESTCAMERADISTANCE`
the way Table 1 splits by range. Report static-target accuracy separately from anything
involving moving subjects: synchronization error and motion blur do not appear here at all.

To compare two versions of the mathematics fairly, both must be applied to the same clicked
screen coordinates rather than to the stored 3D results, since the stored coordinates only
change when points are recalculated. The clicks are preserved in `ZVSSCREENPOINT` (`Z_ENT` 12,
`VSEventScreenPoint`), each tied to the video clip and calibration it belongs to.
