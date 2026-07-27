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
#include <set>
#include <sstream>

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

// Minimum black-to-white range, on a 0-1 intensity scale, for a patch to be judged at all.
// Without this the contrast normalization turns noise in flat regions into high scores.
const double kMinPatchContrast = 0.12;

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
    // An absolute floor as well as the normalization. Dividing by the patch's own contrast is
    // what makes the score comparable between a corner in shadow and one under glare, but in a
    // nearly uniform patch -- the middle of a chessboard square, say -- that same division
    // amplifies sensor noise into a high score. Since a checkerboard is mostly flat area, with
    // no floor this fabricates detections across the whole board interior. A real corner spans
    // a large part of the black-to-white range even after local equalization.
    const double contrast = hi - lo;
    if (contrast < kMinPatchContrast) return 0.0;
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

// Local contrast equalization followed by conversion to floats in 0..1. Shared by detection
// and by the refinement pass, which searches the image again at predicted positions and must
// see exactly the same pixels the appearance score was calibrated against.
void prepareImage(const cv::Mat &gray, cv::Mat *gray32)
{
    cv::Mat equalized;
    cv::Ptr<cv::CLAHE> clahe = cv::createCLAHE(kClaheClipLimit, cv::Size(kClaheTileSize, kClaheTileSize));
    clahe->apply(gray, equalized);
    equalized.convertTo(*gray32, CV_32F, 1.0 / 255.0);
}

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
    result.prefilterRejectedCount = 0;
    result.estimatedCellSize = 0.0f;
    if (gray.empty() || gray.type() != CV_8UC1) return result;

    // Equalize local contrast first. Underwater housings vignette badly and illumination
    // across a submerged board is rarely uniform, so without this a corner in shadow and
    // a corner under glare cannot share a single detection threshold.
    cv::Mat gray32;
    prepareImage(gray, &gray32);

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
        if (bestScoreOverOrientations(gray32, x, y, prefilterBank) < kPrefilterMinScore) {
            result.prefilterRejectedCount++;
            continue;
        }

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

// --- Stage B and C ----------------------------------------------------------------

namespace {

// Fewest points a window needs before its histogram means anything.
const size_t kWindowMinPoints = 12;

// Windows span roughly this many grid cells. Small enough that distortion has not visibly
// bent the grid across the window, large enough that the histogram peak is well populated.
const double kWindowCells = 10.0;

// Centered-window sizes, as fractions of the image width, tried smallest first. Deliberately
// not derived from a point-density estimate: point density is exactly what contamination
// corrupts, and with spurious detections between the true corners the median
// nearest-neighbor distance reads a fraction of the real cell pitch.
const double kWindowWidthFractions[] = {0.5, 0.7, 0.34};
const int kWindowWidthFractionCount = 3;

// A seed patch this size is good enough to stop enlarging the window.
const size_t kGoodSeedPatchPoints = 24;

// A basis further off the image axes than this is treated as suspect and only used when no
// window offers an aligned one. The field protocol calls for the board to be rotated into
// approximate alignment with the cameras, so a genuine basis is normally within a few degrees
// of the axes: measured on real footage, good frames come out at 6 to 8 degrees and the one
// that failed at 40. The threshold sits well clear of both, leaving room for a board set down
// carelessly while still excluding anything close to diagonal.
const double kMaxBasisMisalignmentDegrees = 30.0;

// The displacement histogram is built twice per window. The first pass uses a radius
// covering a good fraction of the window, so it finds the lattice step without assuming
// it; the second pass re-bins tightly around that step for a precise basis.
const double kCoarseRadiusFraction = 1.0 / 3.0;
const int kCoarseHistogramBins = 65;
const double kCoarsePeakMinFraction = 0.35;
const double kFineRadiusFactor = 1.8;
const int kFineHistogramBins = 33;

// A histogram peak must reach this fraction of the largest non-origin count to be a
// candidate basis vector.
const double kPeakMinFraction = 0.25;

// Rejects a second basis vector that is collinear with the first (u versus 2u).
const double kMinSinAngle = 0.5;

// The two basis vectors of a chessboard cannot differ wildly in length.
const double kBasisLengthRatioMax = 2.5;

// A genuine lattice also shows peaks at the cell diagonals. Requiring them rejects
// one-dimensional periodic clutter such as a row of evenly spaced bolts.
const double kDiagonalMinFraction = 0.10;

// How far a point may sit from its predicted lattice position, as a fraction of the
// shorter basis vector.
const double kLatticeTolerance = 0.15;

// Below this many fully-consistent points, accept three-of-four consistency instead.
const size_t kMinFullyConsistentPoints = 6;

// Looks up corners by position without an O(n^2) scan.
class PointLookup {
public:
    PointLookup(const std::vector<CornerCandidate> &corners, const std::vector<int> &subset, double cell)
        : corners_(corners), subset_(subset), cell_(cell > 1.0 ? cell : 1.0)
    {
        for (size_t k = 0; k < subset_.size(); k++) {
            buckets_[key(corners_[subset_[k]].position)].push_back(k);
        }
    }

    // As nearestWithin, but ignoring corners already claimed by another lattice site.
    int nearestWithinExcluding(const cv::Point2f &p, double radius, const std::vector<bool> &excluded) const
    {
        const double radiusSq = radius * radius;
        const long long bx = (long long)std::floor(p.x / cell_);
        const long long by = (long long)std::floor(p.y / cell_);
        int best = -1;
        double bestSq = radiusSq;
        const int span = (int)std::ceil(radius / cell_);
        for (long long gx = bx - span; gx <= bx + span; gx++) {
            for (long long gy = by - span; gy <= by + span; gy++) {
                std::map<long long, std::vector<size_t> >::const_iterator it = buckets_.find(gx * 1000000LL + gy);
                if (it == buckets_.end()) continue;
                for (size_t k = 0; k < it->second.size(); k++) {
                    const size_t slot = it->second[k];
                    if (slot < excluded.size() && excluded[slot]) continue;
                    const cv::Point2f &q = corners_[subset_[slot]].position;
                    const double dx = p.x - q.x;
                    const double dy = p.y - q.y;
                    const double dsq = dx * dx + dy * dy;
                    if (dsq < bestSq) {
                        bestSq = dsq;
                        best = (int)slot;
                    }
                }
            }
        }
        return best;
    }

    // Returns the position within `subset` of the nearest corner to p inside radius, or -1.
    int nearestWithin(const cv::Point2f &p, double radius) const
    {
        const double radiusSq = radius * radius;
        const long long bx = (long long)std::floor(p.x / cell_);
        const long long by = (long long)std::floor(p.y / cell_);
        int best = -1;
        double bestSq = radiusSq;
        const int span = (int)std::ceil(radius / cell_);
        for (long long gx = bx - span; gx <= bx + span; gx++) {
            for (long long gy = by - span; gy <= by + span; gy++) {
                std::map<long long, std::vector<size_t> >::const_iterator it = buckets_.find(gx * 1000000LL + gy);
                if (it == buckets_.end()) continue;
                for (size_t k = 0; k < it->second.size(); k++) {
                    const cv::Point2f &q = corners_[subset_[it->second[k]]].position;
                    const double dx = p.x - q.x;
                    const double dy = p.y - q.y;
                    const double dsq = dx * dx + dy * dy;
                    if (dsq < bestSq) {
                        bestSq = dsq;
                        best = (int)it->second[k];
                    }
                }
            }
        }
        return best;
    }

private:
    long long key(const cv::Point2f &p) const
    {
        return (long long)std::floor(p.x / cell_) * 1000000LL + (long long)std::floor(p.y / cell_);
    }

    const std::vector<CornerCandidate> &corners_;
    const std::vector<int> &subset_;
    double cell_;
    std::map<long long, std::vector<size_t> > buckets_;
};

double vectorLength(const cv::Point2f &p)
{
    return std::sqrt((double)p.x * p.x + (double)p.y * p.y);
}

struct HistogramPeak {
    cv::Point2f displacement;
    float count;
};

bool byPeakCountDescending(const HistogramPeak &a, const HistogramPeak &b)
{
    return a.count > b.count;
}

// Builds the pairwise-displacement histogram for one window and extracts its peaks.
// Returns the sharpness of the strongest peak relative to the diffuse background, which
// is the score used to decide which window is looking at the board.
double displacementPeaks(const std::vector<CornerCandidate> &corners,
                         const std::vector<int> &subset,
                         double radius,
                         int binCount,
                         double peakMinFraction,
                         std::vector<HistogramPeak> *peaks)
{
    peaks->clear();
    if (radius <= 0.0) return 0.0;

    const int nb = binCount;
    const double binSize = 2.0 * radius / nb;
    cv::Mat hist(nb, nb, CV_32F, cv::Scalar(0.0f));
    const double radiusSq = radius * radius;
    for (size_t i = 0; i < subset.size(); i++) {
        const cv::Point2f &a = corners[subset[i]].position;
        for (size_t j = i + 1; j < subset.size(); j++) {
            const cv::Point2f &b = corners[subset[j]].position;
            const double dx = b.x - a.x;
            const double dy = b.y - a.y;
            if (dx * dx + dy * dy > radiusSq) continue;
            // Accumulate both signs; the set of lattice displacements is symmetric.
            for (int s = 0; s < 2; s++) {
                const double sx = s ? -dx : dx;
                const double sy = s ? -dy : dy;
                int bx = (int)std::floor((sx + radius) / binSize);
                int by = (int)std::floor((sy + radius) / binSize);
                if (bx < 0 || by < 0 || bx >= nb || by >= nb) continue;
                hist.at<float>(by, bx) += 1.0f;
            }
        }
    }
    cv::GaussianBlur(hist, hist, cv::Size(3, 3), 1.0);

    // Suppress the cluster around zero displacement, which carries no lattice information.
    // Scaled to the bin size rather than to the search radius, so that a fine-pitched board
    // does not have its own basis peak suppressed along with the origin.
    const double originRadius = 2.5 * binSize;
    for (int by = 0; by < nb; by++) {
        for (int bx = 0; bx < nb; bx++) {
            const double dx = (bx + 0.5) * binSize - radius;
            const double dy = (by + 0.5) * binSize - radius;
            if (dx * dx + dy * dy < originRadius * originRadius) hist.at<float>(by, bx) = 0.0f;
        }
    }

    double maxCount = 0.0;
    double totalCount = 0.0;
    int nonZeroBins = 0;
    for (int by = 0; by < nb; by++) {
        for (int bx = 0; bx < nb; bx++) {
            const float c = hist.at<float>(by, bx);
            if (c > maxCount) maxCount = c;
            totalCount += c;
            nonZeroBins++;
        }
    }
    if (maxCount <= 0.0) return 0.0;

    cv::Mat dilated;
    cv::dilate(hist, dilated, cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3)));
    for (int by = 1; by < nb - 1; by++) {
        for (int bx = 1; bx < nb - 1; bx++) {
            const float c = hist.at<float>(by, bx);
            if (c < peakMinFraction * maxCount) continue;
            if (c < dilated.at<float>(by, bx)) continue;
            // Keep one of each mirrored pair, chosen before sub-bin refinement so the
            // choice cannot flip for peaks lying on an axis.
            const double cx = (bx + 0.5) * binSize - radius;
            const double cy = (by + 0.5) * binSize - radius;
            if (cx < 0.0 || (std::fabs(cx) < 0.5 * binSize && cy < 0.0)) continue;
            // Refine to sub-bin precision by centroid over the 3x3 neighborhood.
            double wsum = 0.0, xsum = 0.0, ysum = 0.0;
            for (int oy = -1; oy <= 1; oy++) {
                for (int ox = -1; ox <= 1; ox++) {
                    const double w = hist.at<float>(by + oy, bx + ox);
                    wsum += w;
                    xsum += w * ((bx + ox + 0.5) * binSize - radius);
                    ysum += w * ((by + oy + 0.5) * binSize - radius);
                }
            }
            if (wsum <= 0.0) continue;
            HistogramPeak peak;
            peak.displacement = cv::Point2f((float)(xsum / wsum), (float)(ysum / wsum));
            peak.count = c;
            peaks->push_back(peak);
        }
    }

    const double meanCount = nonZeroBins > 0 ? totalCount / nonZeroBins : 0.0;
    return meanCount > 1e-9 ? maxCount / meanCount : 0.0;
}

// Counts how much histogram mass sits near a given displacement, as a fraction of the
// strongest peak. Used to confirm the cell diagonals exist.
bool peakExistsNear(const std::vector<HistogramPeak> &peaks, const cv::Point2f &target, double tolerance,
                    double minCount)
{
    for (size_t i = 0; i < peaks.size(); i++) {
        for (int s = 0; s < 2; s++) {
            const cv::Point2f p = s ? cv::Point2f(-peaks[i].displacement.x, -peaks[i].displacement.y)
                                    : peaks[i].displacement;
            if (vectorLength(cv::Point2f(p.x - target.x, p.y - target.y)) < tolerance && peaks[i].count >= minCount) {
                return true;
            }
        }
    }
    return false;
}

// How far a basis is from lining up with the image axes, in degrees: 0 for a grid running
// exactly horizontally and vertically, 45 for one running exactly diagonally.
//
// The field protocol has the board rotated into approximate alignment with the cameras, so a
// basis near 45 degrees is not describing the rows and columns of the board. It is describing
// the diagonals, which happens when the detector finds only every other corner over part of a
// window: those form a lattice of their own, rotated 45 degrees with a cell root two times
// larger, and the displacement histogram peaks on it just as convincingly. Nothing downstream
// recovers from that, because the diagonal lattice does not contain the true row and column
// vectors at all -- the Lagrange reduction in selectBasis shortens a basis within the lattice
// it is handed and cannot step outside it.
//
// Taken modulo 90 degrees because which vector is called u, and which way each points, are
// both arbitrary; only the grid's orientation matters.
double basisMisalignmentDegrees(const cv::Point2f &u, const cv::Point2f &v)
{
    double worst = 0.0;
    for (int which = 0; which < 2; which++) {
        const cv::Point2f &w = (which == 0) ? u : v;
        if (vectorLength(w) < 1e-6) continue;
        double angle = std::atan2((double)w.y, (double)w.x) * 180.0 / CV_PI;
        angle = angle - 90.0 * std::floor(angle / 90.0);   // fold into [0, 90)
        const double offAxis = std::min(angle, 90.0 - angle);
        if (offAxis > worst) worst = offAxis;
    }
    return worst;
}

// Picks two short, non-collinear peaks as the lattice basis and sanity-checks them.
bool selectBasis(const std::vector<HistogramPeak> &peaksIn, cv::Point2f *outU, cv::Point2f *outV)
{
    // Ordered by how populated each peak is, not by how short it is. The nearest-neighbour
    // displacement is by construction the most populated bin, whereas the shortest peak is
    // whatever spurious detection happens to sit closest together -- scratches and scuffs on
    // the board produce clusters that generate real but meaningless short-range peaks, and
    // selecting by length walks straight into them.
    std::vector<HistogramPeak> peaks = peaksIn;
    std::sort(peaks.begin(), peaks.end(), byPeakCountDescending);
    if (peaks.size() < 2) return false;

    cv::Point2f u = peaks[0].displacement;
    const double lenU = vectorLength(u);
    if (lenU < 1e-6) return false;

    cv::Point2f v(0.0f, 0.0f);
    bool foundV = false;
    for (size_t i = 1; i < peaks.size(); i++) {
        const cv::Point2f cand = peaks[i].displacement;
        const double lenC = vectorLength(cand);
        if (lenC < 1e-6) continue;
        const double cross = (double)u.x * cand.y - (double)u.y * cand.x;
        if (std::fabs(cross) / (lenU * lenC) < kMinSinAngle) continue;   // collinear: u versus 2u
        v = cand;
        foundV = true;
        break;
    }
    if (!foundV) return false;

    // Lagrange reduction, so the basis describes the smallest cell rather than a sheared
    // multiple of it.
    for (int iteration = 0; iteration < 8; iteration++) {
        bool changed = false;
        if (vectorLength(cv::Point2f(v.x - u.x, v.y - u.y)) < vectorLength(v)) {
            v = cv::Point2f(v.x - u.x, v.y - u.y);
            changed = true;
        } else if (vectorLength(cv::Point2f(v.x + u.x, v.y + u.y)) < vectorLength(v)) {
            v = cv::Point2f(v.x + u.x, v.y + u.y);
            changed = true;
        }
        if (vectorLength(v) < vectorLength(u)) std::swap(u, v);
        if (!changed) break;
    }

    const double a = vectorLength(u);
    const double b = vectorLength(v);
    if (a < 1e-6 || b < 1e-6) return false;
    if (b / a > kBasisLengthRatioMax) return false;
    const double cross = (double)u.x * v.y - (double)u.y * v.x;
    if (std::fabs(cross) / (a * b) < kMinSinAngle) return false;

    // Consistent sign convention, so the same board always yields the same basis.
    if (u.x < 0.0f || (std::fabs(u.x) < 1e-6 && u.y < 0.0f)) u = cv::Point2f(-u.x, -u.y);
    if ((double)u.x * v.y - (double)u.y * v.x < 0.0) v = cv::Point2f(-v.x, -v.y);

    *outU = u;
    *outV = v;
    return true;
}

// The outcome of running the lattice-consistency test over one window with one basis.
struct SeedPatch {
    std::vector<int> cornerIndex;
    std::vector<cv::Point2i> ij;
    int extentI;
    int extentJ;
    int duplicatesDropped;
    bool conflict;

    SeedPatch() : extentI(0), extentJ(0), duplicatesDropped(0), conflict(false) {}
};

// Keeps the points in `subset` that behave like sites of the lattice (u, v), takes the
// largest connected group of them, and labels each with its integer grid coordinate.
SeedPatch labelSeedPatch(const std::vector<CornerCandidate> &corners,
                         const std::vector<int> &subset,
                         const cv::Point2f &u,
                         const cv::Point2f &v)
{
    SeedPatch patch;
    const double epsilon = kLatticeTolerance * std::min(vectorLength(u), vectorLength(v));
    if (epsilon <= 0.0) return patch;
    PointLookup lookup(corners, subset, std::max(epsilon, 1.0));

    cv::Point2f steps[4];
    steps[0] = u;
    steps[1] = cv::Point2f(-u.x, -u.y);
    steps[2] = v;
    steps[3] = cv::Point2f(-v.x, -v.y);

    std::vector<int> consistency(subset.size(), 0);
    std::vector<int> neighbor(subset.size() * 4, -1);
    for (size_t k = 0; k < subset.size(); k++) {
        const cv::Point2f &p = corners[subset[k]].position;
        for (int d = 0; d < 4; d++) {
            const cv::Point2f target(p.x + steps[d].x, p.y + steps[d].y);
            const int found = lookup.nearestWithin(target, epsilon);
            neighbor[k * 4 + d] = found;
            if (found >= 0) consistency[k]++;
        }
    }

    // Points on the window boundary can only ever reach three neighbours, so insisting on
    // four throws away the whole outer ring. Relax when that would leave too little.
    int requiredConsistency = 4;
    size_t fullyConsistent = 0;
    for (size_t k = 0; k < consistency.size(); k++) if (consistency[k] == 4) fullyConsistent++;
    if (fullyConsistent < kMinFullyConsistentPoints) requiredConsistency = 3;

    std::vector<bool> kept(subset.size(), false);
    for (size_t k = 0; k < consistency.size(); k++) kept[k] = (consistency[k] >= requiredConsistency);

    // Largest connected group, walking only along basis steps. Connectivity is what keeps
    // this on the board: unrelated structure elsewhere is never reached.
    std::vector<int> component(subset.size(), -1);
    int bestComponent = -1;
    size_t bestComponentSize = 0;
    int componentCount = 0;
    for (size_t start = 0; start < subset.size(); start++) {
        if (!kept[start] || component[start] >= 0) continue;
        std::vector<size_t> queue;
        queue.push_back(start);
        component[start] = componentCount;
        size_t size = 0;
        for (size_t q = 0; q < queue.size(); q++) {
            const size_t k = queue[q];
            size++;
            for (int d = 0; d < 4; d++) {
                const int n = neighbor[k * 4 + d];
                if (n < 0 || !kept[n] || component[n] >= 0) continue;
                component[n] = componentCount;
                queue.push_back((size_t)n);
            }
        }
        if (size > bestComponentSize) {
            bestComponentSize = size;
            bestComponent = componentCount;
        }
        componentCount++;
    }
    if (bestComponent < 0) return patch;

    // Label by walking the component, adding one integer step per basis edge traversed.
    const cv::Point2i stepIJ[4] = {cv::Point2i(1, 0), cv::Point2i(-1, 0), cv::Point2i(0, 1), cv::Point2i(0, -1)};
    std::vector<cv::Point2i> label(subset.size(), cv::Point2i(0, 0));
    std::vector<bool> labelled(subset.size(), false);
    // How far each corner sat from the position the lattice predicted for it. This is the
    // criterion for resolving two corners that claim the same site: the one that landed
    // closer to where the grid says it should be is the real one.
    std::vector<double> arrivalError(subset.size(), 1e30);
    size_t root = 0;
    for (size_t k = 0; k < subset.size(); k++) {
        if (component[k] == bestComponent) { root = k; break; }
    }
    std::vector<size_t> queue;
    queue.push_back(root);
    labelled[root] = true;
    arrivalError[root] = 0.0;
    for (size_t q = 0; q < queue.size(); q++) {
        const size_t k = queue[q];
        for (int d = 0; d < 4; d++) {
            const int n = neighbor[k * 4 + d];
            if (n < 0 || component[n] != bestComponent) continue;
            const cv::Point2i expected(label[k].x + stepIJ[d].x, label[k].y + stepIJ[d].y);
            if (labelled[n]) {
                // Reaching the same corner with two different coordinates means the basis or
                // the tolerance is wrong. Report it rather than quietly averaging.
                if (label[n] != expected) patch.conflict = true;
            } else {
                const cv::Point2f predicted(corners[subset[k]].position.x + steps[d].x,
                                            corners[subset[k]].position.y + steps[d].y);
                label[n] = expected;
                labelled[n] = true;
                arrivalError[n] = vectorLength(cv::Point2f(corners[subset[n]].position.x - predicted.x,
                                                           corners[subset[n]].position.y - predicted.y));
                queue.push_back((size_t)n);
            }
        }
    }

    // How good a claim a corner has on its site. Appearance carries most of the weight,
    // because telling a real corner from a scratch is precisely what that score measures.
    // Arrival error is only a tie-breaker: under strong fisheye the straight-line prediction
    // from a neighbour is systematically offset from the true corner, since the grid curves
    // between them, so on its own it favours whichever point sits in the direction the
    // curvature bends and will happily prefer a scratch to the corner beside it. Expressing
    // the error as a fraction of a cell puts the two terms on a comparable scale.
    const double cellSize = std::min(vectorLength(u), vectorLength(v));
    std::vector<double> claimQuality(subset.size(), -1e30);
    for (size_t k = 0; k < subset.size(); k++) {
        if (!labelled[k]) continue;
        claimQuality[k] = corners[subset[k]].score - (cellSize > 1e-6 ? arrivalError[k] / cellSize : 0.0);
    }

    // One corner per lattice site. A scratch or scuff close to a real corner passes the
    // lattice-consistency test exactly as the real corner does, because it lies within the
    // matching tolerance of the same four neighbours, so both end up labelled. The conflict
    // test above cannot see this: it fires when one corner is reached with two different
    // coordinates, not when two corners claim one coordinate.
    std::map<long long, size_t> siteOwner;
    for (size_t k = 0; k < subset.size(); k++) {
        if (!labelled[k]) continue;
        const long long key = (long long)label[k].x * 1000000LL + (long long)label[k].y;
        std::map<long long, size_t>::iterator it = siteOwner.find(key);
        if (it == siteOwner.end()) {
            siteOwner[key] = k;
            continue;
        }
        const size_t incumbent = it->second;
        if (claimQuality[k] > claimQuality[incumbent]) {
            labelled[incumbent] = false;
            it->second = k;
        } else {
            labelled[k] = false;
        }
        patch.duplicatesDropped++;
    }

    // Two corners closer together than half a cell cannot both be lattice sites whatever
    // coordinates they were given, so this also catches a near-duplicate that happened to be
    // labelled with a neighbouring index rather than the same one.
    const double minSeparation = 0.5 * std::min(vectorLength(u), vectorLength(v));
    for (size_t k = 0; k < subset.size(); k++) {
        if (!labelled[k]) continue;
        for (size_t m = k + 1; m < subset.size(); m++) {
            if (!labelled[m]) continue;
            const cv::Point2f &p = corners[subset[k]].position;
            const cv::Point2f &q = corners[subset[m]].position;
            if (vectorLength(cv::Point2f(p.x - q.x, p.y - q.y)) >= minSeparation) continue;
            if (claimQuality[m] > claimQuality[k]) {
                labelled[k] = false;
                patch.duplicatesDropped++;
                break;
            }
            labelled[m] = false;
            patch.duplicatesDropped++;
        }
    }

    int minI = 0, maxI = 0, minJ = 0, maxJ = 0;
    bool first = true;
    for (size_t k = 0; k < subset.size(); k++) {
        if (!labelled[k]) continue;
        patch.cornerIndex.push_back(subset[k]);
        patch.ij.push_back(label[k]);
        if (first) {
            minI = maxI = label[k].x;
            minJ = maxJ = label[k].y;
            first = false;
        } else {
            minI = std::min(minI, label[k].x);
            maxI = std::max(maxI, label[k].x);
            minJ = std::min(minJ, label[k].y);
            maxJ = std::max(maxJ, label[k].y);
        }
    }
    patch.extentI = first ? 0 : (maxI - minI + 1);
    patch.extentJ = first ? 0 : (maxJ - minJ + 1);
    return patch;
}

}   // anonymous namespace

SeedLattice findSeedLattice(const std::vector<CornerCandidate> &corners,
                            float coarseCellSize,
                            cv::Size imageSize,
                            const LatticeSeedHint &hint)
{
    (void)coarseCellSize;   // Advisory only; the histogram measures the pitch itself.

    SeedLattice seed;
    seed.valid = false;
    seed.basis.valid = false;
    seed.basis.u = cv::Point2f(0.0f, 0.0f);
    seed.basis.v = cv::Point2f(0.0f, 0.0f);
    seed.basis.windowCenter = cv::Point2f(0.0f, 0.0f);
    seed.basis.windowSide = 0.0f;
    seed.basis.peakSharpness = 0.0f;

    if (corners.size() < kWindowMinPoints) {
        seed.status = "Too few corners detected to look for a lattice.";
        return seed;
    }

    // The window is centered, not searched for. The field protocol has the board covering the
    // middle of the frame, and the middle is also where radial distortion is weakest, so the
    // assumption that one basis describes the whole window holds best there. An earlier
    // version tiled windows across the frame and scored them, which was both unnecessary and
    // actively wrong: the score it used rises as a window shrinks, because a smaller window
    // has fewer long-range pairs and less distortion smearing, so it always chose the
    // smallest window offered.
    const cv::Point2f center((float)imageSize.width / 2.0f, (float)imageSize.height / 2.0f);
    const double maxSide = std::min((double)imageSize.width, (double)imageSize.height);

    // Sizes are tried smallest first, and the first one yielding a solid patch wins. This is
    // not a search for where the board is; it is an escalation to take in enough cells when
    // the board is coarse, since a window has to span several cells to have a lattice at all.
    std::vector<double> sides;
    if (hint.provided) {
        const double hintedStep = vectorLength(cv::Point2f(hint.to.x - hint.from.x, hint.to.y - hint.from.y));
        if (hintedStep > 1e-3) sides.push_back(std::min(kWindowCells * hintedStep, maxSide));
    }
    for (int f = 0; f < kWindowWidthFractionCount; f++) {
        sides.push_back(std::min(imageSize.width * kWindowWidthFractions[f], maxSide));
    }

    const cv::Point2f windowCenter = hint.provided ? hint.from : center;

    SeedPatch bestPatch;
    cv::Point2f bestU(0.0f, 0.0f), bestV(0.0f, 0.0f);
    double bestSide = 0.0, bestStep = 0.0, bestSharpness = 0.0;
    bool haveBasis = false;
    bool bestAligned = false;
    double bestMisalignment = 0.0;
    bool sawConflict = false;
    std::ostringstream attempts;

    for (size_t s = 0; s < sides.size(); s++) {
        const double side = sides[s];
        if (side < 32.0) continue;

        std::vector<int> subset;
        for (size_t i = 0; i < corners.size(); i++) {
            const cv::Point2f &p = corners[i].position;
            if (std::fabs(p.x - windowCenter.x) <= side / 2.0 &&
                std::fabs(p.y - windowCenter.y) <= side / 2.0) subset.push_back((int)i);
        }
        attempts.setf(std::ios::fixed);
        attempts.precision(0);
        attempts << " [" << (int)side << "px/" << subset.size() << "pts:";
        if (subset.size() < kWindowMinPoints) {
            attempts << " too few points]";
            continue;
        }

        // First pass: a generous radius, to discover the lattice step rather than assume it.
        // The step is taken from the *strongest* peak, not the shortest one. On a window
        // holding only a few dozen corners the histogram is sparse, and "shortest peak above
        // a fraction of the maximum" will happily select a noise bin at short range, which
        // then sizes the second pass too small to contain the real basis at all. The nearest
        // neighbour displacement is by construction the most populated bin, which is a far
        // sturdier statistic.
        std::vector<HistogramPeak> coarsePeaks;
        displacementPeaks(corners, subset, side * kCoarseRadiusFraction, kCoarseHistogramBins,
                          kCoarsePeakMinFraction, &coarsePeaks);
        if (coarsePeaks.empty()) {
            attempts << " no coarse peaks]";
            continue;
        }
        double step = 0.0;
        double strongestCoarse = -1.0;
        for (size_t i = 0; i < coarsePeaks.size(); i++) {
            const double len = vectorLength(coarsePeaks[i].displacement);
            if (len > 1e-6 && coarsePeaks[i].count > strongestCoarse) {
                strongestCoarse = coarsePeaks[i].count;
                step = len;
            }
        }
        if (step <= 1e-6) {
            attempts << " no usable step]";
            continue;
        }
        attempts << " step=" << step;

        // Second pass: re-bin tightly around the discovered step, for a precise basis.
        const double fineRadius = kFineRadiusFactor * step;
        std::vector<HistogramPeak> peaks;
        const double sharpness = displacementPeaks(corners, subset, fineRadius, kFineHistogramBins,
                                                   kPeakMinFraction, &peaks);
        attempts << " peaks=" << peaks.size();
        cv::Point2f u, v;
        if (!selectBasis(peaks, &u, &v)) {
            attempts << " no basis]";
            continue;
        }
        attempts << " |u|=" << vectorLength(u) << " |v|=" << vectorLength(v);

        // A real two-dimensional lattice also shows peaks at the cell diagonals. A row of
        // evenly spaced bolts or a grating is periodic in one direction only and has none, so
        // finding one is enough to rule that out. Requiring both was too strict under strong
        // fisheye, where the longer diagonal displacement smears across more bins than the
        // basis vectors do.
        double strongest = 0.0;
        for (size_t i = 0; i < peaks.size(); i++) if (peaks[i].count > strongest) strongest = peaks[i].count;
        const double diagonalTolerance = 0.3 * std::min(vectorLength(u), vectorLength(v));
        const cv::Point2f sum(u.x + v.x, u.y + v.y);
        const cv::Point2f diff(u.x - v.x, u.y - v.y);
        int diagonalsInRange = 0;
        int diagonalsFound = 0;
        if (vectorLength(sum) < fineRadius) {
            diagonalsInRange++;
            if (peakExistsNear(peaks, sum, diagonalTolerance, kDiagonalMinFraction * strongest)) diagonalsFound++;
        }
        if (vectorLength(diff) < fineRadius) {
            diagonalsInRange++;
            if (peakExistsNear(peaks, diff, diagonalTolerance, kDiagonalMinFraction * strongest)) diagonalsFound++;
        }
        if (diagonalsInRange > 0 && diagonalsFound == 0) {
            attempts << " no diagonals]";
            continue;
        }

        // A hint fixes the first basis direction outright: the user has said which way the
        // grid runs, which beats any automatic choice.
        if (hint.provided) {
            const cv::Point2f hinted(hint.to.x - hint.from.x, hint.to.y - hint.from.y);
            if (vectorLength(hinted) > 1e-3) {
                const double cross = (double)hinted.x * v.y - (double)hinted.y * v.x;
                if (std::fabs(cross) / (vectorLength(hinted) * vectorLength(v)) >= kMinSinAngle) u = hinted;
            }
        }

        const SeedPatch patch = labelSeedPatch(corners, subset, u, v);
        const double misalignment = basisMisalignmentDegrees(u, v);
        const bool aligned = (misalignment <= kMaxBasisMisalignmentDegrees);
        attempts << " off-axis=" << misalignment << "deg patch=" << patch.cornerIndex.size()
                 << (patch.conflict ? " CONFLICT]" : "]");
        if (patch.conflict) {
            sawConflict = true;
            continue;
        }

        // Alignment outranks patch size. Comparing on patch size alone let a single window
        // that had locked onto the grid diagonals beat two windows that agreed with each other
        // on the true basis, purely by growing a larger patch from it -- 16 corners against 7.
        // Every row and column downstream then ran diagonally across the board. A window whose
        // basis is diagonal is not a better reading of the same grid; it is a reading of a
        // different grid, so no patch grown from it should be allowed to win.
        if (!haveBasis || (aligned && !bestAligned) ||
            (aligned == bestAligned && patch.cornerIndex.size() > bestPatch.cornerIndex.size())) {
            bestPatch = patch;
            bestU = u;
            bestV = v;
            bestSide = side;
            bestStep = step;
            bestSharpness = sharpness;
            bestAligned = aligned;
            bestMisalignment = misalignment;
            haveBasis = true;
        }
        // Only stop early on a patch that is both big enough and aligned; otherwise a large
        // diagonal patch found first would end the search before an aligned window is tried.
        if (bestAligned && bestPatch.cornerIndex.size() >= kGoodSeedPatchPoints) break;
    }

    if (!haveBasis) {
        std::ostringstream message;
        message << "No lattice found in the center of the frame among " << corners.size() << " corners.";
        if (sawConflict) {
            message << " A basis was found but produced inconsistent grid coordinates, which means "
                    << "the basis or the matching tolerance is wrong.";
        } else {
            message << " No window produced a displacement histogram with two non-collinear peaks "
                    << "and matching diagonals. Tried:" << attempts.str();
        }
        seed.status = message.str();
        return seed;
    }

    seed.basis.u = bestU;
    seed.basis.v = bestV;
    seed.basis.windowCenter = windowCenter;
    seed.basis.windowSide = (float)bestSide;
    seed.basis.peakSharpness = (float)bestSharpness;
    seed.basis.valid = true;

    if (bestPatch.cornerIndex.size() < kMinFullyConsistentPoints) {
        std::ostringstream message;
        message.setf(std::ios::fixed);
        message.precision(1);
        message << "Basis found (|u| = " << vectorLength(bestU) << " px, |v| = " << vectorLength(bestV)
                << " px) but only " << bestPatch.cornerIndex.size() << " corners form a connected "
                << "lattice, so the basis is probably wrong. Tried:" << attempts.str();
        seed.status = message.str();
        return seed;
    }

    seed.cornerIndex = bestPatch.cornerIndex;
    seed.ij = bestPatch.ij;

    std::ostringstream message;
    message.setf(std::ios::fixed);
    message.precision(1);
    message << "u = (" << bestU.x << ", " << bestU.y << "), |u| = " << vectorLength(bestU) << " px; "
            << "v = (" << bestV.x << ", " << bestV.y << "), |v| = " << vectorLength(bestV) << " px. "
            << "Seed patch: " << seed.cornerIndex.size() << " corners spanning "
            << bestPatch.extentI << " x " << bestPatch.extentJ << " cells";
    if (bestPatch.duplicatesDropped > 0) {
        message << " (" << bestPatch.duplicatesDropped << " near-duplicate corner"
                << (bestPatch.duplicatesDropped == 1 ? "" : "s") << " dropped)";
    }
    message << ". Grid runs " << bestMisalignment << " deg off the image axes";
    if (!bestAligned) {
        message << ", which is further than the " << kMaxBasisMisalignmentDegrees
                << " deg expected of a board aligned to the cameras -- no window found a better "
                << "aligned basis, so check that the rows and columns drawn on screen follow the "
                << "board rather than its diagonals";
    }
    message << ". Centered window "
            << (int)bestSide << " px = " << (bestStep > 1e-6 ? bestSide / bestStep : 0.0)
            << " cells; histogram peak sharpness " << bestSharpness << ". Tried:" << attempts.str();
    seed.status = message.str();
    seed.valid = true;
    return seed;
}

// --- Stage D: grid growth -----------------------------------------------------------

namespace {

// How close a corner must lie to its predicted position to be accepted, as a fraction of
// the local cell spacing. This doubles as the smoothness test: when three corners are
// already placed along a line the prediction is the constant-third-difference
// extrapolation, so the residual against it *is* the third difference, which stays near
// zero along a smoothly curving grid line however strong the curvature.
const double kGrowthTolerance = 0.30;

// Guards against a runaway walk into clutter beyond the board.
const int kMaxGrowthRounds = 200;
const int kMaxLatticeSpan = 400;

long long siteKey(int i, int j)
{
    return (long long)(i + 100000) * 1000000LL + (long long)(j + 100000);
}

// Component-wise median, which shrugs off one bad prediction among several.
cv::Point2f medianPoint(std::vector<cv::Point2f> &values)
{
    const size_t n = values.size();
    std::vector<float> xs(n), ys(n);
    for (size_t i = 0; i < n; i++) {
        xs[i] = values[i].x;
        ys[i] = values[i].y;
    }
    std::sort(xs.begin(), xs.end());
    std::sort(ys.begin(), ys.end());
    return cv::Point2f(xs[n / 2], ys[n / 2]);
}

struct SitePrediction {
    cv::Point2f position;
    double spacing;   // Local cell spacing near this site, for scaling the tolerance.
    int tier;         // 3 curvature-aware, 2 linear, 1 basis-only, 0 none.
};

// Predicts where the corner at (i, j) should be, from the corners already placed nearby.
//
// Predictions are tiered rather than pooled, because a weak predictor mixed into an
// average drags a good one off. Tier 3 covers the two forms that cancel curvature to
// second order: the constant-third-difference extrapolation along a line, and the
// parallelogram rule, which is exact for any affine grid. Tier 2 is straight-line
// extrapolation from two corners, which under fisheye is biased outward on the convex
// side. Tier 1 steps one basis vector from a single neighbour and is a last resort,
// biased for the same reason.
SitePrediction predictSite(const std::map<long long, int> &siteToCorner,
                           const std::vector<CornerCandidate> &corners,
                           int i, int j,
                           const cv::Point2f &u, const cv::Point2f &v)
{
    SitePrediction result;
    result.position = cv::Point2f(0.0f, 0.0f);
    result.spacing = 0.0;
    result.tier = 0;

    const int di[4] = {1, -1, 0, 0};
    const int dj[4] = {0, 0, 1, -1};

    std::vector<cv::Point2f> tier3, tier2, tier1;
    std::vector<double> spacings;

    for (int d = 0; d < 4; d++) {
        // Corners lying back along this axis from the site, at one, two and three steps.
        const cv::Point2f *p1 = 0;
        const cv::Point2f *p2 = 0;
        const cv::Point2f *p3 = 0;
        std::map<long long, int>::const_iterator it;
        it = siteToCorner.find(siteKey(i - di[d], j - dj[d]));
        if (it != siteToCorner.end()) p1 = &corners[it->second].position;
        it = siteToCorner.find(siteKey(i - 2 * di[d], j - 2 * dj[d]));
        if (it != siteToCorner.end()) p2 = &corners[it->second].position;
        it = siteToCorner.find(siteKey(i - 3 * di[d], j - 3 * dj[d]));
        if (it != siteToCorner.end()) p3 = &corners[it->second].position;

        if (p1 && p2) spacings.push_back(vectorLength(cv::Point2f(p1->x - p2->x, p1->y - p2->y)));

        if (p1 && p2 && p3) {
            tier3.push_back(cv::Point2f(p3->x - 3.0f * p2->x + 3.0f * p1->x,
                                        p3->y - 3.0f * p2->y + 3.0f * p1->y));
        } else if (p1 && p2) {
            tier2.push_back(cv::Point2f(2.0f * p1->x - p2->x, 2.0f * p1->y - p2->y));
        } else if (p1) {
            const cv::Point2f step = (d < 2) ? cv::Point2f(u.x * di[d], u.y * di[d])
                                             : cv::Point2f(v.x * dj[d], v.y * dj[d]);
            tier1.push_back(cv::Point2f(p1->x + step.x, p1->y + step.y));
        }
    }

    // Parallelogram rule over each pair of perpendicular directions: with the three other
    // corners of a cell known, the fourth follows exactly for an affine grid.
    const int cornerI[4] = {1, 1, -1, -1};
    const int cornerJ[4] = {1, -1, 1, -1};
    for (int c = 0; c < 4; c++) {
        std::map<long long, int>::const_iterator a = siteToCorner.find(siteKey(i - cornerI[c], j));
        std::map<long long, int>::const_iterator b = siteToCorner.find(siteKey(i, j - cornerJ[c]));
        std::map<long long, int>::const_iterator ab = siteToCorner.find(siteKey(i - cornerI[c], j - cornerJ[c]));
        if (a == siteToCorner.end() || b == siteToCorner.end() || ab == siteToCorner.end()) continue;
        const cv::Point2f &pa = corners[a->second].position;
        const cv::Point2f &pb = corners[b->second].position;
        const cv::Point2f &pab = corners[ab->second].position;
        tier3.push_back(cv::Point2f(pa.x + pb.x - pab.x, pa.y + pb.y - pab.y));
        spacings.push_back(vectorLength(cv::Point2f(pa.x - pab.x, pa.y - pab.y)));
    }

    std::vector<cv::Point2f> *chosen = 0;
    if (!tier3.empty()) { chosen = &tier3; result.tier = 3; }
    else if (!tier2.empty()) { chosen = &tier2; result.tier = 2; }
    else if (!tier1.empty()) { chosen = &tier1; result.tier = 1; }
    if (!chosen) return result;

    result.position = medianPoint(*chosen);
    if (spacings.empty()) {
        result.spacing = std::min(vectorLength(u), vectorLength(v));
    } else {
        std::sort(spacings.begin(), spacings.end());
        result.spacing = spacings[spacings.size() / 2];
    }
    return result;
}

}   // anonymous namespace

GrownLattice growLattice(const std::vector<CornerCandidate> &corners,
                         const SeedLattice &seed,
                         cv::Size imageSize)
{
    GrownLattice grown;
    if (!seed.valid || seed.cornerIndex.empty()) {
        grown.status = "No seed lattice to grow from.";
        return grown;
    }

    // Every corner is a candidate for placement, so the lookup covers the whole cloud.
    std::vector<int> all;
    all.reserve(corners.size());
    for (size_t i = 0; i < corners.size(); i++) all.push_back((int)i);
    const double cellSize = std::min(vectorLength(seed.basis.u), vectorLength(seed.basis.v));
    PointLookup lookup(corners, all, std::max(cellSize * kGrowthTolerance, 1.0));

    std::map<long long, int> siteToCorner;
    std::vector<bool> claimed(corners.size(), false);
    for (size_t k = 0; k < seed.cornerIndex.size(); k++) {
        siteToCorner[siteKey(seed.ij[k].x, seed.ij[k].y)] = seed.cornerIndex[k];
        claimed[seed.cornerIndex[k]] = true;
    }
    const size_t seedSize = siteToCorner.size();

    int minI = seed.ij[0].x, maxI = seed.ij[0].x, minJ = seed.ij[0].y, maxJ = seed.ij[0].y;
    for (size_t k = 0; k < seed.ij.size(); k++) {
        minI = std::min(minI, seed.ij[k].x);
        maxI = std::max(maxI, seed.ij[k].x);
        minJ = std::min(minJ, seed.ij[k].y);
        maxJ = std::max(maxJ, seed.ij[k].y);
    }

    int round = 0;
    for (; round < kMaxGrowthRounds; round++) {
        // Collect the empty sites adjacent to filled ones. Gathering the whole ring before
        // placing anything keeps the result independent of the order sites are visited,
        // which the old nearest-neighbour walk was notoriously sensitive to.
        std::vector<cv::Point2i> frontier;
        {
            std::map<long long, bool> seen;
            const int di[4] = {1, -1, 0, 0};
            const int dj[4] = {0, 0, 1, -1};
            for (std::map<long long, int>::const_iterator it = siteToCorner.begin();
                 it != siteToCorner.end(); ++it) {
                const int i = (int)(it->first / 1000000LL) - 100000;
                const int j = (int)(it->first % 1000000LL) - 100000;
                for (int d = 0; d < 4; d++) {
                    const int ni = i + di[d];
                    const int nj = j + dj[d];
                    if (ni < minI - kMaxLatticeSpan || ni > maxI + kMaxLatticeSpan) continue;
                    if (nj < minJ - kMaxLatticeSpan || nj > maxJ + kMaxLatticeSpan) continue;
                    const long long key = siteKey(ni, nj);
                    if (siteToCorner.count(key)) continue;
                    if (seen.count(key)) continue;
                    seen[key] = true;
                    frontier.push_back(cv::Point2i(ni, nj));
                }
            }
        }
        if (frontier.empty()) break;

        // Score every frontier site first, then commit. Where two sites want the same
        // corner, the better fit takes it and the other is left for a later round.
        std::map<int, size_t> cornerClaim;      // corner index -> index into `proposals`
        std::vector<cv::Point2i> proposalSite;
        std::vector<int> proposalCorner;
        std::vector<double> proposalResidual;

        for (size_t f = 0; f < frontier.size(); f++) {
            const int i = frontier[f].x;
            const int j = frontier[f].y;
            const SitePrediction pred = predictSite(siteToCorner, corners, i, j, seed.basis.u, seed.basis.v);
            if (pred.tier == 0 || pred.spacing <= 1e-6) continue;
            if (pred.position.x < 0.0f || pred.position.y < 0.0f ||
                pred.position.x >= imageSize.width || pred.position.y >= imageSize.height) continue;

            const double tolerance = kGrowthTolerance * pred.spacing;
            const int slot = lookup.nearestWithinExcluding(pred.position, tolerance, claimed);
            if (slot < 0) continue;
            const int cornerIdx = all[slot];
            const cv::Point2f &p = corners[cornerIdx].position;
            const double residual = vectorLength(cv::Point2f(p.x - pred.position.x, p.y - pred.position.y));

            std::map<int, size_t>::iterator existing = cornerClaim.find(cornerIdx);
            if (existing != cornerClaim.end()) {
                if (residual < proposalResidual[existing->second]) {
                    proposalSite[existing->second] = frontier[f];
                    proposalResidual[existing->second] = residual;
                }
                continue;
            }
            cornerClaim[cornerIdx] = proposalSite.size();
            proposalSite.push_back(frontier[f]);
            proposalCorner.push_back(cornerIdx);
            proposalResidual.push_back(residual);
        }

        if (proposalCorner.empty()) break;

        for (size_t k = 0; k < proposalCorner.size(); k++) {
            siteToCorner[siteKey(proposalSite[k].x, proposalSite[k].y)] = proposalCorner[k];
            claimed[proposalCorner[k]] = true;
            minI = std::min(minI, proposalSite[k].x);
            maxI = std::max(maxI, proposalSite[k].x);
            minJ = std::min(minJ, proposalSite[k].y);
            maxJ = std::max(maxJ, proposalSite[k].y);
        }
    }

    for (std::map<long long, int>::const_iterator it = siteToCorner.begin(); it != siteToCorner.end(); ++it) {
        grown.cornerIndex.push_back(it->second);
        grown.ij.push_back(cv::Point2i((int)(it->first / 1000000LL) - 100000,
                                       (int)(it->first % 1000000LL) - 100000));
    }
    grown.basis = seed.basis;
    grown.minI = minI;
    grown.maxI = maxI;
    grown.minJ = minJ;
    grown.maxJ = maxJ;
    grown.rounds = round;
    grown.valid = true;

    const int spanI = maxI - minI + 1;
    const int spanJ = maxJ - minJ + 1;
    std::ostringstream message;
    message.setf(std::ios::fixed);
    message.precision(0);
    message << "Grew " << seedSize << " seed corners to " << grown.cornerIndex.size() << " over "
            << round << " rounds, spanning " << spanI << " x " << spanJ << " cells ("
            << (spanI * spanJ - (int)grown.cornerIndex.size()) << " holes). Used "
            << grown.cornerIndex.size() * 100 / (corners.empty() ? 1 : corners.size())
            << "% of the " << corners.size() << " detected corners.";
    grown.status = message.str();
    return grown;
}

std::vector<Plumbline> extractPlumblines(const std::vector<CornerCandidate> &corners,
                                         const GrownLattice &lattice,
                                         int minPoints)
{
    std::vector<Plumbline> lines;
    if (!lattice.valid) return lines;

    // Rows share a j and vary in i; columns the other way. A missing site is not a break,
    // since the corners either side of it still lie on the same straight world line.
    for (int pass = 0; pass < 2; pass++) {
        const bool isRow = (pass == 0);
        const int from = isRow ? lattice.minJ : lattice.minI;
        const int to = isRow ? lattice.maxJ : lattice.maxI;
        for (int fixed = from; fixed <= to; fixed++) {
            std::vector<std::pair<int, int> > along;   // varying coordinate, corner index
            for (size_t k = 0; k < lattice.ij.size(); k++) {
                if (isRow) {
                    if (lattice.ij[k].y != fixed) continue;
                    along.push_back(std::make_pair(lattice.ij[k].x, lattice.cornerIndex[k]));
                } else {
                    if (lattice.ij[k].x != fixed) continue;
                    along.push_back(std::make_pair(lattice.ij[k].y, lattice.cornerIndex[k]));
                }
            }
            if ((int)along.size() < minPoints) continue;
            std::sort(along.begin(), along.end());
            Plumbline line;
            line.isRow = isRow;
            line.index = fixed;
            for (size_t k = 0; k < along.size(); k++) line.points.push_back(corners[along[k].second].position);
            lines.push_back(line);
        }
    }
    return lines;
}

// --- Stage E: curve-fit refinement --------------------------------------------------

namespace {

// Two passes is almost always enough: the fits improve once the worst outliers are gone,
// and a third pass has nothing left to find.
const int kRefinementPasses = 2;

// A corner is expelled when its deviation exceeds this many robust standard deviations of
// the deviations along its line, but never for a deviation below the absolute floor. Without
// the floor, a line whose corners all sit within a hundredth of a cell of their estimates
// would have its own sub-pixel jitter treated as gross error. Measured on real frames, good
// corners deviate by a median of 0.0025 of a cell and a 99th percentile of 0.016, then there
// is an empty gap before the one genuinely misplaced corner per frame at 0.07 and 0.106. The
// floor sits in that gap. Three sigma alone would be about 0.011 here and would cut into the
// legitimate tail, since the deviations are heavier tailed than a normal distribution; the
// sigma term only takes over on frames whose corners are noisier than these.
const double kOutlierSigmas = 3.0;
const double kMinOutlierDeviation = 0.05;

// How far from a predicted site to accept an already-detected corner, and how far to let a
// direct image search move, both as fractions of the cell spacing.
// Both are tight because the prediction is good: leave-one-out estimates land within about
// 0.0025 of a cell of where corners actually are. A loose search radius lets the image search
// snap back onto the very corner just expelled, which sits only a few hundredths of a cell
// away, quietly undoing the expulsion.
const double kRecoveryMatchFraction = 0.10;
const double kRecoverySearchFraction = 0.06;

// Estimates where a corner should sit from its two neighbours either side along a line, and
// returns how far it actually sits from that estimate, as a fraction of the local spacing.
//
// The four-point centered estimate (-p[-2] + 4p[-1] + 4p[+1] - p[+2]) / 6 is exact for any
// cubic, so along a smoothly curving grid line it is unbiased however strong the curvature,
// and the deviation it reports is close to zero for every corner that belongs there.
//
// This replaced fitting a polynomial to the whole line and measuring residuals from it, which
// the reference design calls for but which does not work here. A cubic cannot represent a
// fisheye-distorted line exactly, so its residuals carry systematic model error that inflates
// the robust scale, and a single corner displaced a few pixels along a line 1500 px long is
// partly absorbed by the fit. Leaving the corner out of its own estimate makes the test local
// and removes the model error at once.
bool leaveOneOutDeviations(const std::map<int, int> &alongLine,
                           const std::vector<CornerCandidate> &corners,
                           std::map<int, double> *deviations)
{
    deviations->clear();
    for (std::map<int, int>::const_iterator it = alongLine.begin(); it != alongLine.end(); ++it) {
        const int k = it->first;
        // The stencil needs both neighbours on each side to be present at consecutive lattice
        // indices; across a hole the spacing is unequal and the formula does not hold.
        std::map<int, int>::const_iterator m2 = alongLine.find(k - 2);
        std::map<int, int>::const_iterator m1 = alongLine.find(k - 1);
        std::map<int, int>::const_iterator p1 = alongLine.find(k + 1);
        std::map<int, int>::const_iterator p2 = alongLine.find(k + 2);
        if (m2 == alongLine.end() || m1 == alongLine.end() ||
            p1 == alongLine.end() || p2 == alongLine.end()) continue;

        const cv::Point2f &a = corners[m2->second].position;
        const cv::Point2f &b = corners[m1->second].position;
        const cv::Point2f &c = corners[p1->second].position;
        const cv::Point2f &d = corners[p2->second].position;
        const cv::Point2f estimate((-a.x + 4.0f * b.x + 4.0f * c.x - d.x) / 6.0f,
                                   (-a.y + 4.0f * b.y + 4.0f * c.y - d.y) / 6.0f);
        const cv::Point2f &actual = corners[it->second].position;
        const double spacing = 0.5 * vectorLength(cv::Point2f(c.x - b.x, c.y - b.y));
        if (spacing < 1e-6) continue;
        (*deviations)[k] = vectorLength(cv::Point2f(actual.x - estimate.x, actual.y - estimate.y)) / spacing;
    }
    return !deviations->empty();
}

// 1.4826 scales the median absolute deviation to a standard deviation for normally
// distributed data, and unlike a plain standard deviation it is not inflated by the very
// outliers being looked for.
double robustScale(std::vector<double> values)
{
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    return 1.4826 * values[values.size() / 2];
}

}   // anonymous namespace

RefinementResult refineLattice(std::vector<CornerCandidate> &corners,
                               const GrownLattice &latticeIn,
                               const cv::Mat &gray)
{
    RefinementResult result;
    result.lattice = latticeIn;
    if (!latticeIn.valid || latticeIn.cornerIndex.empty()) {
        result.status = "No lattice to refine.";
        return result;
    }

    cv::Mat gray32;
    prepareImage(gray, &gray32);

    std::map<long long, int> site;
    for (size_t k = 0; k < latticeIn.cornerIndex.size(); k++) {
        site[siteKey(latticeIn.ij[k].x, latticeIn.ij[k].y)] = latticeIn.cornerIndex[k];
    }

    const cv::Point2f u = latticeIn.basis.u;
    const cv::Point2f v = latticeIn.basis.v;
    const double cellSize = std::min(vectorLength(u), vectorLength(v));
    if (cellSize < 1e-6) {
        result.status = "Lattice has no usable basis; refinement skipped.";
        return result;
    }

    // Corners already placed cannot be reused elsewhere; ones dropped as outliers can be,
    // since a later pass may find they fit a different site properly.
    std::vector<bool> claimed(corners.size(), false);
    for (std::map<long long, int>::const_iterator it = site.begin(); it != site.end(); ++it) {
        claimed[it->second] = true;
    }

    int minI = latticeIn.minI, maxI = latticeIn.maxI, minJ = latticeIn.minJ, maxJ = latticeIn.maxJ;

    // Corners already judged not to belong at a given site, so that filling the hole left
    // behind cannot undo the expulsion that created it.
    std::map<long long, std::set<int> > rejected;
    std::map<long long, std::vector<cv::Point2f> > rejectedPositions;
    int holesFilled = 0;

    for (int pass = 0; pass < kRefinementPasses; pass++) {
        result.passes = pass + 1;
        int removedThisPass = 0;
        int recoveredThisPass = 0;
        int filledThisPass = 0;

        // --- Expel corners that sit off their line -----------------------------------
        // A corner belongs to both a row and a column, and being a gross outlier on either
        // is disqualifying, so the two verdicts are combined before anything is removed.
        std::map<long long, bool> expel;
        for (int orientation = 0; orientation < 2; orientation++) {
            const bool isRow = (orientation == 0);
            const int from = isRow ? minJ : minI;
            const int to = isRow ? maxJ : maxI;
            for (int fixed = from; fixed <= to; fixed++) {
                std::map<int, int> alongLine;
                const int varyFrom = isRow ? minI : minJ;
                const int varyTo = isRow ? maxI : maxJ;
                for (int varying = varyFrom; varying <= varyTo; varying++) {
                    const long long key = isRow ? siteKey(varying, fixed) : siteKey(fixed, varying);
                    std::map<long long, int>::const_iterator it = site.find(key);
                    if (it != site.end()) alongLine[varying] = it->second;
                }
                std::map<int, double> deviations;
                if (!leaveOneOutDeviations(alongLine, corners, &deviations)) continue;
                std::vector<double> values;
                for (std::map<int, double>::const_iterator it = deviations.begin();
                     it != deviations.end(); ++it) values.push_back(it->second);
                const double threshold = std::max(kOutlierSigmas * robustScale(values), kMinOutlierDeviation);
                for (std::map<int, double>::const_iterator it = deviations.begin();
                     it != deviations.end(); ++it) {
                    if (it->second <= threshold) continue;
                    expel[isRow ? siteKey(it->first, fixed) : siteKey(fixed, it->first)] = true;
                }
            }
        }
        for (std::map<long long, bool>::const_iterator it = expel.begin(); it != expel.end(); ++it) {
            std::map<long long, int>::iterator found = site.find(it->first);
            if (found == site.end()) continue;
            // Remember the pairing, so the hole-filling below cannot simply take the same
            // corner back: it is still the nearest thing to the position predicted for that
            // site, which is how it came to be placed there in the first place.
            rejected[it->first].insert(found->second);
            rejectedPositions[it->first].push_back(corners[found->second].position);
            claimed[found->second] = false;
            site.erase(found);
            removedThisPass++;
        }

        // --- Fill holes, and reach one ring beyond the current extent -----------------
        std::vector<int> allCorners;
        allCorners.reserve(corners.size());
        for (size_t k = 0; k < corners.size(); k++) allCorners.push_back((int)k);
        PointLookup lookup(corners, allCorners, std::max(cellSize * kRecoveryMatchFraction, 1.0));

        for (int j = minJ - 1; j <= maxJ + 1; j++) {
            for (int i = minI - 1; i <= maxI + 1; i++) {
                if (site.count(siteKey(i, j))) continue;
                const SitePrediction predicted = predictSite(site, corners, i, j, u, v);
                if (predicted.tier < 2 || predicted.spacing <= 1e-6) continue;   // too little context
                const cv::Point2f p = predicted.position;
                if (p.x < 1.0f || p.y < 1.0f || p.x >= gray.cols - 1.0f || p.y >= gray.rows - 1.0f) continue;

                const long long key = siteKey(i, j);
                // Prefer a corner the detector already found near the prediction, unless it
                // is the one just expelled from this very site.
                const int slot = lookup.nearestWithinExcluding(p, kRecoveryMatchFraction * predicted.spacing, claimed);
                if (slot >= 0 && !(rejected.count(key) && rejected[key].count(allCorners[slot]))) {
                    site[key] = allCorners[slot];
                    claimed[allCorners[slot]] = true;
                    filledThisPass++;
                    continue;
                }

                // Otherwise look in the image itself. Corners the detector missed are common
                // near the frame edges, which is exactly where they matter most for measuring
                // distortion, so it is worth the second look now that the grid says where to
                // aim. Anything found must still pass the same appearance test as the rest.
                const int px = (int)(p.x + 0.5f);
                const int py = (int)(p.y + 0.5f);
                const int margin = kSubPixelRadius + 1;
                if (px < margin || py < margin || px >= gray.cols - margin || py >= gray.rows - margin) continue;
                cv::Point2f refined;
                if (!subPixelSaddle(gray32, px, py, &refined)) continue;
                // The index blacklist does not cover a corner manufactured afresh at the same
                // spot, so compare positions too.
                bool nearRejected = false;
                std::map<long long, std::vector<cv::Point2f> >::const_iterator rp = rejectedPositions.find(key);
                if (rp != rejectedPositions.end()) {
                    for (size_t r = 0; r < rp->second.size(); r++) {
                        if (vectorLength(cv::Point2f(refined.x - rp->second[r].x,
                                                     refined.y - rp->second[r].y)) < 0.03 * predicted.spacing) {
                            nearRejected = true;
                            break;
                        }
                    }
                }
                if (nearRejected) continue;
                if (vectorLength(cv::Point2f(refined.x - p.x, refined.y - p.y)) >
                    kRecoverySearchFraction * predicted.spacing) continue;
                const int radius = std::max(3, (int)(0.4 * predicted.spacing));
                const int rx = (int)(refined.x + 0.5f);
                const int ry = (int)(refined.y + 0.5f);
                if (rx - radius < 0 || ry - radius < 0 || rx + radius >= gray.cols || ry + radius >= gray.rows) continue;
                const std::vector<QuadrantMask> bank = buildMaskBank(radius, kOrientationCount);
                if (bestScoreOverOrientations(gray32, rx, ry, bank) < kMinScore) continue;

                CornerCandidate recovered;
                recovered.position = refined;
                recovered.score = (float)kMinScore;
                corners.push_back(recovered);
                claimed.push_back(true);
                site[key] = (int)corners.size() - 1;
                recoveredThisPass++;
            }
        }

        result.outliersRemoved += removedThisPass;
        result.cornersRecovered += recoveredThisPass;
        holesFilled += filledThisPass;

        for (std::map<long long, int>::const_iterator it = site.begin(); it != site.end(); ++it) {
            const int i = (int)(it->first / 1000000LL) - 100000;
            const int j = (int)(it->first % 1000000LL) - 100000;
            minI = std::min(minI, i);
            maxI = std::max(maxI, i);
            minJ = std::min(minJ, j);
            maxJ = std::max(maxJ, j);
        }

        if (removedThisPass == 0 && recoveredThisPass == 0 && filledThisPass == 0) break;
    }

    GrownLattice out;
    out.basis = latticeIn.basis;
    for (std::map<long long, int>::const_iterator it = site.begin(); it != site.end(); ++it) {
        out.cornerIndex.push_back(it->second);
        out.ij.push_back(cv::Point2i((int)(it->first / 1000000LL) - 100000,
                                     (int)(it->first % 1000000LL) - 100000));
    }
    out.minI = minI;
    out.maxI = maxI;
    out.minJ = minJ;
    out.maxJ = maxJ;
    out.rounds = latticeIn.rounds;
    out.valid = true;
    out.status = latticeIn.status;
    result.lattice = out;

    std::ostringstream message;
    message << "Refinement over " << result.passes << " pass" << (result.passes == 1 ? "" : "es")
            << ": removed " << result.outliersRemoved << " corners lying off their line, filled "
            << holesFilled << " holes from corners already detected, and recovered "
            << result.cornersRecovered << " more by searching the image where the grid predicted "
            << "a corner. Lattice now " << out.cornerIndex.size() << " corners.";
    result.status = message.str();
    return result;
}

std::vector<std::vector<cv::Point2f> > extractDiagonalRuns(const std::vector<CornerCandidate> &corners,
                                                           const GrownLattice &lattice,
                                                           int minPoints)
{
    std::vector<std::vector<cv::Point2f> > runs;
    if (!lattice.valid) return runs;

    std::map<long long, int> site;
    for (size_t k = 0; k < lattice.ij.size(); k++) {
        site[siteKey(lattice.ij[k].x, lattice.ij[k].y)] = lattice.cornerIndex[k];
    }

    // Both diagonal families: constant i-j runs one way, constant i+j the other.
    for (int family = 0; family < 2; family++) {
        const int step = (family == 0) ? 1 : -1;
        const int fromConstant = (family == 0) ? lattice.minI - lattice.maxJ : lattice.minI + lattice.minJ;
        const int toConstant = (family == 0) ? lattice.maxI - lattice.minJ : lattice.maxI + lattice.maxJ;
        for (int constant = fromConstant; constant <= toConstant; constant++) {
            std::vector<cv::Point2f> run;
            for (int i = lattice.minI; i <= lattice.maxI; i++) {
                const int j = (family == 0) ? (i - constant) : (constant - i);
                if (j < lattice.minJ || j > lattice.maxJ) continue;
                std::map<long long, int>::const_iterator it = site.find(siteKey(i, j));
                if (it == site.end()) continue;
                run.push_back(corners[it->second].position);
            }
            (void)step;
            if ((int)run.size() >= minPoints) runs.push_back(run);
        }
    }
    return runs;
}

}   // namespace vidsync
