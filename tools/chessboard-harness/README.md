# Chessboard detector harness

Runs `VSChessboardDetector.cpp` over a single still frame outside the application, printing
what each stage decided and optionally dumping the resulting plumblines.

It exists because the detector was previously only reachable by launching VidSync, opening a
document, and clicking a button, which meant changes to it could not be tested against real
footage before shipping. A change that looked well justified and was validated only against
plumblines already stored in a document turned out, when finally run against the frame those
plumblines came from, to be innocent of the failure it appeared to have caused — and the real
culprit, a wrong basis chosen during seeding, was visible in one line of the harness output.
Reproducing a detection in a second rather than a minute is the difference between guessing
and measuring.

## Building

    tools/chessboard-harness/build.sh

Links against the OpenCV framework vendored in `OpenCV/`, so no separate install is needed.
Not part of the Xcode project: it is a development tool, and adding it to the app target would
mean every VidSync build paid for it.

## Getting a frame

`grabframe.swift` pulls an exact frame from a video, matching what VidSync itself feeds the
detector — the frame at the playhead, not at the calibration timecode.

    swift tools/chessboard-harness/grabframe.swift "/path/to/clip.mp4" 4430.0 frame.png

The seconds argument is a decimal offset. A VidSync timecode of `0:01:13:54.0/30` means day 0,
01:13:54, plus 0/30 of a second, so 4434.0 s. The current playhead and the calibration
timecode are both stored in the document:

    sqlite3 "Project.vsd" "SELECT ZCURRENTTIMECODE, ZCALIBRATIONTIMECODE FROM ZVSPROJECT;"

## Running

    DYLD_FRAMEWORK_PATH=OpenCV tools/chessboard-harness/harness frame.png [out.csv]

Prints the corner count, the seed basis with the length of each vector and the angle between
them, the growth and refinement summaries, and a histogram of plumbline orientations in
15-degree bins. The histogram is the quickest way to see a bad basis: a correctly seeded board
gives two clusters about 90 degrees apart, while a basis locked onto the grid diagonals
scatters across 45 and 135 degrees.

With a second argument it also writes the plumblines as CSV columns
`calibration,line,index,x,y`, with y flipped to VidSync's bottom-left origin so the output can
be compared directly against points read out of a `.vsd` document.

## Comparing two versions of the detector

Build a second binary from a different revision of the detector and run both over the same
frame:

    git show <rev>:VSChessboardDetector.cpp > /tmp/other.cpp
    clang++ -std=c++14 -O2 -I. -FOpenCV tools/chessboard-harness/main.cpp /tmp/other.cpp \
        -framework opencv2 -framework Accelerate -framework OpenCL -o /tmp/harness_other

Judge the result on whether the distortion fit that follows is *accepted*, not on its residual.
An unconstrained fit to plumblines will often collapse the image toward the distortion centre,
which drives the residual to near zero while making the correction meaningless; on real
footage from this project three of four such fits were degenerate, including one reporting
0.0037 px per point. Check the solved parameters against the criteria in
`-[VSCalibration reasonToRejectSolvedDistortion:overPlumblineBox:warning:]` before believing
any residual.
