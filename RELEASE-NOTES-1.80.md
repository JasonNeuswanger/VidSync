# VidSync 1.80

## Headline changes

**Automatic plumbline detection, substantially rebuilt.** Detection of chessboard
plumblines is far more reliable: it recovers corners that blown-out highlights erase, grows
the lattice across gaps the detector missed, judges each corner against a curve fitted
through its whole line rather than in isolation, and resolves conflicts by consensus so one
bad edge costs one edge instead of derailing the grid. Seeding is about three times faster,
handles vertical video correctly, and no longer produces reversed line fragments.
Undistortion candidates are now scored for projective validity.

**Video export runs in the background, with a queue you can watch.** Captures no longer
freeze the program. Each export shows its own progress, more can be queued while earlier
ones run, and any of them can be cancelled. Closing a project with exports still running
asks first instead of quietly abandoning them. Exports with overlays burned in benefit
most — they used to lock the interface for the duration.

**Videos re-attach themselves when a project moves.** Opening a project whose video files
are missing now looks for files of the same name beside the project file and attaches them
automatically, reporting what it did. Moving, copying, or restoring a project folder no
longer means relinking every clip by hand.

**Data export overhauled.** A new JSON export sits alongside the XML. The XML now states
what its numbers mean and in what units. The points CSV carries the identifiers a script
needs, not just the ones a person reads. Exports record where they came from, and each
calibration now includes the camera's central sight line and angular field of view.

## Other changes

### Numbers that may change

A batch of correctness fixes in the calibration and triangulation math means some figures
will read differently than they did in 1.721. The new values are the right ones.

- **Mean remaining distortion per point now reads higher, and is correct.** Plumblines with
  fewer than three points are straight by definition and contribute nothing to the fit, but
  they were still counted in the denominator, which quietly flattered the reported residual.
  Only lines that can actually contribute are counted now.
- **Fitted distortion parameters may differ slightly.** The quantity being minimised is no
  longer divided by total line length, and a fit that stalled at the iteration limit used to
  be accepted as though it had converged, which also stopped the remaining starting guesses
  from being tried. Undistorted screen coordinates shift accordingly.
- **Refraction-corrected coordinates no longer go undefined in edge cases.** Angles very
  slightly outside the valid range for their inverse cosine produced undefined results, as
  could a square root of a marginally negative number; both are now clamped.
- **Triangulation reads its screen points in a fixed order.** The previous code re-derived
  the point list on every pass through the loop and depended on an ordering the system does
  not guarantee, which could mismatch sight lines to their points.
- Solving with fewer than two contributing lines returns nothing rather than the output of a
  singular matrix.

If you reopen an older project and want its stored values brought onto the current math, use
**Recalculate All Points**. This is also the fix for projects analysed across the 1.64
boundary years ago, whose stored reprojection errors can be larger than they should be by a
factor of about 1.4 for two-camera points.

### Measurement and calibration
- Hint lines are traced along the line rather than sorted by horizontal position, are
  rebuilt whenever a point is recalculated, and treat "unpaired" as a property of the point
  rather than of the clip. Rigs with several cameras were the most affected.
- Distortion correction rejects a solution lying past the fold in the model, which could
  previously produce nonsense in the far field.
- New 3-D calibrations are asked whether to correct for refraction rather than assuming it.
- Confirmation before the Example button overwrites frame coordinates.

### Export
- **.mov output has been retired. Every video export is now a clean .mp4.**
- **H.265 is selectable alongside H.264** — smaller files, at some cost in compatibility.
- Sound can be included or omitted in captured video.
- Rotation-flagged video (vertical phone footage, upside-down mounts) exports the right way
  up. It previously came out sideways and cropped.
- A failed export now says so instead of leaving a button stuck.
- Exported elements come out in a repeatable order, so two exports of an unchanged project
  can be compared directly.
- Line breaks in multi-line notes survive export.
- Screen point export no longer fails on a coordinate that was never computed.
- Connecting lines, and a distortion field that never existed, are no longer exported.

### Interface
- Buttons whose prerequisites aren't met are now greyed out instead of accepting the click
  and then explaining why it couldn't work.
- Windows tile themselves when a project's saved layout doesn't fit the current screen.
- Open projects no longer share each other's tab and filter selections.
- The project's clip list is sorted by name and opens scrolled to the top.
- Object and event types imported from a file offer conflict resolution instead of
  failing or duplicating.
- The video clip window can shrink to 15% of full size; below a certain width its controls
  hide so the window can follow the video down.
- The clip window shows the sync offset as a whole number of frames rather than a timecode.
- Read-only fields in the playback panel no longer draw focus rings.
- Colours that cannot be read back from an older file fall back to something visible
  instead of disappearing.

### Reliability
- VidSync now records a report when it crashes and offers to email it on the next launch,
  which makes problems far easier to diagnose.
- Several crashes and memory faults fixed, including a race in tracked-object updates, an
  image leak, unsafe file naming, and a division by zero on clips with no frame rate.

### Licensing
- VidSync's source remains under the MIT licence. Because the application links the GNU
  Scientific Library, the compiled program is distributed under the GPL v3; both licence
  texts and a full list of third-party components now ship with the source.
