/*********************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2026 Jason Neuswanger
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 ***********************************************************************************/

// Chessboard corner detection for the distortion-correction plumbline workflow.
//
// This is deliberately plain C++ with no Cocoa or Core Data dependency, so it can be
// exercised from a test target against synthetic grids and a corpus of saved frames
// rather than only by eye against live video.
//
// Stage A of the detection pipeline lives here: find the points in the image that
// actually look like chessboard corners. Later stages (lattice basis estimation,
// grid assembly, curve-fit refinement) consume the point list this produces.

#ifndef VSChessboardDetector_hpp
#define VSChessboardDetector_hpp

#include <string>
#include <vector>

#include "opencv2/opencv.hpp"

namespace vidsync {

struct CornerCandidate {
    cv::Point2f position;   // Sub-pixel, in OpenCV image coordinates (origin top left, y downward).
    float score;            // Contrast-normalized corner score: 0 is nothing like a corner, 1 is ideal.
};

struct CornerDetectionResult {
    std::vector<CornerCandidate> corners;

    // Diagnostics, for the overlay and for tuning against real frames.
    int saddleCandidateCount;      // Local maxima of the saddle response, before appearance scoring.
    int prefilterRejectedCount;    // Candidates killed by the cheap single-radius appearance pass.
    float estimatedCellSize;       // Median nearest-neighbor spacing among accepted corners, px. 0 if indeterminate.
};

// Finds chessboard corners in a single-channel 8-bit image. Returns an empty result
// for an empty or wrongly-typed input rather than throwing.
//
// There are no tuning parameters by design. The appearance score is normalized by the
// local contrast of each candidate's own neighborhood, and is evaluated across a range
// of patch radii, so neither the frame's illumination nor the board's apparent cell size
// changes what counts as a corner.
CornerDetectionResult detectChessboardCorners(const cv::Mat &gray);

// --- Stage B and C: find the board and label a seed patch of it ---------------------

// The repeating step of the chessboard grid in image coordinates, measured over a small
// enough region that distortion has not yet bent it appreciably.
struct LatticeBasis {
    cv::Point2f u;
    cv::Point2f v;
    cv::Point2f windowCenter;   // Center of the region the basis was measured over.
    float windowSide;
    float peakSharpness;        // Histogram peak height over background; how grid-like the region is.
    bool valid;
};

// An optional hint from the user: two clicked points one grid step apart. This overrides
// the automatic search for the board, which matters because no automatic method will get
// every frame right and clicking two corners is a five second fix.
struct LatticeSeedHint {
    bool provided;
    cv::Point2f from;
    cv::Point2f to;

    LatticeSeedHint() : provided(false), from(0.0f, 0.0f), to(0.0f, 0.0f) {}
};

// A connected patch of corners that are consistent with a single lattice basis, each
// labelled with its integer grid coordinate. This is the starting point for grid growth.
struct SeedLattice {
    LatticeBasis basis;
    std::vector<int> cornerIndex;   // Indices into the corner vector passed in.
    std::vector<cv::Point2i> ij;    // Integer lattice coordinate of the corresponding corner.
    std::string status;             // Human-readable outcome, for the diagnostics display.
    bool valid;
};

// Locates the chessboard within a contaminated point cloud and labels a seed patch of it.
//
// The board is found rather than assumed to be centered: overlapping windows are tiled
// across the frame and each is scored by how sharply its pairwise-displacement histogram
// peaks. Clutter is aperiodic, so it spreads counts diffusely over thousands of histogram
// bins while every true corner pair one cell apart lands in the same bin. That signal to
// noise gap is what lets the board be picked out of a frame that is mostly riverbed.
//
// coarseCellSize is the estimate from detectChessboardCorners; pass 0 if unknown.
SeedLattice findSeedLattice(const std::vector<CornerCandidate> &corners,
                            float coarseCellSize,
                            cv::Size imageSize,
                            const LatticeSeedHint &hint);

// --- Stage D: grow the seed outward over the whole board ----------------------------

// Every corner the grid could be extended to, each with its integer grid coordinate.
// Holes are permitted: a site with no acceptable corner is simply absent.
struct GrownLattice {
    std::vector<int> cornerIndex;   // Indices into the corner vector passed in.
    std::vector<cv::Point2i> ij;
    LatticeBasis basis;             // Carried through from the seed, for predicting new sites.
    int minI, maxI, minJ, maxJ;
    int rounds;                     // Expansion rounds run before nothing more could be added.
    std::string status;
    bool valid;

    GrownLattice() : minI(0), maxI(0), minJ(0), maxJ(0), rounds(0), valid(false) {}
};

// Extends the seed lattice outward one ring at a time. Each candidate site's position is
// predicted from the corners already placed around it, preferring predictors that cancel
// the curvature radial distortion imposes on grid lines, and a corner is accepted only if
// it lies close to that prediction relative to the local cell spacing.
GrownLattice growLattice(const std::vector<CornerCandidate> &corners,
                         const SeedLattice &seed,
                         cv::Size imageSize);

// --- Stage E: curve-fit refinement ---------------------------------------------------

struct RefinementResult {
    GrownLattice lattice;
    int outliersRemoved;
    int cornersRecovered;   // Corners found directly in the image that the detector had missed.
    int passes;
    std::string status;

    RefinementResult() : outliersRemoved(0), cornersRecovered(0), passes(0) {}
};

// Cleans up the grown lattice by fitting a smooth curve to each row and column, discarding
// corners that sit far off their curve, and then filling the resulting holes -- along with
// any that growth left -- from the corners already detected, or failing that by searching the
// image directly at the predicted position.
//
// Corners recovered from the image are appended to `corners`, so it is taken by reference and
// the returned lattice indexes into the enlarged vector.
RefinementResult refineLattice(std::vector<CornerCandidate> &corners,
                               const GrownLattice &lattice,
                               const cv::Mat &gray);

// --- Plumblines ---------------------------------------------------------------------

// An ordered run of corners that lie on one straight line in the world, which is what the
// distortion fit consumes. Curvature in the image is the distortion to be solved for.
struct Plumbline {
    std::vector<cv::Point2f> points;   // Ordered along the line, OpenCV image coordinates.
    bool isRow;                        // True for constant j, false for constant i.
    int index;                         // The constant lattice coordinate of this line.
};

// Emits one plumbline per lattice row and column holding at least minPoints corners.
// Holes are not breaks: corners either side of a missing site are still collinear.
std::vector<Plumbline> extractPlumblines(const std::vector<CornerCandidate> &corners,
                                         const GrownLattice &lattice,
                                         int minPoints);

// The lattice diagonals, as ordered point sequences. Any arithmetic run of lattice sites is
// collinear on a planar board, so these are straight world lines exactly as rows and columns
// are, and they pass through the same corners.
//
// They are deliberately not fed to the distortion fit. Within a Brown-Conrady model, which is
// a radially symmetric map plus small tangential terms, several hundred points on fifty lines
// already overdetermine thirteen parameters, and every extra line costs a proportional share
// of every iteration of the solver. Held back instead, they measure whether the fitted model
// straightens directions it was never asked to straighten -- something the fit's own residual
// cannot report, since that can always be lowered by having fewer or shorter lines.
std::vector<std::vector<cv::Point2f> > extractDiagonalRuns(const std::vector<CornerCandidate> &corners,
                                                           const GrownLattice &lattice,
                                                           int minPoints);

}   // namespace vidsync

#endif /* VSChessboardDetector_hpp */
