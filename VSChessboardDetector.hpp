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
    int saddleCandidateCount;   // Local maxima of the saddle response, before appearance scoring.
    float estimatedCellSize;    // Median nearest-neighbor spacing among accepted corners, px. 0 if indeterminate.
};

// Finds chessboard corners in a single-channel 8-bit image. Returns an empty result
// for an empty or wrongly-typed input rather than throwing.
//
// There are no tuning parameters by design. The appearance score is normalized by the
// local contrast of each candidate's own neighborhood, and is evaluated across a range
// of patch radii, so neither the frame's illumination nor the board's apparent cell size
// changes what counts as a corner.
CornerDetectionResult detectChessboardCorners(const cv::Mat &gray);

}   // namespace vidsync

#endif /* VSChessboardDetector_hpp */
