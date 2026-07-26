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

#include "VSChessboardDetector.hpp"

#include <algorithm>
#include <cmath>
#include <map>

namespace vidsync {

namespace {

// --- Constants -------------------------------------------------------------------
//
// None of these are exposed as user settings, and that is the point. The algorithm
// this replaces needed six numbers tuned per video because its corner detector had a
// threshold relative to the strongest response anywhere in the frame and a fixed
// pixel spacing. Here the threshold is applied to a locally contrast-normalized score
// and the patch size is swept, so the same constants hold across lighting and scale.

const double kClaheClipLimit = 2.0;
const int kClaheTileSize = 8;

// Gaussian sigmas, in pixels, at which the saddle response is computed. The pixel-wise
// maximum over scales responds to crisp and out-of-focus corners alike.
const double kSaddleScales[] = {1.5, 3.0};
const int kSaddleScaleCount = 2;

// Radius of the non-maximum suppression that turns the dense response into candidates.
// Small on purpose: at this stage duplicates are cheap and a missed corner is not.
const int kNonMaxRadius = 3;

// Safety valve, not a tuning knob. A board filling a 1080p frame yields on the order of
// 10^3 corners, so this only bounds pathological input.
const size_t kMaxCandidates = 8000;

// Patch radii at which the quadrant-contrast score is evaluated. The score is the maximum
// over every radius that fits inside the image, which is what makes it independent of the
// board's apparent cell size: a real corner scores well at any radius that stays within
// its own cell, and junk scores poorly at all of them.
const int kScoreRadii[] = {4, 6, 9, 13, 19, 28};
const int kScoreRadiusCount = 6;

// Orientations per radius, spread over the 90 degree period of a quadrant pattern.
const int kOrientationCount = 12;

// A cheap single-radius pass discards most junk before the full sweep runs.
const int kPrefilterRadius = 5;
const int kPrefilterOrientationCount = 6;
const double kPrefilterMinScore = 0.05;

// Minimum final appearance score. Conservative by design: later stages can reject a
// spurious point that survives, but they can never recover a real corner dropped here.
const double kMinScore = 0.15;

// Half-width of the sub-pixel fit window. The closed-form coefficients in
// subPixelSaddle() are derived for this value and must be re-derived if it changes.
const int kSubPixelRadius = 2;
const double kMaxSubPixelShift = 1.5;

// Two accepted corners closer than this are the same corner found twice.
const double kDuplicateRadius = 2.0;

// --- Quadrant masks --------------------------------------------------------------

// The pixel offsets making up one scoring patch, each tagged with which of the four
// quadrants of a corner at this orientation it falls into.
struct QuadrantMask {
    std::vector<cv::Point> offsets;
    std::vector<int> quadrant;
};

QuadrantMask buildQuadrantMask(int radius, double theta)
{
    QuadrantMask mask;
    // Skip a central disc. The corner itself is blurred across a few pixels by the lens
    // and the sensor, so those pixels belong to no quadrant in particular.
    const double innerSq = (0.3 * radius) * (0.3 * radius);
    const double outerSq = (double)radius * (double)radius;
    for (int dy = -radius; dy <= radius; dy++) {
        for (int dx = -radius; dx <= radius; dx++) {
            const double rsq = (double)(dx * dx + dy * dy);
            if (rsq < innerSq || rsq > outerSq) continue;
            double angle = std::atan2((double)dy, (double)dx) - theta;
            while (angle < 0.0) angle += 2.0 * CV_PI;
            while (angle >= 2.0 * CV_PI) angle -= 2.0 * CV_PI;
            mask.offsets.push_back(cv::Point(dx, dy));
            mask.quadrant.push_back(((int)(angle / (CV_PI / 2.0))) & 3);
        }
    }
    return mask;
}

// Builds masks for one radius at evenly spaced orientations covering 90 degrees.
std::vector<QuadrantMask> buildMaskBank(int radius, int orientationCount)
{
    std::vector<QuadrantMask> bank;
    bank.reserve(orientationCount);
    for (int i = 0; i < orientationCount; i++) {
        bank.push_back(buildQuadrantMask(radius, (CV_PI / 2.0) * i / orientationCount));
    }
    return bank;
}

// --- Appearance score ------------------------------------------------------------

// Measures how much a neighborhood looks like a chessboard corner: two diagonally
// opposite quadrants darker than both of the other two. A blob (a rock, a bolt head)
// has no such split. A step edge (a stick, the rim of the housing) puts its dark
// quadrants next to each other rather than opposite, so both pairings come out
// negative. Only a genuine saddle scores.
//
// Dividing by the patch's own contrast range is what makes a fixed threshold work: an
// ideal corner scores near 1 whether it sits in a shadow or under glare.
double quadrantScore(const cv::Mat &gray32, int x, int y, const QuadrantMask &mask)
{
    double sum[4] = {0.0, 0.0, 0.0, 0.0};
    int count[4] = {0, 0, 0, 0};
    double lo = 1e30;
    double hi = -1e30;
    const size_t n = mask.offsets.size();
    for (size_t i = 0; i < n; i++) {
        const float v = gray32.at<float>(y + mask.offsets[i].y, x + mask.offsets[i].x);
        const int q = mask.quadrant[i];
        sum[q] += v;
        count[q]++;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
    }
    for (int q = 0; q < 4; q++) {
        if (count[q] == 0) return 0.0;
    }
    const double contrast = hi - lo;
    if (contrast < 1e-6) return 0.0;
    const double m0 = sum[0] / count[0];
    const double m1 = sum[1] / count[1];
    const double m2 = sum[2] / count[2];
    const double m3 = sum[3] / count[3];
    const double darkEven = std::min(m1, m3) - std::max(m0, m2);
    const double darkOdd = std::min(m0, m2) - std::max(m1, m3);
    const double best = std::max(darkEven, darkOdd);
    if (best <= 0.0) return 0.0;
    return best / contrast;
}

double bestScoreOverOrientations(const cv::Mat &gray32, int x, int y, const std::vector<QuadrantMask> &bank)
{
    double best = 0.0;
    for (size_t i = 0; i < bank.size(); i++) {
        const double s = quadrantScore(gray32, x, y, bank[i]);
        if (s > best) best = s;
    }
    return best;
}

// --- Sub-pixel refinement --------------------------------------------------------

// Fits a quadratic surface to the intensity in a small window and returns its saddle
// point. This models what a chessboard corner actually is, so unlike cornerSubPix it
// needs no window scaled to the cell pitch and cannot be dragged toward a neighboring
// corner by too large a window. Returning false when the surface has no saddle at all
// doubles as a final rejection test.
bool subPixelSaddle(const cv::Mat &gray32, int x, int y, cv::Point2f *out)
{
    const int r = kSubPixelRadius;
    double sI = 0.0, sxI = 0.0, syI = 0.0, sxxI = 0.0, sxyI = 0.0, syyI = 0.0;
    for (int dy = -r; dy <= r; dy++) {
        for (int dx = -r; dx <= r; dx++) {
            const double v = gray32.at<float>(y + dy, x + dx);
            sI += v;
            sxI += dx * v;
            syI += dy * v;
            sxxI += dx * dx * v;
            sxyI += dx * dy * v;
            syyI += dy * dy * v;
        }
    }
    // Least-squares fit of a + b*x + c*y + d*x^2 + e*x*y + f*y^2 over the 5x5 integer
    // grid. Because that grid is fixed and symmetric the normal equations collapse to
    // these divisors: sum(x^2) = 50, sum(x^2*y^2) = 100, and the coupled (a, d, f) block
    // inverts to the constant 1/70 form below.
    const double b = sxI / 50.0;
    const double c = syI / 50.0;
    const double e = sxyI / 100.0;
    const double d = (sxxI - 2.0 * sI) / 70.0;
    const double f = (syyI - 2.0 * sI) / 70.0;

    // A saddle needs curvatures of opposite sign, i.e. a negative Hessian determinant.
    const double det = 4.0 * d * f - e * e;
    if (det >= -1e-12) return false;

    const double ox = (e * c - 2.0 * f * b) / det;
    const double oy = (e * b - 2.0 * d * c) / det;
    if (std::fabs(ox) > kMaxSubPixelShift || std::fabs(oy) > kMaxSubPixelShift) return false;

    out->x = (float)((double)x + ox);
    out->y = (float)((double)y + oy);
    return true;
}

// --- Small helpers ---------------------------------------------------------------

struct ScoredPixel {
    int x;
    int y;
    float response;
};

bool byResponseDescending(const ScoredPixel &a, const ScoredPixel &b)
{
    return a.response > b.response;
}

bool byScoreDescending(const CornerCandidate &a, const CornerCandidate &b)
{
    return a.score > b.score;
}

// Greedy duplicate collapse, keeping the higher-scoring member of each cluster. Uses a
// bucket grid so this stays linear in the number of corners.
std::vector<CornerCandidate> collapseDuplicates(std::vector<CornerCandidate> corners, double radius)
{
    std::sort(corners.begin(), corners.end(), byScoreDescending);
    const double radiusSq = radius * radius;
    std::map<long long, std::vector<size_t> > buckets;
    std::vector<CornerCandidate> kept;
    kept.reserve(corners.size());
    for (size_t i = 0; i < corners.size(); i++) {
        const cv::Point2f &p = corners[i].position;
        const long long bx = (long long)std::floor(p.x / radius);
        const long long by = (long long)std::floor(p.y / radius);
        bool duplicate = false;
        for (long long gx = bx - 1; gx <= bx + 1 && !duplicate; gx++) {
            for (long long gy = by - 1; gy <= by + 1 && !duplicate; gy++) {
                std::map<long long, std::vector<size_t> >::const_iterator it = buckets.find(gx * 1000000LL + gy);
                if (it == buckets.end()) continue;
                for (size_t k = 0; k < it->second.size(); k++) {
                    const cv::Point2f &q = kept[it->second[k]].position;
                    const double dx = p.x - q.x;
                    const double dy = p.y - q.y;
                    if (dx * dx + dy * dy < radiusSq) {
                        duplicate = true;
                        break;
                    }
                }
            }
        }
        if (duplicate) continue;
        buckets[bx * 1000000LL + by].push_back(kept.size());
        kept.push_back(corners[i]);
    }
    return kept;
}

// Median nearest-neighbor distance, a first approximation of the board's cell pitch.
// Stage B replaces this with a proper pairwise-displacement histogram; it is here so the
// overlay can report something useful and so later stages have a starting scale.
float medianNearestNeighborDistance(const std::vector<CornerCandidate> &corners)
{
    const size_t n = corners.size();
    if (n < 2) return 0.0f;
    std::vector<double> nearest;
    nearest.reserve(n);
    for (size_t i = 0; i < n; i++) {
        double best = 1e30;
        for (size_t j = 0; j < n; j++) {
            if (i == j) continue;
            const double dx = corners[i].position.x - corners[j].position.x;
            const double dy = corners[i].position.y - corners[j].position.y;
            const double dsq = dx * dx + dy * dy;
            if (dsq < best) best = dsq;
        }
        nearest.push_back(std::sqrt(best));
    }
    std::sort(nearest.begin(), nearest.end());
    return (float)nearest[nearest.size() / 2];
}

}   // anonymous namespace

// --- Entry point -----------------------------------------------------------------

CornerDetectionResult detectChessboardCorners(const cv::Mat &gray)
{
    CornerDetectionResult result;
    result.saddleCandidateCount = 0;
    result.estimatedCellSize = 0.0f;
    if (gray.empty() || gray.type() != CV_8UC1) return result;

    // Equalize local contrast first. Underwater housings vignette badly and illumination
    // across a submerged board is rarely uniform, so without this a corner in shadow and
    // a corner under glare cannot share a single detection threshold.
    cv::Mat equalized;
    cv::Ptr<cv::CLAHE> clahe = cv::createCLAHE(kClaheClipLimit, cv::Size(kClaheTileSize, kClaheTileSize));
    clahe->apply(gray, equalized);

    cv::Mat gray32;
    equalized.convertTo(gray32, CV_32F, 1.0 / 255.0);

    // A chessboard corner is a saddle of the intensity surface, where the Hessian
    // determinant is negative. Rocks and other blobs curve the same way in both
    // directions and are excluded here rather than merely outscored, which is the key
    // difference from the Shi-Tomasi detector this replaces.
    cv::Mat response;
    for (int s = 0; s < kSaddleScaleCount; s++) {
        cv::Mat blurred, ixx, iyy, ixy, scaleResponse;
        cv::GaussianBlur(gray32, blurred, cv::Size(0, 0), kSaddleScales[s]);
        cv::Sobel(blurred, ixx, CV_32F, 2, 0, 3);
        cv::Sobel(blurred, iyy, CV_32F, 0, 2, 3);
        cv::Sobel(blurred, ixy, CV_32F, 1, 1, 3);
        scaleResponse = ixy.mul(ixy) - ixx.mul(iyy);
        if (response.empty()) {
            response = scaleResponse;
        } else {
            cv::max(response, scaleResponse, response);
        }
    }

    // Non-maximum suppression by comparing against a dilation of the response.
    cv::Mat dilated;
    cv::dilate(response, dilated,
               cv::getStructuringElement(cv::MORPH_RECT, cv::Size(2 * kNonMaxRadius + 1, 2 * kNonMaxRadius + 1)));

    // The margin only has to accommodate the prefilter and the sub-pixel window. Larger
    // scoring radii are skipped individually near the frame edge instead of excluding the
    // corner, because corners near the edge carry the most information about distortion.
    const int margin = std::max(kPrefilterRadius, kSubPixelRadius) + 1;
    std::vector<ScoredPixel> candidates;
    for (int y = margin; y < gray.rows - margin; y++) {
        const float *responseRow = response.ptr<float>(y);
        const float *dilatedRow = dilated.ptr<float>(y);
        for (int x = margin; x < gray.cols - margin; x++) {
            if (responseRow[x] <= 0.0f) continue;       // not a saddle at any scale
            if (responseRow[x] < dilatedRow[x]) continue;   // not a local maximum
            ScoredPixel p;
            p.x = x;
            p.y = y;
            p.response = responseRow[x];
            candidates.push_back(p);
        }
    }
    result.saddleCandidateCount = (int)candidates.size();

    if (candidates.size() > kMaxCandidates) {
        std::partial_sort(candidates.begin(), candidates.begin() + kMaxCandidates, candidates.end(),
                          byResponseDescending);
        candidates.resize(kMaxCandidates);
    }

    const std::vector<QuadrantMask> prefilterBank = buildMaskBank(kPrefilterRadius, kPrefilterOrientationCount);
    std::vector<std::vector<QuadrantMask> > scoreBanks;
    scoreBanks.reserve(kScoreRadiusCount);
    for (int r = 0; r < kScoreRadiusCount; r++) {
        scoreBanks.push_back(buildMaskBank(kScoreRadii[r], kOrientationCount));
    }

    std::vector<CornerCandidate> accepted;
    for (size_t i = 0; i < candidates.size(); i++) {
        const int x = candidates[i].x;
        const int y = candidates[i].y;

        // Cheap single-radius pass first; most junk dies here.
        if (bestScoreOverOrientations(gray32, x, y, prefilterBank) < kPrefilterMinScore) continue;

        double best = 0.0;
        for (int r = 0; r < kScoreRadiusCount; r++) {
            const int radius = kScoreRadii[r];
            if (x - radius < 0 || y - radius < 0 || x + radius >= gray.cols || y + radius >= gray.rows) continue;
            const double s = bestScoreOverOrientations(gray32, x, y, scoreBanks[r]);
            if (s > best) best = s;
        }
        if (best < kMinScore) continue;

        CornerCandidate corner;
        if (!subPixelSaddle(gray32, x, y, &corner.position)) continue;
        corner.score = (float)best;
        accepted.push_back(corner);
    }

    result.corners = collapseDuplicates(accepted, kDuplicateRadius);
    result.estimatedCellSize = medianNearestNeighborDistance(result.corners);
    return result;
}

}   // namespace vidsync
