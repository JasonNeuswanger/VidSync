# VidSync export format: plan of record

This records the multi-phase plan for VidSync's data exports, why each decision was made, and
what is deliberately not being done. It exists because the first two phases were planned in a
chat session and implemented from a transcript, which is not a durable place for a plan that
spans several commits.

Written 2026-07-31, covering work through the JSON mirror.

## The compatibility rule that governs everything here

VidSync's XML and CSV exports have been parsed by other people's scripts for years. Those
scripts are not accessible from here and cannot be inventoried, so the only safe assumption is
that every attribute, every column, every element name and every value's rendering is load
bearing for somebody.

The rule this plan follows is therefore: **append only**. Nothing existing is renamed, removed,
reordered, or re-rendered. New attributes go after all existing attributes on their element; new
child elements go after all existing children; new columns go after all existing columns. An
export produced after these changes must differ from one produced before them only by insertions.

Two consumer shapes were examined while writing this, as evidence rather than as an inventory:

- The Drift Model harness (`PythonDataAnalysis/VideoDataProcessing/DataVideo.py` and friends)
  parses with `xml.etree.ElementTree` and reaches everything by XPath with attribute predicates
  and tag names — `findall("./objects/object[@type='Dolly Varden']")`,
  `videoClip[@name='X']/calibration`, `attemptxml.findall("./point")` — reading attributes
  individually by name. Nothing iterates the attribute set, counts attributes, or indexes
  children positionally. Appended attributes and appended named children are invisible to it.
  Two of its queries use `findall(".//point")`, a *descendant* search, which is why no new
  element anywhere in this format may be named `point`.
- The offline research harness in `tools/pooltest/` parses some of the same files with regular
  expressions. Two scripts match `<videoClip name="([^"]+)">`, which requires `>` immediately
  after the name attribute and therefore breaks on any new `videoClip` attribute. They are fixed
  in the same commit that adds those attributes. Five other scripts match the prefix
  `<videoClip name="X"` without the closing bracket and are unaffected, which is why `name`
  remains the first attribute on that element.

The general lesson: a consumer that reads by name survives appends; a consumer that reads by
position or by exact-shape regex may not. Keeping existing names, order and rendering fixed is
what makes the first group safe, and keeping `name` first on `videoClip` is a cheap concession
to the second.

## Phase 1 and 2 — correctness and provenance (done, commit 3700c19)

Phase 1 fixed things that were already producing wrong output: unescaped spreadsheet fields, a
header that declared thirteen columns while the rows emitted twelve, unmeasured values printing
as `0.000000` instead of empty, locale-dependent decimal separators, nil project fields reaching
`NSXMLNode`, a literal `{{(null),...}}` for an uncalibrated clip's matrices, silent no-ops on an
empty export, and undefined row order.

Phase 2 added provenance: `appVersionCreated`, `appVersionLastSaved` and `dateLastExported` on
`VSProject`, and `exportFormatVersion`, `exportDate` and `appVersion` in every export.
`VSExportFormatVersion` lives in `DataExport.m` and is bumped on any structural change.

## Phase 3 — additive XML content

All additions. No existing attribute, element, name or value changes.

**`videoClip`** gains `fileName`, `syncOffset`, `syncIsLocked`, `isMasterClip`, `muted`,
`timeScale`, `frameRate`, `clipLength`, `clipWidth`, `clipHeight`, appended after `name`. Screen
coordinates cannot be interpreted without the clip resolution and per-clip times cannot be
related to master times without the sync offset, so this is the largest single gain in
interpretability available. The last five read through `windowController`, which returns zero or
nil when a clip's window has not loaded or its video file is missing; each is guarded and emits
an empty string rather than `0` in that case. That is a known property of the format: a clip
whose video is missing exports blank timing and resolution.

**`calibration`** gains `axisHorizontal`, `axisVertical`, `axisFrontToBack`, `planeCoordFront`,
`planeCoordBack`, `cameraMeanPLD`, `shouldCorrectRefraction`, `frontQuadratSurfaceThickness`,
`frontQuadratSurfaceRefractiveIndex`, `mediumRefractiveIndex`, `frontIsCalibrated` and
`backIsCalibrated`. `cameraMeanPLD` was the one residual-family value omitted, which read as an
oversight rather than a decision. The refraction settings materially change every exported
coordinate and were previously invisible in the file.

**Quadrat node lists** become `<quadratNodesFront>` and `<quadratNodesBack>` child elements
carrying their text, appended after the existing calibration children. They cannot be attributes:
the lists are newline-delimited `h, v` pairs, and XML attribute-value normalization converts
newlines to spaces, so every parser would silently flatten the line structure. This is the
physical quadrat geometry the entire fit rests on.

**`point`** gains `numViews`, the count of `calibratedScreenPoints`. It separates a two-camera
from a four-camera solve and identifies single-view points, which the export previously left
ambiguous.

**The project root** gains `useIterativeTriangulation`. On the linear path the coordinates are
the closest-point-of-approach solution and `reprojectionErrorNorm` is deliberately nil; on the
iterative path they minimize pixel error. Without this attribute an empty `reprojectionErrorNorm`
is ambiguous between "linear method" and "too few views."

**`screenpoint`** (the `VSEventScreenPoint` one) gains `reprojectedX`, `reprojectedY` and
`residualPixels`, from `reprojectedScreenPoint:NO` against `undistortedCoords`, guarded on the
parent point having 3D coordinates and the clip being calibrated, empty otherwise. A per-camera
pixel residual is exactly the diagnostic wanted when auditing a suspect measurement, and the
machinery already existed.

**`distortionLine`** gains `lambda`. **Calibration points** gain `index`.

**`event`** gains a `<connectingLines>` wrapper, appended after the existing `point` and
`objectChildOfEvent` children, holding one `connectingLine` per segment with `fromPointIndex`,
`toPointIndex`, both endpoint timecodes, `length` and `speed`. A wrapper rather than bare
children so a positional consumer sees one new child at the end; named `connectingLine` rather
than anything containing `point` so the `.//point` descendant searches in the Drift Model harness
cannot absorb it.

This XML path is **ungated**. The existing clipboard export gates connecting lines on
`connectingLineLengthLabeled`, which is a drawing preference deciding what data you get — the
wrong coupling. It is left gated anyway, because ungating it would add rows to output people
already paste into spreadsheets. The asymmetry is deliberate: new output is ungated, existing
output keeps its existing behaviour.

`VSExportFormatVersion` goes to 2.

**Deferred.** `apparentWorldHcoord` and `apparentWorldVcoord` on calibration points are
`@synthesize`, not `@dynamic` — in-memory only, so they are nil on a freshly opened document
until a recompute runs in that session, and would export empty in the common case. Exporting
them properly means persisting them first, which is a larger change than this.

**Not fixed in code.** An event shared by several objects is still emitted in full under each
owning object, so a consumer that flattens the objects tree double-counts it. Event index is
project-unique and is the dedupe key. This is documented in `DataExport.m` and in the help
rather than restructured, because restructuring would move existing elements.

## Phase 4 — appended CSV columns

The original plan proposed three new CSV files (connecting lines, screen points, calibrations).
**Dropped.** People who need those data can use the XML or the JSON. The spreadsheet exports stay
a single table of 3D points.

Four columns are appended to the points CSV and its clipboard twin, **after** the conditional
`Screen Coordinates` column, so that no existing column ever changes position regardless of how
`includeScreenCoordsInExports` is set:

- `Event Index` — project-unique, and the dedupe key for the multi-object duplication above.
  Previously recoverable only by parsing it back out of the composite `Event` string.
- `Event Type` and `Event Name` — the other two components of that composite, separated.
- `Object Indices` — semicolon-joined indices of the owning objects. The existing `Object(s)`
  column joins full human-readable descriptions with `", "` and is quoted; this is the
  machine-readable key that survives multi-object events without anyone parsing prose.

Object type and name are deliberately *not* split into columns. An event can own several objects,
so those fields are inherently multi-valued and would be either lossy or need their own delimiter
convention inside a cell. The index list plus the existing composite covers the need.

A `Views` column (`numViews`) was considered and **rejected**: it invites more confusion than it
resolves in a flat file, and anyone who needs it can compute it from the XML.

Two project-level constants go on the provenance line rather than becoming columns, since they
are identical in every row: `useIterativeTriangulation` and `includeScreenCoordsInExports`. That
line is already free-form `key=value` and already not a data record, so this costs nothing
structurally while telling a reader what the coordinates in the file actually mean.

The connecting-lines clipboard export is untouched.

## Phase 5 — JSON mirror

The requirement is that the JSON and the XML cannot drift. That is a structural property, not a
discipline problem, so it is achieved structurally: **there is one generator and two renderers.**
The JSON is derived mechanically from the same `NSXMLDocument` the XML export writes. There is no
`representationAsJSON` on any model class, and adding an attribute to the XML adds it to the JSON
with no second edit.

The converter has no per-element knowledge. Its rules:

1. An element becomes a JSON object. The document becomes `{"project": {...}}`, so the root tag
   is not lost.
2. Attributes become keys of that object.
3. Children are grouped by tag name into **arrays — always arrays, even for a single child**.
   This is the rule that does the real work: no consumer ever has to handle "an object, or a list
   of objects, depending on the data," which is the classic XML-to-JSON trap.
4. Text content becomes a `text` key. Only the quadrat node lists use this today.
5. Values are typed through a registry keyed by attribute name: number, boolean, `matrix3x3`
   (parsed from the `{{a,b,c},{...}}` string into a nested array of numbers), or string. An empty
   string becomes `null`, so "not computed" is explicit rather than an empty string.
6. An attribute not in the registry falls back to string and logs. New XML attributes therefore
   appear in the JSON automatically — typed if registered, string if not — and can never be
   silently missing.
7. An attribute whose name collides with a child tag name on the same element would be ambiguous.
   None do today; the converter logs rather than silently overwriting if one ever does.

Three consequences worth recording, because they retire concerns raised in the original audit:

- **The duplicate `screenpoint` element name stops mattering.** `VSEventScreenPoint` and
  `VSCalibrationPoint` both serialize to `screenpoint`, but they never appear as siblings — event
  screen points live under `point`, calibration ones under `frontCalibrationPoints` and
  `backCalibrationPoints` — so grouping by tag name keeps them in separate arrays. Their attribute
  sets union cleanly, with no name meaning two different types. No rename is needed, so no
  existing XML consumer is disturbed.
- **The heterogeneous unwrapped children under `videoClip` stop mattering.** One calibration and N
  annotations as bare siblings become `{"calibration": [...], "annotation": [...]}` automatically.
- **The inconsistent collection wrapping survives into the JSON**, as
  `{"objects": [{"object": [...]}]}`. This is kept faithful rather than heuristically flattened.
  "The JSON is exactly the XML" is worth more than tidiness, and any flattening rule is a special
  case that could misfire on a future element.

The registry is the one hand-maintained piece, so it is covered by a checker under `tools/` that
parses both files and asserts that every element and attribute in one is present in the other
with an equal value after string coercion. That is the mechanical guarantee that the mirror is a
mirror, and it is also where an unregistered attribute shows up.

**Delivery**: a separate "Export JSON file" button on the Export Data tab, beside the XML one,
wired to `exportJSONFile:`. Both actions build the tree through the same method, so the two files
have identical content whichever button is pressed.

## Explicitly deferred beyond this plan

Portraits and hint lines in the XML; entity ids; collection wrappers made consistent; structured
matrix children alongside the string attribute; renaming the duplicate `screenpoint` element. The
JSON design above removed the reason to do the last three. Separately and trivially, the export
file name uses colons in `HH:mm:ss`, which Finder renders as slashes.

## Verification

There are no automated tests for the export path, so acceptance is a before-and-after diff on a
real project — ideally one with multi-object events and a full calibration, not a toy.

- The points CSV and both clipboard outputs must be **byte-identical through phase 3**. After
  phase 4 they must be identical up through the last pre-existing column, with only appended
  fields after it.
- The XML diff must be **additions only**: inserted lines, and inserted attributes on existing
  lines. No removed lines, no changed values.
- The Drift Model harness re-run against a regenerated export must produce identical fish,
  foraging-attempt and tracer counts.
- The XML-versus-JSON checker must report no differences.

Those four criteria are the operational definition of "did not break backward compatibility."
