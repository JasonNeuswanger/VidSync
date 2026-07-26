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

}   // namespace vidsync

#endif /* VSChessboardDetector_hpp */
