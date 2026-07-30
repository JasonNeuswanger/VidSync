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

// A cheap pass discards most junk before the full sweep runs. Two radii rather than one: the
// narrow one is what makes it cheap, but on its own it rejects corners whose quadrant structure
// only exists further out. On the frame described at kSubPixelRadii, 26 of 28 known junctions in
// the sunlit half were rejected here at radius 5 alone, every one of them scoring well enough at
// radius 13 or beyond to have been accepted by the full sweep.
const int kPrefilterRadius = 5;          // the narrow radius, and what sets the frame margin
const int kPrefilterWideRadius = 13;
const int kPrefilterOrientationCount = 6;
const double kPrefilterMinScore = 0.05;

// The wide pass runs on every candidate the narrow one rejects, which is most of them, and costs
// roughly six times as much per candidate. Restricting it to neighbourhoods that are substantially
// saturated was tried, on the reasoning that the bloom is what it exists to rescue, and rejected:
// it does hold the cost down, but it also removes corners that have nothing to do with blooming.
// Gated at a saturated fraction of 0.03 it lost 36 points on one frame and 19 on another, in
// regions under 3% saturated -- corners whose structure simply exceeds 5 px, from defocus or a
// coarse cell. The predicate that actually matters is the wide score itself, so there is no cheap
// proxy for it, and detection is a one-shot operation where a few hundred milliseconds is cheaper
// than the corners.

// Minimum final appearance score. Conservative by design: later stages can reject a
// spurious point that survives, but they can never recover a real corner dropped here.
const double kMinScore = 0.15;

// Minimum black-to-white range, on a 0-1 intensity scale, for a patch to be judged at all.
// Without this the contrast normalization turns noise in flat regions into high scores.
const double kMinPatchContrast = 0.12;

// Half-widths of the sub-pixel fit window, tried in order until one yields a saddle. The
// coefficients in subPixelSaddleAtRadius() are now derived for a general radius, so this is a
// list rather than a single value; radius 2 is first so that every corner the detector already
// localised is localised identically.
//
// The fallback exists because a corner can be erased locally while remaining perfectly clear a
// little further out. Where the white squares are blown out, the highlight blooms into the black
// far enough to wipe out the crossing itself: on one frame the junctions in the sunlit half scored
// 0.000 at radii 4 and 6 and then 0.28, 0.47, 0.64 and 0.71 at radii 9, 13, 19 and 28. Within
// +-2 px of those crossings the surface is a saturated plateau, so the Hessian determinant comes
// out non-negative and the fit rejects the corner outright -- 24 of 28 known junctions there died
// at this test, against 5 of 32 in a control region with the same lighting but narrower bloom.
const int kSubPixelRadii[] = {2, 4, 6};
const int kSubPixelRadiusCount = 3;
const int kSubPixelRadius = 2;          // the first radius tried, and what sets the frame margin

// Allowed shift, per unit of fit radius. At radius 2 this is the 1.5 px the fit has always used;
// a wider window legitimately supports a proportionally larger correction.
const double kMaxSubPixelShiftPerRadius = 0.75;

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
// Least-squares fit of a + b*x + c*y + d*x^2 + e*x*y + f*y^2 over the (2r+1) square integer grid,
// returning the saddle point of that quadratic.
//
// The grid is symmetric, so the odd moments drop out and the normal equations separate into three
// independent pieces: b and c each divide by sum(x^2), e divides by sum(x^2*y^2), and the coupled
// (a, d, f) block reduces to the two expressions below. Writing A for the pixel count, B for
// sum(x^2), C for sum(x^4) and D for sum(x^2*y^2), the divisor C - D happens to equal
// C + D - 2*B*B/A at every radius, so one constant serves for both d and f. At radius 2 these come
// out to 50, 100 and 70 with a coefficient of 2 on sI, which is exactly the hand-derived form this
// replaces -- radius 2 therefore produces bit-identical results.
bool subPixelSaddleAtRadius(const cv::Mat &gray32, int x, int y, int r, cv::Point2f *out)
{
    if (r < 1) return false;
    if (x - r < 0 || y - r < 0 || x + r >= gray32.cols || y + r >= gray32.rows) return false;

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

    const double side = 2.0 * r + 1.0;
    double q2 = 0.0, q4 = 0.0;
    for (int k = -r; k <= r; k++) { q2 += (double)k * k; q4 += (double)k * k * k * k; }
    const double A = side * side;
    const double B = side * q2;
    const double C = side * q4;
    const double D = q2 * q2;
    const double K = C - D;
    if (K <= 0.0 || B <= 0.0 || D <= 0.0) return false;

    const double b = sxI / B;
    const double c = syI / B;
    const double e = sxyI / D;
    const double d = (sxxI - (B / A) * sI) / K;
    const double f = (syyI - (B / A) * sI) / K;

    // A saddle needs curvatures of opposite sign, i.e. a negative Hessian determinant.
    const double det = 4.0 * d * f - e * e;
    if (det >= -1e-12) return false;

    const double ox = (e * c - 2.0 * f * b) / det;
    const double oy = (e * b - 2.0 * d * c) / det;
    const double maxShift = kMaxSubPixelShiftPerRadius * (double)r;
    if (std::fabs(ox) > maxShift || std::fabs(oy) > maxShift) return false;

    out->x = (float)((double)x + ox);
    out->y = (float)((double)y + oy);
    return true;
}

// Localises a corner to sub-pixel accuracy, widening the fit window only if the narrow one finds
// no saddle at all. Widening is never preferred: the first radius that succeeds is used, so a
// corner that the tightest window can resolve is resolved exactly as before.
bool subPixelSaddle(const cv::Mat &gray32, int x, int y, cv::Point2f *out)
{
    for (int i = 0; i < kSubPixelRadiusCount; i++) {
        if (subPixelSaddleAtRadius(gray32, x, y, kSubPixelRadii[i], out)) return true;
    }
    return false;
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
    const std::vector<QuadrantMask> prefilterWideBank = buildMaskBank(kPrefilterWideRadius, kPrefilterOrientationCount);

    std::vector<std::vector<QuadrantMask> > scoreBanks;
    scoreBanks.reserve(kScoreRadiusCount);
    for (int r = 0; r < kScoreRadiusCount; r++) {
        scoreBanks.push_back(buildMaskBank(kScoreRadii[r], kOrientationCount));
    }

    std::vector<CornerCandidate> accepted;
    for (size_t i = 0; i < candidates.size(); i++) {
        const int x = candidates[i].x;
        const int y = candidates[i].y;

        // Cheap pass first; most junk dies here. A corner the bloom has erased shows nothing at
        // radius 5 and plenty at 13, so before giving up, look again at the wider radius, where it
        // fits inside the frame.
        if (bestScoreOverOrientations(gray32, x, y, prefilterBank) < kPrefilterMinScore) {
            const int rad = kPrefilterWideRadius;
            const bool fits = (x - rad >= 0 && y - rad >= 0 && x + rad < gray.cols && y + rad < gray.rows);
            if (!fits || bestScoreOverOrientations(gray32, x, y, prefilterWideBank) < kPrefilterMinScore) {
                result.prefilterRejectedCount++;
                continue;
            }
        }

        double best = 0.0;
        int goodScaleCount = 0;
        for (int r = 0; r < kScoreRadiusCount; r++) {
            const int radius = kScoreRadii[r];
            if (x - radius < 0 || y - radius < 0 || x + radius >= gray.cols || y + radius >= gray.rows) continue;
            const double s = bestScoreOverOrientations(gray32, x, y, scoreBanks[r]);
            if (s > best) best = s;
            if (s >= kMinScore) goodScaleCount++;
        }
        if (best < kMinScore || goodScaleCount < 2) continue;

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

// A basis further off the image axes than this is treated as suspect and only used when no
// window offers an aligned one. The field protocol calls for the board to be rotated into
// approximate alignment with the cameras, so a genuine basis is normally within a few degrees
// of the axes. Frames checked during tuning put the true board around 5 to 8 degrees, while
// scratch/debris lattices that grew into bad plumblines landed around 24 to 40 degrees.
// Keep this as a domain prior, not as a per-video tuning knob: if the board is deliberately
// placed at a steep angle, the two-point seed hint should be used.
const double kMaxBasisMisalignmentDegrees = 15.0;

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
    // Buckets live in a flat array covering the subset's own bounding box, not in a std::map keyed
    // by cell. Each query walks a fixed neighbourhood of cells, so with a map it paid a red-black
    // tree descent per cell; profiling the seed search showed 1.4 to 15 million queries per frame
    // and 89% of labelSeedPatch's time inside them, which made this the single hottest thing in the
    // detector. The array is indexed directly instead. Cells are visited in the same order and each
    // cell's contents remain in subset order, so every query makes exactly the same comparisons in
    // exactly the same sequence and the results are unchanged down to the tie-breaking.
    PointLookup(const std::vector<CornerCandidate> &corners, const std::vector<int> &subset, double cell)
        : corners_(corners), subset_(subset), cell_(cell > 1.0 ? cell : 1.0),
          minCellX_(0), minCellY_(0), cellsX_(0), cellsY_(0)
    {
        if (subset_.empty()) return;

        // A degenerate basis can ask for cells barely a pixel across, which over a window-sized
        // box would want millions of them. Coarsening keeps the array small; the span each query
        // walks is derived from cell_, so it still covers the whole radius either way.
        const size_t kMaxCells = 1u << 20;
        for (;;) {
            long long loX = 0, hiX = 0, loY = 0, hiY = 0;
            for (size_t k = 0; k < subset_.size(); k++) {
                const cv::Point2f &p = corners_[subset_[k]].position;
                const long long gx = (long long)std::floor(p.x / cell_);
                const long long gy = (long long)std::floor(p.y / cell_);
                if (k == 0) { loX = hiX = gx; loY = hiY = gy; }
                if (gx < loX) loX = gx;
                if (gx > hiX) hiX = gx;
                if (gy < loY) loY = gy;
                if (gy > hiY) hiY = gy;
            }
            minCellX_ = loX;
            minCellY_ = loY;
            cellsX_ = (int)(hiX - loX + 1);
            cellsY_ = (int)(hiY - loY + 1);
            if ((size_t)cellsX_ * (size_t)cellsY_ <= kMaxCells) break;
            cell_ *= 2.0;
        }

        // Counting sort into the flat array, which keeps each cell's contents in subset order.
        const size_t cellCount = (size_t)cellsX_ * (size_t)cellsY_;
        cellStart_.assign(cellCount + 1, 0);
        std::vector<int> cellOf(subset_.size());
        for (size_t k = 0; k < subset_.size(); k++) {
            cellOf[k] = flatCell(corners_[subset_[k]].position);
            cellStart_[(size_t)cellOf[k] + 1]++;
        }
        for (size_t c = 1; c <= cellCount; c++) cellStart_[c] += cellStart_[c - 1];
        items_.resize(subset_.size());
        std::vector<int> cursor(cellStart_.begin(), cellStart_.end() - 1);
        for (size_t k = 0; k < subset_.size(); k++) items_[(size_t)cursor[cellOf[k]]++] = (int)k;
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
            const long long ix = gx - minCellX_;
            if (ix < 0 || ix >= (long long)cellsX_) continue;
            for (long long gy = by - span; gy <= by + span; gy++) {
                const long long iy = gy - minCellY_;
                if (iy < 0 || iy >= (long long)cellsY_) continue;
                const size_t cell = (size_t)iy * (size_t)cellsX_ + (size_t)ix;
                for (int e = cellStart_[cell]; e < cellStart_[cell + 1]; e++) {
                    const size_t slot = (size_t)items_[(size_t)e];
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
            const long long ix = gx - minCellX_;
            if (ix < 0 || ix >= (long long)cellsX_) continue;
            for (long long gy = by - span; gy <= by + span; gy++) {
                const long long iy = gy - minCellY_;
                if (iy < 0 || iy >= (long long)cellsY_) continue;
                const size_t cell = (size_t)iy * (size_t)cellsX_ + (size_t)ix;
                for (int e = cellStart_[cell]; e < cellStart_[cell + 1]; e++) {
                    const size_t slot = (size_t)items_[(size_t)e];
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

private:
    int flatCell(const cv::Point2f &p) const
    {
        const long long gx = (long long)std::floor(p.x / cell_) - minCellX_;
        const long long gy = (long long)std::floor(p.y / cell_) - minCellY_;
        return (int)(gy * (long long)cellsX_ + gx);
    }

    const std::vector<CornerCandidate> &corners_;
    const std::vector<int> &subset_;
    double cell_;
    long long minCellX_, minCellY_;
    int cellsX_, cellsY_;
    std::vector<int> cellStart_;   // cellStart_[c] .. cellStart_[c+1] index into items_
    std::vector<int> items_;       // positions within subset_, grouped by cell, in subset order
};

double vectorLength(const cv::Point2f &p)
{
    return std::sqrt((double)p.x * p.x + (double)p.y * p.y);
}

struct PitchPrior {
    double pitch;
    double confidence;
    int scanlineCount;
    double spread;

    PitchPrior() : pitch(0.0), confidence(0.0), scanlineCount(0), spread(0.0) {}
};

bool byEstimatePitch(const std::pair<double, double> &a, const std::pair<double, double> &b)
{
    return a.first < b.first;
}

double medianOfSorted(std::vector<double> values)
{
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const size_t mid = values.size() / 2;
    if ((values.size() & 1) != 0) return values[mid];
    return 0.5 * (values[mid - 1] + values[mid]);
}

bool scanlinePitchEstimate(const cv::Mat &gray,
                           bool horizontal,
                           int fixed,
                           int from,
                           int to,
                           int minLag,
                           int maxLag,
                           double *pitch,
                           double *score)
{
    const int n = to - from;
    if (n < 4 * minLag || maxLag <= minLag) return false;

    std::vector<double> values;
    values.reserve((size_t)n);
    for (int t = from; t < to; t++) {
        double sum = 0.0;
        int count = 0;
        for (int o = -1; o <= 1; o++) {
            const int x = horizontal ? t : fixed + o;
            const int y = horizontal ? fixed + o : t;
            if (x < 0 || y < 0 || x >= gray.cols || y >= gray.rows) continue;
            sum += gray.at<uchar>(y, x) / 255.0;
            count++;
        }
        if (count == 0) return false;
        values.push_back(sum / (double)count);
    }

    double mean = 0.0;
    for (size_t i = 0; i < values.size(); i++) mean += values[i];
    mean /= (double)values.size();
    double variance = 0.0;
    for (size_t i = 0; i < values.size(); i++) {
        values[i] -= mean;
        variance += values[i] * values[i];
    }
    variance /= (double)values.size();
    if (variance < 0.0025) return false;
    const double invStd = 1.0 / std::sqrt(variance);
    for (size_t i = 0; i < values.size(); i++) values[i] *= invStd;

    std::vector<double> corr((size_t)(2 * maxLag + 1), 0.0);
    for (int lag = 1; lag <= 2 * maxLag; lag++) {
        if (lag >= n) break;
        double c = 0.0;
        for (int i = 0; i + lag < n; i++) c += values[(size_t)i] * values[(size_t)(i + lag)];
        corr[(size_t)lag] = c / (double)(n - lag);
    }

    double bestScore = -1e30;
    for (int lag = minLag; lag <= maxLag && 2 * lag < n; lag++) {
        const double c1 = corr[(size_t)lag];
        const double c2 = corr[(size_t)(2 * lag)];
        const double s = std::max(0.0, -c1) + 0.55 * std::max(0.0, c2);
        if (s > bestScore) bestScore = s;
    }
    if (bestScore < 0.25) return false;

    int chosenLag = 0;
    double chosenScore = 0.0;
    for (int lag = minLag; lag <= maxLag && 2 * lag < n; lag++) {
        const double c1 = corr[(size_t)lag];
        const double c2 = corr[(size_t)(2 * lag)];
        const double s = std::max(0.0, -c1) + 0.55 * std::max(0.0, c2);
        if (s >= 0.78 * bestScore) {
            chosenLag = lag;
            chosenScore = s;
            break;
        }
    }
    if (chosenLag <= 0) return false;
    *pitch = (double)chosenLag;
    *score = chosenScore;
    return true;
}

PitchPrior estimateCentralPitchPrior(const cv::Mat &gray)
{
    PitchPrior prior;
    if (gray.empty() || gray.type() != CV_8UC1 || gray.cols < 80 || gray.rows < 80) return prior;

    const int minDim = std::min(gray.cols, gray.rows);
    const int minLag = std::max(14, minDim / 80);
    const int maxLag = std::min(minDim / 4, 260);
    if (maxLag <= minLag) return prior;

    std::vector<std::pair<double, double> > estimates;
    const double fractions[] = {0.34, 0.38, 0.42, 0.46, 0.50, 0.54, 0.58, 0.62, 0.66};
    const int fractionCount = (int)(sizeof(fractions) / sizeof(fractions[0]));
    const int xFrom = gray.cols / 5;
    const int xTo = gray.cols - xFrom;
    const int yFrom = gray.rows / 5;
    const int yTo = gray.rows - yFrom;
    for (int i = 0; i < fractionCount; i++) {
        double pitch = 0.0, score = 0.0;
        const int y = std::max(1, std::min(gray.rows - 2, (int)(gray.rows * fractions[i] + 0.5)));
        if (scanlinePitchEstimate(gray, true, y, xFrom, xTo, minLag, maxLag, &pitch, &score)) {
            estimates.push_back(std::make_pair(pitch, score));
        }
        const int x = std::max(1, std::min(gray.cols - 2, (int)(gray.cols * fractions[i] + 0.5)));
        if (scanlinePitchEstimate(gray, false, x, yFrom, yTo, minLag, maxLag, &pitch, &score)) {
            estimates.push_back(std::make_pair(pitch, score));
        }
    }

    if (estimates.size() < 4) return prior;
    std::sort(estimates.begin(), estimates.end(), byEstimatePitch);
    std::vector<double> pitches;
    std::vector<double> scores;
    pitches.reserve(estimates.size());
    scores.reserve(estimates.size());
    for (size_t i = 0; i < estimates.size(); i++) {
        pitches.push_back(estimates[i].first);
        scores.push_back(estimates[i].second);
    }

    const double pitch = medianOfSorted(pitches);
    if (pitch <= 1e-6) return prior;
    std::vector<double> relativeDeviation;
    relativeDeviation.reserve(pitches.size());
    for (size_t i = 0; i < pitches.size(); i++) {
        relativeDeviation.push_back(std::fabs(pitches[i] - pitch) / pitch);
    }
    const double spread = medianOfSorted(relativeDeviation);
    const double medianScore = medianOfSorted(scores);
    const double countConfidence = std::min(1.0, (double)estimates.size() / 8.0);
    const double scoreConfidence = std::min(1.0, medianScore / 0.65);
    const double spreadConfidence = std::max(0.0, 1.0 - spread / 0.35);

    prior.pitch = pitch;
    prior.confidence = countConfidence * scoreConfidence * spreadConfidence;
    if (prior.confidence < 0.15) prior.confidence = 0.0;
    prior.scanlineCount = (int)estimates.size();
    prior.spread = spread;
    return prior;
}

double pitchPriorScore(double candidatePitch, const PitchPrior &prior)
{
    if (candidatePitch <= 1e-6 || prior.pitch <= 1e-6 || prior.confidence <= 0.0) return 0.0;
    const double sigma = std::log(1.6);
    const double z = std::log(candidatePitch / prior.pitch) / sigma;
    const double agreement = std::exp(-0.5 * z * z);
    return 12.0 * prior.confidence * (2.0 * agreement - 1.0);
}

struct HistogramPeak {
    cv::Point2f displacement;
    float count;
};

bool byPeakCountDescending(const HistogramPeak &a, const HistogramPeak &b)
{
    return a.count > b.count;
}

std::string summarizedAttempts(const std::ostringstream &attempts)
{
    const std::string text = attempts.str();
    const size_t maxLength = 2400;
    if (text.size() <= maxLength) return text;
    return text.substr(0, maxLength) + " ...";
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

    // Only pairs closer together than `radius` contribute, so they are enumerated through a grid
    // of cells one radius across rather than by considering all n(n-1)/2 of them. Any qualifying
    // partner of a point must lie in that point's own cell or one of the eight around it. This
    // examines exactly the pairs the radius test would have kept plus a fringe the same test still
    // rejects, so the histogram it builds is identical -- the counts are integers accumulated in
    // floats well below the exact range, so even the arithmetic is order-independent.
    //
    // Worth the machinery because the discarded fraction was large and the cost quadratic. Measured
    // over sixteen frames, the seed search examined 3 to 94 million pairs per frame and kept only
    // 20 to 27% of them, and it accounted for 56 to 75% of the whole detector's runtime.
    std::vector<double> px(subset.size()), py(subset.size());
    double minX = 0.0, minY = 0.0, maxX = 0.0, maxY = 0.0;
    for (size_t i = 0; i < subset.size(); i++) {
        const cv::Point2f &p = corners[subset[i]].position;
        px[i] = p.x; py[i] = p.y;
        if (i == 0) { minX = maxX = p.x; minY = maxY = p.y; }
        if (p.x < minX) minX = p.x;
        if (p.x > maxX) maxX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.y > maxY) maxY = p.y;
    }
    const int cellsX = std::max(1, (int)((maxX - minX) / radius) + 1);
    const int cellsY = std::max(1, (int)((maxY - minY) / radius) + 1);
    std::vector<std::vector<int> > cellContents((size_t)cellsX * (size_t)cellsY);
    std::vector<int> cellOf(subset.size());
    for (size_t i = 0; i < subset.size(); i++) {
        int cx = (int)((px[i] - minX) / radius);
        int cy = (int)((py[i] - minY) / radius);
        if (cx < 0) cx = 0; if (cx >= cellsX) cx = cellsX - 1;
        if (cy < 0) cy = 0; if (cy >= cellsY) cy = cellsY - 1;
        cellOf[i] = cy * cellsX + cx;
        cellContents[(size_t)cellOf[i]].push_back((int)i);
    }

    float *const histData = hist.ptr<float>(0);
    const size_t histStride = hist.step / sizeof(float);
    for (size_t i = 0; i < subset.size(); i++) {
        const int cx = cellOf[i] % cellsX;
        const int cy = cellOf[i] / cellsX;
        for (int oy = -1; oy <= 1; oy++) {
            const int ny = cy + oy;
            if (ny < 0 || ny >= cellsY) continue;
            for (int ox = -1; ox <= 1; ox++) {
                const int nx = cx + ox;
                if (nx < 0 || nx >= cellsX) continue;
                const std::vector<int> &bucket = cellContents[(size_t)ny * (size_t)cellsX + (size_t)nx];
                for (size_t k = 0; k < bucket.size(); k++) {
                    const size_t j = (size_t)bucket[k];
                    if (j <= i) continue;   // each unordered pair once, as the old loop did
                    const double dx = px[j] - px[i];
                    const double dy = py[j] - py[i];
                    if (dx * dx + dy * dy > radiusSq) continue;
                    // Accumulate both signs; the set of lattice displacements is symmetric.
                    for (int s = 0; s < 2; s++) {
                        const double sx = s ? -dx : dx;
                        const double sy = s ? -dy : dy;
                        const int bx = (int)std::floor((sx + radius) / binSize);
                        const int by = (int)std::floor((sy + radius) / binSize);
                        if (bx < 0 || by < 0 || bx >= nb || by >= nb) continue;
                        histData[(size_t)by * histStride + (size_t)bx] += 1.0f;
                    }
                }
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
    return findSeedLattice(corners, coarseCellSize, imageSize, hint, cv::Mat());
}

SeedLattice findSeedLattice(const std::vector<CornerCandidate> &corners,
                            float coarseCellSize,
                            cv::Size imageSize,
                            const LatticeSeedHint &hint,
                            const cv::Mat &gray)
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

    SeedPatch bestPatch;
    cv::Point2f bestU(0.0f, 0.0f), bestV(0.0f, 0.0f);
    cv::Point2f bestWindowCenter(0.0f, 0.0f);
    double bestSide = 0.0, bestStep = 0.0, bestSharpness = 0.0;
    double bestPatchScore = -1.0;
    bool haveBasis = false;
    bool bestAligned = false;
    double bestMisalignment = 0.0;
    bool sawConflict = false;
    std::ostringstream attempts;
    const PitchPrior pitchPrior = hint.provided ? PitchPrior() : estimateCentralPitchPrior(gray);

    std::vector<cv::Point2f> windowCenters;
    if (hint.provided) {
        windowCenters.push_back(hint.from);
    } else {
        windowCenters.push_back(center);
        const double xFractions[] = {0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85};
        const double yFractions[] = {0.25, 0.35, 0.45, 0.55, 0.65, 0.75};
        for (size_t y = 0; y < sizeof(yFractions) / sizeof(yFractions[0]); y++) {
            for (size_t x = 0; x < sizeof(xFractions) / sizeof(xFractions[0]); x++) {
                windowCenters.push_back(cv::Point2f((float)(imageSize.width * xFractions[x]),
                                                    (float)(imageSize.height * yFractions[y])));
            }
        }
    }

    for (size_t c = 0; c < windowCenters.size(); c++) {
        const cv::Point2f windowCenter = windowCenters[c];
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
            attempts << " [" << (int)windowCenter.x << "," << (int)windowCenter.y
                     << " " << (int)side << "px/" << subset.size() << "pts:";
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

            // Second pass: re-bin tightly around the discovered step, for a precise basis. Debris
            // stuck to the board can create a stronger short-period peak than the true chessboard
            // pitch, so do not let that shrink the second pass enough to exclude the board's own
            // row and column displacements.
            const double fineRadius = kFineRadiusFactor * std::max(step, side / kWindowCells);
            std::vector<HistogramPeak> peaks;
            const double sharpness = displacementPeaks(corners, subset, fineRadius, kFineHistogramBins,
                                                       kPeakMinFraction, &peaks);
            attempts << " peaks=" << peaks.size();
            // Try every plausible pair of histogram peaks, not just the two strongest. In contaminated
            // frames the diagonals can outvote the true row and column steps, but a lower-ranked peak pair
            // can still form the correct aligned basis.
            std::vector<HistogramPeak> sortedPeaks = peaks;
            std::sort(sortedPeaks.begin(), sortedPeaks.end(), byPeakCountDescending);
            bool foundCandidateInWindow = false;
            double strongest = 0.0;
            for (size_t i = 0; i < sortedPeaks.size(); i++) if (sortedPeaks[i].count > strongest) strongest = sortedPeaks[i].count;

        for (size_t i = 0; i < sortedPeaks.size(); i++) {
            for (size_t j = i + 1; j < sortedPeaks.size(); j++) {
                cv::Point2f u = sortedPeaks[i].displacement;
                cv::Point2f v = sortedPeaks[j].displacement;
                const double lenU = vectorLength(u);
                const double lenV = vectorLength(v);
                if (lenU < 1e-6 || lenV < 1e-6) continue;
                const double initialCross = (double)u.x * v.y - (double)u.y * v.x;
                if (std::fabs(initialCross) / (lenU * lenV) < kMinSinAngle) continue;

                // Lagrange reduction, so the basis describes the smallest cell rather than a sheared
                // multiple of it. This matches selectBasis(), but is kept inline here because each
                // peak pair needs to be reduced and scored independently.
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
                if (a < 1e-6 || b < 1e-6) continue;
                if (b / a > kBasisLengthRatioMax) continue;
                const double cross = (double)u.x * v.y - (double)u.y * v.x;
                if (std::fabs(cross) / (a * b) < kMinSinAngle) continue;

                if (u.x < 0.0f || (std::fabs(u.x) < 1e-6 && u.y < 0.0f)) u = cv::Point2f(-u.x, -u.y);
                if ((double)u.x * v.y - (double)u.y * v.x < 0.0) v = cv::Point2f(-v.x, -v.y);

                // A real two-dimensional lattice also shows peaks at the cell diagonals. A row of
                // evenly spaced bolts or a grating is periodic in one direction only and has none, so
                // finding one is enough to rule that out. Requiring both was too strict under strong
                // fisheye, where the longer diagonal displacement smears across more bins than the
                // basis vectors do.
                const double diagonalTolerance = 0.3 * std::min(vectorLength(u), vectorLength(v));
                const cv::Point2f sum(u.x + v.x, u.y + v.y);
                const cv::Point2f diff(u.x - v.x, u.y - v.y);
                int diagonalsInRange = 0;
                int diagonalsFound = 0;
                if (vectorLength(sum) < fineRadius) {
                    diagonalsInRange++;
                    if (peakExistsNear(sortedPeaks, sum, diagonalTolerance, kDiagonalMinFraction * strongest)) diagonalsFound++;
                }
                if (vectorLength(diff) < fineRadius) {
                    diagonalsInRange++;
                    if (peakExistsNear(sortedPeaks, diff, diagonalTolerance, kDiagonalMinFraction * strongest)) diagonalsFound++;
                }
                if (diagonalsInRange > 0 && diagonalsFound == 0) continue;

                // A hint fixes the first basis direction outright: the user has said which way the
                // grid runs, which beats any automatic choice.
                if (hint.provided) {
                    const cv::Point2f hinted(hint.to.x - hint.from.x, hint.to.y - hint.from.y);
                    if (vectorLength(hinted) > 1e-3) {
                        const double hintCross = (double)hinted.x * v.y - (double)hinted.y * v.x;
                        if (std::fabs(hintCross) / (vectorLength(hinted) * vectorLength(v)) >= kMinSinAngle) u = hinted;
                    }
                }

                const SeedPatch patch = labelSeedPatch(corners, subset, u, v);
                const double misalignment = basisMisalignmentDegrees(u, v);
                const bool aligned = (misalignment <= kMaxBasisMisalignmentDegrees);
                foundCandidateInWindow = true;
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
                const double spanI = patch.extentI > 1 ? (patch.extentI - 1) * vectorLength(u) : 0.0;
                const double spanJ = patch.extentJ > 1 ? (patch.extentJ - 1) * vectorLength(v) : 0.0;
                const double coverage = side > 1e-6 ? std::min(spanI, spanJ) / side : 0.0;
                const double candidatePitch = std::sqrt(vectorLength(u) * vectorLength(v));
                const double patchScore = patch.cornerIndex.size() + 10.0 * coverage +
                                          pitchPriorScore(candidatePitch, pitchPrior);
                if (!haveBasis || (aligned && !bestAligned) ||
                    (aligned == bestAligned && patchScore > bestPatchScore)) {
                    bestPatch = patch;
                    bestU = u;
                    bestV = v;
                    bestWindowCenter = windowCenter;
                    bestSide = side;
                    bestStep = step;
                    bestSharpness = sharpness;
                    bestPatchScore = patchScore;
                    bestAligned = aligned;
                    bestMisalignment = misalignment;
                    haveBasis = true;
                }
            }
        }

        if (!foundCandidateInWindow) {
            attempts << " no basis]";
        } else {
            attempts << " best |u|=" << vectorLength(bestU) << " |v|=" << vectorLength(bestV)
                     << " off-axis=" << bestMisalignment << "deg patch=" << bestPatch.cornerIndex.size() << "]";
        }
        }
    }

    if (!haveBasis) {
        std::ostringstream message;
        message << "No lattice found among " << corners.size() << " corners.";
        if (sawConflict) {
            message << " A basis was found but produced inconsistent grid coordinates, which means "
                    << "the basis or the matching tolerance is wrong.";
        } else {
            message << " No window produced a displacement histogram with two non-collinear peaks "
                    << "and matching diagonals. Tried:" << summarizedAttempts(attempts);
        }
        seed.status = message.str();
        return seed;
    }

    seed.basis.u = bestU;
    seed.basis.v = bestV;
    seed.basis.windowCenter = bestWindowCenter;
    seed.basis.windowSide = (float)bestSide;
    seed.basis.peakSharpness = (float)bestSharpness;
    seed.basis.valid = true;

    if (bestPatch.cornerIndex.size() < kMinFullyConsistentPoints) {
        std::ostringstream message;
        message.setf(std::ios::fixed);
        message.precision(1);
        message << "Basis found (|u| = " << vectorLength(bestU) << " px, |v| = " << vectorLength(bestV)
                << " px) but only " << bestPatch.cornerIndex.size() << " corners form a connected "
                << "lattice, so the basis is probably wrong. Tried:" << summarizedAttempts(attempts);
        seed.status = message.str();
        return seed;
    }

    if (!hint.provided && !bestAligned) {
        std::ostringstream message;
        message.setf(std::ios::fixed);
        message.precision(1);
        message << "Best automatic basis runs " << bestMisalignment << " deg off the image axes, "
                << "which is probably the chessboard diagonals rather than its rows and columns. "
                << "Draw a two-point seed line along one true grid step and run detection again. Tried:"
                << summarizedAttempts(attempts);
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
    message << ". Seed window centered at (" << (int)bestWindowCenter.x << ", " << (int)bestWindowCenter.y << "), "
            << (int)bestSide << " px = " << (bestStep > 1e-6 ? bestSide / bestStep : 0.0)
            << " cells; histogram peak sharpness " << bestSharpness;
    if (pitchPrior.confidence > 0.0) {
        message << "; brightness pitch prior " << pitchPrior.pitch << " px from "
                << pitchPrior.scanlineCount << " scanlines, confidence " << pitchPrior.confidence
                << ", spread " << pitchPrior.spread;
    } else if (!gray.empty()) {
        message << "; no reliable brightness pitch prior";
    }
    message << ". Tried:" << summarizedAttempts(attempts);
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
    // Kept per axis. The tolerance derived from these is the distance at which this site could be
    // confused with an adjacent one, which is the pitch of the *tighter* axis; pooling both into
    // one median overstates it wherever the board is viewed obliquely. Measured on one frame, 21%
    // of grown sites had their tolerance inflated by more than 1.5x this way and some by 2.8x.
    std::vector<double> spacingsI, spacingsJ;

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

        if (p1 && p2) {
            const double pitch = vectorLength(cv::Point2f(p1->x - p2->x, p1->y - p2->y));
            (d < 2 ? spacingsI : spacingsJ).push_back(pitch);
        }

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
        // pa and pab differ only in j, so this is a j-axis pitch.
        spacingsJ.push_back(vectorLength(cv::Point2f(pa.x - pab.x, pa.y - pab.y)));
    }

    std::vector<cv::Point2f> *chosen = 0;
    if (!tier3.empty()) { chosen = &tier3; result.tier = 3; }
    else if (!tier2.empty()) { chosen = &tier2; result.tier = 2; }
    else if (!tier1.empty()) { chosen = &tier1; result.tier = 1; }
    if (!chosen) return result;

    result.position = medianPoint(*chosen);
    // Median within each axis, so one corrupted pair cannot set the scale, then the smaller of the
    // two axes, because that is the shorter of the two distances to an adjacent site.
    double best = 0.0;
    for (int axis = 0; axis < 2; axis++) {
        std::vector<double> &pitches = (axis == 0) ? spacingsI : spacingsJ;
        if (pitches.empty()) continue;
        std::sort(pitches.begin(), pitches.end());
        const double median = pitches[pitches.size() / 2];
        if (best <= 0.0 || median < best) best = median;
    }
    result.spacing = (best > 0.0) ? best : std::min(vectorLength(u), vectorLength(v));
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
            // Tier 1 steps one seed basis vector from a single neighbour, so both the position it
            // predicts and the spacing it reports are the basis measured near the middle of the
            // frame. Where the board is compressed against a frame edge the real pitch can be half
            // that, which makes the prediction wrong by most of a cell and simultaneously inflates
            // the tolerance that is supposed to catch it. Measured on one frame, the 9 tier-1
            // placements had a median residual of 16.2 px against 2.1 px for the 460 tier-3 ones,
            // and each bad one corrupts a whole run: a tier-1 placement at site (14,5) took a
            // corner 35 px from where that site belongs, after which the row read 17.6, 38.5 and
            // 66.9 px between consecutive corners on a 35 px pitch and refinement expelled most of
            // it. Leaving the site empty is harmless by comparison -- holes are bridged later, and
            // refinement's own recovery pass already declines tier 1 for the same reason.
            if (pred.tier < 2 || pred.spacing <= 1e-6) continue;
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

namespace {

// How many lattice cells a run may bridge in one step before it is split in two. A step of 1
// is two adjacent corners; anything up to this leaves at most three consecutive corners
// missing, which the surrounding corners on both sides still vouch for. Measured on real
// frames, ordinary holes from a missed corner or two span 2 to 4 cells and are worth keeping,
// while the joins that turned out to be untrustworthy spanned 8, 10 and 21.
const int kMaxBridgedCells = 4;

// A final guard against a row or column whose lattice indices walk backward in screen space.
// Real distortion bends a line, but it does not make consecutive chessboard corners reverse
// direction along the row/column basis. Large reversals mean growth reached the same plumbline
// through two fragments and assigned one fragment's sites to the wrong side of the other.
const double kMaxReverseProgressFraction = 0.35;

// A sparse line can still walk monotonically along the basis while hopping sideways onto
// scratches or onto a neighbouring row/column. Consecutive accepted corners may bridge a
// few missing lattice cells, but the per-cell screen displacement should stay close to the
// pitch of the rest of the line and mostly aligned with the basis.
//
// How far a step's length may stray from that pitch. The reference has to be measured
// locally. Radial distortion compresses the on-screen pitch toward the edge of the frame,
// and on the 8 mm fisheye footage in this project the pitch at the left and right edges of a
// row runs a quarter of the pitch at its centre -- 25 px against 104 px on one measured
// frame. Judged against the single basis taken from the seed window, which sits near the
// centre, every step out there read as impossibly short: the outer three or four columns
// were split off into fragments below minPoints and discarded, so the fit lost exactly the
// corners where the distortion it is solving for is strongest, while the columns through the
// same corners survived intact because the vertical direction is tangential there and barely
// compressed at all. Judged against its own neighbours the same step is unremarkable. Over
// fourteen real frames, on the eight where the board was actually found, 99% of steps fall
// between 0.79 and 1.16 of the local pitch and only 0.15% fall outside these bounds; on the
// six where the lattice came out junk the same bounds still split 27% of steps, so the guard
// keeps its discriminating power.
const double kMinLocalStepFraction = 0.50;
const double kMaxLocalStepFraction = 2.00;

// How many steps either side of a step are averaged to get the pitch it is judged against.
// The pitch changes by only a few percent per cell, so a short window tracks it closely, and
// taking the median of six neighbours means one or two bad steps cannot vouch for themselves.
const int kLocalPitchWindow = 3;

// The sideways component, by contrast, is deliberately still measured against the global
// basis. Localizing it was tried and is worse: on the frames where the board was found it
// rejects more good steps (0.09% against 0.06%), and on the frames where the lattice was junk
// it catches fewer bad ones (29% against 36%), because a contaminated run drags its own local
// reference along with it while the seed basis stays put.
const double kMaxPerpendicularStepFraction = 0.70;

// The per-cell screen length of every step in one run. Entry k is the step from along[k] to
// along[k + 1], divided by the number of lattice cells it bridges, so holes do not make a
// step look long.
std::vector<double> perCellStepLengths(const std::vector<std::pair<int, int> > &along,
                                       const std::vector<CornerCandidate> &corners)
{
    std::vector<double> lengths;
    if (along.size() < 2) return lengths;
    lengths.reserve(along.size() - 1);
    for (size_t k = 1; k < along.size(); k++) {
        const int gap = along[k].first - along[k - 1].first;
        const cv::Point2f &a = corners[along[k - 1].second].position;
        const cv::Point2f &b = corners[along[k].second].position;
        lengths.push_back(gap > 0 ? vectorLength(cv::Point2f(b.x - a.x, b.y - a.y)) / (double)gap : 0.0);
    }
    return lengths;
}

// The pitch step k should be judged against: the median per-cell length of the steps within
// kLocalPitchWindow either side of it, itself excluded so it cannot vouch for itself. Returns
// 0 when there are no neighbours to measure, which leaves the caller to fall back.
double localPitch(const std::vector<double> &stepLengths, size_t k)
{
    if (stepLengths.empty()) return 0.0;
    const size_t from = k > (size_t)kLocalPitchWindow ? k - (size_t)kLocalPitchWindow : 0;
    const size_t to = std::min(stepLengths.size(), k + (size_t)kLocalPitchWindow + 1);
    std::vector<double> neighbours;
    neighbours.reserve(to - from);
    for (size_t m = from; m < to; m++) {
        if (m != k && stepLengths[m] > 0.0) neighbours.push_back(stepLengths[m]);
    }
    if (neighbours.empty()) return 0.0;
    std::sort(neighbours.begin(), neighbours.end());
    const size_t mid = neighbours.size() / 2;
    return neighbours.size() % 2 == 1 ? neighbours[mid]
                                      : 0.5 * (neighbours[mid - 1] + neighbours[mid]);
}

bool plumblineStepBreaks(const cv::Point2f &previous,
                         const cv::Point2f &current,
                         int latticeGap,
                         const cv::Point2f &basis,
                         double basisLength,
                         double pitch)
{
    if (latticeGap <= 0 || basisLength <= 1e-6) return true;
    // A run too short to have neighbours has nothing local to measure against; the seed basis
    // is a poor reference but it is the only one there is.
    if (pitch <= 1e-6) pitch = basisLength;
    const cv::Point2f delta(current.x - previous.x, current.y - previous.y);
    const double stepLength = vectorLength(delta) / (double)latticeGap;
    if (stepLength < kMinLocalStepFraction * pitch ||
        stepLength > kMaxLocalStepFraction * pitch) {
        return true;
    }

    const double perpendicular = std::fabs(delta.x * basis.y - delta.y * basis.x) /
                                 (basisLength * (double)latticeGap);
    return perpendicular > kMaxPerpendicularStepFraction * basisLength;
}

}   // anonymous namespace

std::vector<Plumbline> extractPlumblines(const std::vector<CornerCandidate> &corners,
                                         const GrownLattice &lattice,
                                         int minPoints)
{
    std::vector<Plumbline> lines;
    if (!lattice.valid) return lines;

    // Rows share a j and vary in i; columns the other way. A short hole is not a break, since
    // the corners either side of it still lie on the same straight world line -- but only if
    // they really are the same line. Across a long hole the lattice indices on the far side
    // were established by growing around the hole through neighbouring lines, never through
    // it, so nothing has verified that the two fragments share a row. One slip in that
    // detour and the fragments belong to different rows, and the fit is then handed a line
    // that is genuinely bent and asked to straighten it. Real frames from an 8 mm fisheye
    // produced joins spanning up to 21 cells and 929 px, arcing right across the frame.
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
            // Split into fragments wherever the hole is too long to vouch for, or where the
            // run walks backward in screen space. The latter catches duplicated fragments that
            // growth attached to the wrong end of a row/column: their lattice indices are sorted,
            // but their projected position jumps back across already-emitted points.
            const cv::Point2f basis = isRow ? lattice.basis.u : lattice.basis.v;
            const double basisLength = vectorLength(basis);
            const double reverseTolerance = kMaxReverseProgressFraction * basisLength;
            // Measured over the whole run up front, so that a step near the compressed end of
            // a row is judged against the pitch there rather than against the pitch wherever
            // the seed window happened to land.
            const std::vector<double> stepLengths = perCellStepLengths(along, corners);
            size_t start = 0;
            double previousProgress = 0.0;
            bool havePreviousProgress = false;
            for (size_t k = 0; k <= along.size(); k++) {
                bool breakHere = (k == along.size()) ||
                                 (k > 0 && along[k].first - along[k - 1].first > kMaxBridgedCells);
                if (!breakHere && basisLength > 1e-6) {
                    const cv::Point2f &p = corners[along[k].second].position;
                    const double progress = (p.x * basis.x + p.y * basis.y) / basisLength;
                    if (havePreviousProgress && progress < previousProgress - reverseTolerance) {
                        breakHere = true;
                    } else if (k > 0 &&
                               plumblineStepBreaks(corners[along[k - 1].second].position,
                                                   p,
                                                   along[k].first - along[k - 1].first,
                                                   basis,
                                                   basisLength,
                                                   localPitch(stepLengths, k - 1))) {
                        breakHere = true;
                    } else {
                        previousProgress = progress;
                        havePreviousProgress = true;
                    }
                }
                if (!breakHere) continue;
                if ((int)(k - start) >= minPoints) {
                    Plumbline line;
                    line.isRow = isRow;
                    line.index = fixed;
                    for (size_t m = start; m < k; m++) line.points.push_back(corners[along[m].second].position);
                    lines.push_back(line);
                }
                start = k;
                havePreviousProgress = false;
                if (k < along.size() && basisLength > 1e-6) {
                    const cv::Point2f &p = corners[along[k].second].position;
                    previousProgress = (p.x * basis.x + p.y * basis.y) / basisLength;
                    havePreviousProgress = true;
                }
            }
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

// Both floors above and below are fractions of a cell, but the noise they are meant to sit
// above is sub-pixel localisation error, which is a fixed number of pixels regardless of how
// large the cell is. Where the board is compressed against the edge of a fisheye frame a cell
// can be 15 to 25 px, and 0.05 of a cell is then 0.75 to 1.25 px -- inside the noise. Measured
// over sixteen real frames, the median leave-one-out deviation of corners that survive
// refinement is 0.32 px and barely moves with cell size (0.33 px where cells exceed 60 px,
// 0.32 px where they are under 30 px), while expressed in cells the same figure rises from
// 0.0042 to 0.0145. So the fractional floors quietly tighten to nothing exactly where the
// corners are hardest to localise, and on one frame refinement expelled 104 of the 184 grown
// corners in the right-hand sixth of the image while expelling 0 to 10 per sixth everywhere
// else. A deviation must now clear both a fraction of a cell and an absolute number of pixels
// to count as gross error. 2.5 px is about twice the 90th percentile of the honest deviations
// and stays well below the misplacements worth catching: the two documented on real frames
// were 0.07 and 0.106 of a cell, 6.7 and 10 px on a 95 px cell, and the one that prompted this
// investigation was 8.9 px. In well-resolved regions the pixel floor never binds, since 2.5 px
// is under 0.05 of a cell as soon as a cell exceeds 50 px.
const double kMinOutlierPixels = 2.5;

// The same idea applied to the whole-line fit, which is coarser and so needs looser bounds: it
// carries the fisheye curvature the local stencil cancels exactly, and it is being asked to
// judge corners at the ends of short, holey runs where there is least support. Measured on
// real frames, a camera whose lines were judged clean by eye had a worst deviation of 0.08 of
// a cell, while the camera with visibly wrong endpoints had a cluster between 0.19 and 0.47.
// The absolute floor sits between those.
//
// Unlike the local test, the scale here is pooled over every line in the lattice rather than
// measured per line. Measured per line it defeats itself: the short, strongly curved runs in
// the frame corners have a baseline scatter of 0.033 to 0.052 of a cell against 0.005 on a
// long central line, both because a quartic fits a short sharply curved arc less well and
// because those regions have the worst contrast. Five sigma of a per-line scale is then 0.24
// to 0.38 there, comfortably above the very outliers being looked for, so the lines most in
// need of the test were the ones exempted from it. Pooling gives a scale set by the whole
// image, which still lets a genuinely noisy frame raise its own threshold without letting one
// bad line excuse itself.
const double kWholeLineOutlierSigmas = 5.0;
const double kMinWholeLineDeviation = 0.13;

// The pixel companion to kMinWholeLineDeviation, in the same ratio to kMinOutlierPixels as the
// two fractional floors are to each other, since this test is the blunter of the two and its
// threshold is correspondingly looser.
const double kMinWholeLinePixels = 6.5;

// How far from a predicted site to accept an already-detected corner, and how far to let a
// direct image search move, both as fractions of the cell spacing.
// Both are tight because the prediction is good: leave-one-out estimates land within about
// 0.0025 of a cell of where corners actually are. A loose search radius lets the image search
// snap back onto the very corner just expelled, which sits only a few hundredths of a cell
// away, quietly undoing the expulsion.
const double kRecoveryMatchFraction = 0.10;
const double kRecoverySearchFraction = 0.06;

// A known weakness of this recovery path, left in place deliberately because both attempted
// cures measured worse than the disease.
//
// A corner manufactured here can end up unfalsifiable. The prediction may come from a single
// extrapolation off the end of a run, with nothing on the far side to contradict it; the
// sub-pixel fit then only has to find some saddle within kRecoverySearchFraction of that
// prediction and scrape kMinScore. Afterwards the only test that can reach such a corner is
// often the same one-sided cubic that placed it, against which it necessarily reads clean. One
// real frame produced a point at 1248.0, 962.8 where the actual junction was at 1239.5, 960.2:
// its row, which had predicted it, measured its deviation at 0.0017 of a cell, while its column,
// which put it 0.27 of a cell out, had a hole beside it and could not judge it at all. Measured
// over sixteen frames, 51 of the 124 manufactured corners surviving refinement had no judge
// other than the fit that placed them, or none at all.
//
// Requiring two independent predictors before manufacturing a corner was tried and rejected: a
// site one ring beyond the board's current extent has support on one side by definition, and
// reaching those edge corners is the whole point of recovery, so the rule cost 73 points on one
// frame and 45 on another while gaining nothing. Requiring a higher appearance score of
// single-predictor recoveries was also tried and rejected: the unfalsifiable group is only
// modestly weaker than the rest (median score 0.393 against 0.506), so any bar high enough to
// bite removed load-bearing hole-fillers and dropped whole lines below minPoints -- a bar of
// 0.30 cost 41 points and four lines on a frame that was working -- and no bar could be shown to
// remove a genuinely bad point, since the failure above could not be reproduced on any frame in
// the corpus. Fixing this properly means making the corner falsifiable rather than guessing at a
// threshold: confirming it against the perpendicular direction at the time it is created, which
// needs the perpendicular neighbours the lattice does not yet have at that point in the pass.

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
// Fetches the corner at a lattice index along the line, or reports it missing.
bool cornerAlongLine(const std::map<int, int> &alongLine, const std::vector<CornerCandidate> &corners,
                     int index, cv::Point2f *out)
{
    std::map<int, int>::const_iterator it = alongLine.find(index);
    if (it == alongLine.end()) return false;
    *out = corners[it->second].position;
    return true;
}

// Puts a one-sided estimate's deviation on the same footing as a centered one, so both kinds
// can share a single robust scale and threshold. With independent per-corner noise of standard
// deviation s, the centered residual has standard deviation sqrt(1 + 34/36) = 1.394 s, while
// the three-point one-sided residual has sqrt(1 + 19) = 4.472 s. One-sided deviations are
// divided by the ratio so that a corner which is merely noisy reads the same either way, and
// only a corner that is genuinely displaced stands out.
const double kOneSidedDeviationScale = 1.394 / 4.472;

// pixelDeviations receives the same displacement in absolute pixels, so the caller can apply an
// absolute noise floor alongside the fraction-of-a-cell one.
//
// Normalizing by the pitch along the line is not obviously the right choice, since the
// displacement being looked for is mostly across it and on an obliquely viewed board the two
// pitches differ by up to a factor of 2.2. Splitting the displacement and normalizing each part
// by its own pitch was tried and measured worse overall: it loosens the row verdicts and tightens
// the column verdicts by the same factor, and since kMinOutlierDeviation and
// kMinWholeLineDeviation were both settled against this normalization, changing it moves the
// operating point rather than improving it. Revisiting it means re-deriving both floors, which
// needs a measure of whether a kept corner is actually right -- not just how many were kept.
bool leaveOneOutDeviations(const std::map<int, int> &alongLine,
                           const std::vector<CornerCandidate> &corners,
                           std::map<int, double> *deviations,
                           std::map<int, double> *pixelDeviations)
{
    deviations->clear();
    pixelDeviations->clear();
    for (std::map<int, int>::const_iterator it = alongLine.begin(); it != alongLine.end(); ++it) {
        const int k = it->first;
        cv::Point2f m3, m2, m1, p1, p2, p3;
        const bool haveM1 = cornerAlongLine(alongLine, corners, k - 1, &m1);
        const bool haveM2 = cornerAlongLine(alongLine, corners, k - 2, &m2);
        const bool haveM3 = cornerAlongLine(alongLine, corners, k - 3, &m3);
        const bool haveP1 = cornerAlongLine(alongLine, corners, k + 1, &p1);
        const bool haveP2 = cornerAlongLine(alongLine, corners, k + 2, &p2);
        const bool haveP3 = cornerAlongLine(alongLine, corners, k + 3, &p3);

        cv::Point2f estimate;
        double spacing = 0.0;
        double scale = 1.0;
        if (haveM2 && haveM1 && haveP1 && haveP2) {
            // Centered and preferred: exact for any cubic, so unbiased however strongly the
            // line curves. Neighbours must sit at consecutive lattice indices, since across a
            // hole the spacing is unequal and the formula does not hold.
            estimate = cv::Point2f((-m2.x + 4.0f * m1.x + 4.0f * p1.x - p2.x) / 6.0f,
                                   (-m2.y + 4.0f * m1.y + 4.0f * p1.y - p2.y) / 6.0f);
            spacing = 0.5 * vectorLength(cv::Point2f(p1.x - m1.x, p1.y - m1.y));
        } else if (haveP1 && haveP2 && haveP3) {
            // Nothing on the left, so extrapolate backwards from the three corners on the
            // right. Without this the first two and last two corners of every run went
            // unchecked, which is precisely where a run walks off onto a neighbouring line:
            // the ends are where the lattice was extended with support on one side only, so
            // where a mispredicted site had nothing to contradict it. Real frames showed runs
            // whose last two corners belonged to two different neighbouring lines, deviating
            // by 0.42 and 0.92 of a cell where a good corner deviates by under 0.016.
            estimate = cv::Point2f(3.0f * p1.x - 3.0f * p2.x + p3.x,
                                   3.0f * p1.y - 3.0f * p2.y + p3.y);
            spacing = vectorLength(cv::Point2f(p2.x - p1.x, p2.y - p1.y));
            scale = kOneSidedDeviationScale;
        } else if (haveM1 && haveM2 && haveM3) {
            estimate = cv::Point2f(3.0f * m1.x - 3.0f * m2.x + m3.x,
                                   3.0f * m1.y - 3.0f * m2.y + m3.y);
            spacing = vectorLength(cv::Point2f(m2.x - m1.x, m2.y - m1.y));
            scale = kOneSidedDeviationScale;
        } else {
            continue;   // fewer than three consecutive neighbours on either side; nothing to compare against
        }
        // Only three neighbours are used, never two: a two-point linear extrapolation carries
        // the line's curvature as systematic error, which on a fisheye near the frame edge is
        // the same size as the displacement being looked for.
        if (spacing < 1e-6) continue;
        const cv::Point2f &actual = corners[it->second].position;
        const cv::Point2f delta(actual.x - estimate.x, actual.y - estimate.y);
        const double displacement = scale * vectorLength(delta);
        (*deviations)[k] = displacement / spacing;
        (*pixelDeviations)[k] = displacement;
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

// Solves a small symmetric system by Gaussian elimination with partial pivoting. Sized for
// polynomial normal equations, so n is 4 or 5 and the cost is irrelevant.
bool solveSmall(std::vector<std::vector<double> > a, std::vector<double> b, std::vector<double> *out)
{
    const size_t n = b.size();
    for (size_t c = 0; c < n; c++) {
        size_t pivot = c;
        for (size_t r = c + 1; r < n; r++) if (std::fabs(a[r][c]) > std::fabs(a[pivot][c])) pivot = r;
        if (std::fabs(a[pivot][c]) < 1e-12) return false;
        std::swap(a[c], a[pivot]); std::swap(b[c], b[pivot]);
        for (size_t r = 0; r < n; r++) {
            if (r == c) continue;
            const double f = a[r][c] / a[c][c];
            for (size_t k = c; k < n; k++) a[r][k] -= f * a[c][k];
            b[r] -= f * b[c];
        }
    }
    out->assign(n, 0.0);
    for (size_t i = 0; i < n; i++) (*out)[i] = b[i] / a[i][i];
    return true;
}

// Weighted polynomial fit of v against t, returning the coefficients.
bool weightedPolyFit(const std::vector<double> &t, const std::vector<double> &v,
                     const std::vector<double> &w, int degree, std::vector<double> *coeffs)
{
    const size_t m = degree + 1;
    std::vector<std::vector<double> > a(m, std::vector<double>(m, 0.0));
    std::vector<double> b(m, 0.0);
    for (size_t s = 0; s < t.size(); s++) {
        double powers[8];
        powers[0] = 1.0;
        for (size_t i = 1; i < m; i++) powers[i] = powers[i - 1] * t[s];
        for (size_t i = 0; i < m; i++) {
            for (size_t j = 0; j < m; j++) a[i][j] += w[s] * powers[i] * powers[j];
            b[i] += w[s] * v[s] * powers[i];
        }
    }
    return solveSmall(a, b, coeffs);
}

double evaluatePoly(const std::vector<double> &c, double x)
{
    double acc = 0.0;
    for (size_t i = c.size(); i > 0; i--) acc = acc * x + c[i - 1];
    return acc;
}

const int kWholeLineDegree = 4;
const size_t kWholeLineMinPoints = 9;

// Deviation of each corner from a curve fitted to the whole line without it, as a fraction of
// the local spacing.
//
// This complements leaveOneOutDeviations rather than replacing it. That test is local, needing
// three or four corners at consecutive lattice indices, which is exactly what the crowded,
// low-contrast regions near a fisheye frame's corners cannot supply: runs there are short and
// full of holes, so the corners most likely to be misplaced are the ones it can least often
// judge. Fitting the whole line needs no particular corner to be present and so reaches them.
//
// A comment on leaveOneOutDeviations records that fitting a polynomial to the line was tried
// and abandoned, because a cubic cannot represent a fisheye-distorted line exactly and the
// resulting systematic error inflates the robust scale. That is right for an absolute
// threshold and is why the caller compares against a multiple of the line's own median
// deviation as well: model error raises every corner on the line together, so a threshold
// measured in units of that line's own scatter sees through it, while a corner belonging to a
// neighbouring line still stands out. Degree four rather than three, since the extra term
// costs nothing and absorbs more of the curvature.
bool wholeLineDeviations(const std::map<int, int> &alongLine,
                         const std::vector<CornerCandidate> &corners,
                         std::map<int, double> *deviations,
                         std::map<int, double> *pixelDeviations)
{
    deviations->clear();
    pixelDeviations->clear();
    if (alongLine.size() < kWholeLineMinPoints) return false;

    std::vector<int> keys;
    std::vector<cv::Point2f> pts;
    for (std::map<int, int>::const_iterator it = alongLine.begin(); it != alongLine.end(); ++it) {
        keys.push_back(it->first);
        pts.push_back(corners[it->second].position);
    }
    const size_t n = pts.size();

    // Work in the line's own frame, so the curve is a function rather than a near-vertical
    // relation the fit cannot represent.
    double cx = 0.0, cy = 0.0;
    for (size_t i = 0; i < n; i++) { cx += pts[i].x; cy += pts[i].y; }
    cx /= (double)n; cy /= (double)n;
    double sxy = 0.0, sqd = 0.0;
    for (size_t i = 0; i < n; i++) {
        const double dx = pts[i].x - cx, dy = pts[i].y - cy;
        sxy += dx * dy; sqd += dx * dx - dy * dy;
    }
    const double theta = 0.5 * std::atan2(2.0 * sxy, sqd);
    const double ct = std::cos(theta), st = std::sin(theta);

    std::vector<double> t(n), v(n);
    double span = 0.0;
    for (size_t i = 0; i < n; i++) {
        const double dx = pts[i].x - cx, dy = pts[i].y - cy;
        t[i] = dx * ct + dy * st;
        v[i] = -dx * st + dy * ct;
        if (std::fabs(t[i]) > span) span = std::fabs(t[i]);
    }
    if (span < 1e-6) return false;
    for (size_t i = 0; i < n; i++) t[i] /= span;   // conditioning: keep the powers near unity

    std::vector<double> spacing(n, 0.0);
    for (size_t i = 0; i < n; i++) {
        const size_t a = (i == 0) ? 0 : i - 1;
        const size_t b = (i + 1 < n) ? i + 1 : n - 1;
        const double d = vectorLength(cv::Point2f(pts[b].x - pts[a].x, pts[b].y - pts[a].y));
        const int steps = keys[b] - keys[a];
        spacing[i] = (steps > 0) ? d / steps : 0.0;
    }

    for (size_t held = 0; held < n; held++) {
        std::vector<double> ft, fv, fw;
        for (size_t i = 0; i < n; i++) {
            if (i == held) continue;
            ft.push_back(t[i]); fv.push_back(v[i]); fw.push_back(1.0);
        }
        if (ft.size() < (size_t)kWholeLineDegree + 2) continue;
        std::vector<double> c;
        // Two reweighting rounds, so that other misplaced corners on the same line do not drag
        // the curve toward themselves and hide the one being tested.
        for (int round = 0; round < 3; round++) {
            if (!weightedPolyFit(ft, fv, fw, kWholeLineDegree, &c)) { c.clear(); break; }
            if (round == 2) break;
            std::vector<double> resid(ft.size());
            for (size_t i = 0; i < ft.size(); i++) resid[i] = std::fabs(fv[i] - evaluatePoly(c, ft[i]));
            std::vector<double> sorted = resid;
            std::sort(sorted.begin(), sorted.end());
            const double scale = std::max(sorted[sorted.size() / 2], 1e-6);
            for (size_t i = 0; i < ft.size(); i++) fw[i] = (resid[i] < 3.0 * scale) ? 1.0 : 0.05;
        }
        if (c.empty() || spacing[held] < 1e-6) continue;
        const double residual = std::fabs(v[held] - evaluatePoly(c, t[held]));
        (*deviations)[keys[held]] = residual / spacing[held];
        (*pixelDeviations)[keys[held]] = residual;
    }
    return !deviations->empty();
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
        std::vector<std::pair<long long, double> > wholeLineDeviation;
        std::vector<double> wholeLineValues;
        std::vector<double> wholeLinePixelDeviation;
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
                // Two independent verdicts, and a corner failing either is expelled. The local
                // stencil is the sharper test but can only judge corners with three or four
                // neighbours at consecutive indices; the whole-line fit is blunter but reaches
                // the ends of short, holey runs, which is where corners get misassigned.
                std::map<int, double> deviations, pixelDeviations;
                if (leaveOneOutDeviations(alongLine, corners, &deviations, &pixelDeviations)) {
                    std::vector<double> values;
                    for (std::map<int, double>::const_iterator it = deviations.begin();
                         it != deviations.end(); ++it) values.push_back(it->second);
                    const double threshold = std::max(kOutlierSigmas * robustScale(values), kMinOutlierDeviation);
                    for (std::map<int, double>::const_iterator it = deviations.begin();
                         it != deviations.end(); ++it) {
                        if (it->second <= threshold) continue;
                        // Also has to be a real displacement in pixels, not sub-pixel jitter
                        // that a small cell has inflated into a large fraction of a cell.
                        if (pixelDeviations[it->first] <= kMinOutlierPixels) continue;
                        expel[isRow ? siteKey(it->first, fixed) : siteKey(fixed, it->first)] = true;
                    }
                }

                // Collected now and judged once every line has been measured, so the scale can
                // be pooled over the whole lattice. The deviation in pixels travels with each one
                // for the noise floor, the same as above.
                std::map<int, double> wholeLine, wholeLinePixels;
                if (wholeLineDeviations(alongLine, corners, &wholeLine, &wholeLinePixels)) {
                    for (std::map<int, double>::const_iterator it = wholeLine.begin();
                         it != wholeLine.end(); ++it) {
                        wholeLineDeviation.push_back(std::make_pair(
                            isRow ? siteKey(it->first, fixed) : siteKey(fixed, it->first), it->second));
                        wholeLinePixelDeviation.push_back(wholeLinePixels[it->first]);
                        wholeLineValues.push_back(it->second);
                    }
                }
            }
        }

        // Now that every line has been measured, judge the whole-line deviations against one
        // scale drawn from all of them.
        if (!wholeLineValues.empty()) {
            const double threshold = std::max(kWholeLineOutlierSigmas * robustScale(wholeLineValues),
                                              kMinWholeLineDeviation);
            for (size_t i = 0; i < wholeLineDeviation.size(); i++) {
                if (wholeLineDeviation[i].second <= threshold) continue;
                if (wholeLinePixelDeviation[i] <= kMinWholeLinePixels) continue;
                expel[wholeLineDeviation[i].first] = true;
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
                //
                // But only where more than one predictor agreed on the aim. Manufacturing a
                // corner from a single one-sided extrapolation is how a point comes to exist at
                // a position no corner occupies: on a real frame the row's backward cubic
                // predicted 1248.2, 962.8 where the actual junction was at 1239.5, 960.2, the
                // sub-pixel fit found a saddle in the noise of a low-contrast square within the
                // search radius of the prediction, and it scraped the score floor. Worse, the
                // resulting point was then unfalsifiable: the only test that could reach it was
                // the same one-sided cubic that had placed it, against which its deviation read
                // 0.0017 of a cell, while its column, which put it 0.27 of a cell out, had a
                // hole beside it and so could not judge it at all.
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
                const double recoveredScore = bestScoreOverOrientations(gray32, rx, ry, bank);
                if (recoveredScore < kMinScore) continue;

                CornerCandidate recovered;
                recovered.position = refined;
                // The measured score, not the floor it had to clear. Stamping every recovery
                // with kMinScore threw away the one piece of independent evidence a manufactured
                // corner has, and made a strong recovery indistinguishable from a marginal one.
                recovered.score = (float)recoveredScore;
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

namespace {

// A backstop, not the usual reason for stopping: the loop below normally ends when a growth pass
// adds nothing, which happens after 2 to 6 cycles on every real frame measured. It is needed
// because a frame whose lattice is junk can oscillate indefinitely, with refinement expelling a
// handful of corners and growth putting them straight back.
const int kMaxAssemblyCycles = 8;

// Presents an already-assembled lattice as a seed, so growth can be run again from it.
SeedLattice seedFromLattice(const GrownLattice &lattice)
{
    SeedLattice seed;
    seed.basis = lattice.basis;
    seed.cornerIndex = lattice.cornerIndex;
    seed.ij = lattice.ij;
    seed.status = "Re-seeded from the previous growth and refinement cycle.";
    seed.valid = lattice.valid && !lattice.cornerIndex.empty();
    return seed;
}

}   // anonymous namespace

RefinementResult assembleLattice(std::vector<CornerCandidate> &corners,
                                 const SeedLattice &seed,
                                 const cv::Mat &gray,
                                 cv::Size imageSize,
                                 GrownLattice *initialGrowth)
{
    RefinementResult result;
    GrownLattice lattice = growLattice(corners, seed, imageSize);
    if (initialGrowth != 0) *initialGrowth = lattice;
    if (!lattice.valid) {
        result.status = "Grid growth did not run, so there was nothing to refine.";
        return result;
    }

    int cycles = 0;
    int totalRemoved = 0;
    int totalRecovered = 0;
    for (; cycles < kMaxAssemblyCycles; cycles++) {
        const size_t sitesBefore = lattice.cornerIndex.size();
        result = refineLattice(corners, lattice, gray);
        totalRemoved += result.outliersRemoved;
        totalRecovered += result.cornersRecovered;

        const GrownLattice regrown = growLattice(corners, seedFromLattice(result.lattice), imageSize);
        if (!regrown.valid) break;
        // Compared against the count before this cycle's refinement, not after it, so the test is
        // monotone in the grown count and cannot be satisfied merely by refinement having expelled
        // something that growth then replaces.
        if (regrown.cornerIndex.size() <= sitesBefore) break;
        lattice = regrown;
    }

    // The lattice handed back has to be a refined one, so refine whatever the last growth produced.
    result = refineLattice(corners, lattice, gray);
    totalRemoved += result.outliersRemoved;
    totalRecovered += result.cornersRecovered;
    result.outliersRemoved = totalRemoved;
    result.cornersRecovered = totalRecovered;

    std::ostringstream message;
    message << "Assembled over " << (cycles + 1) << " growth and refinement cycle"
            << (cycles == 0 ? "" : "s") << ": removed " << totalRemoved
            << " corners lying off their line and recovered " << totalRecovered
            << " by searching the image where the grid predicted a corner. Lattice now "
            << result.lattice.cornerIndex.size() << " corners.";
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
            // Split on long holes for the same reason extractPlumblines does: a diagonal
            // bridging a hole the lattice only ever grew around is not vouched for, and a
            // hold-out check is worthless if the held-out constraint is itself wrong.
            std::vector<cv::Point2f> run;
            int lastI = 0;
            bool haveLast = false;
            for (int i = lattice.minI; i <= lattice.maxI; i++) {
                const int j = (family == 0) ? (i - constant) : (constant - i);
                if (j < lattice.minJ || j > lattice.maxJ) continue;
                std::map<long long, int>::const_iterator it = site.find(siteKey(i, j));
                if (it == site.end()) continue;
                if (haveLast && i - lastI > kMaxBridgedCells) {
                    if ((int)run.size() >= minPoints) runs.push_back(run);
                    run.clear();
                }
                run.push_back(corners[it->second].position);
                lastI = i;
                haveLast = true;
            }
            (void)step;
            if ((int)run.size() >= minPoints) runs.push_back(run);
        }
    }
    return runs;
}

}   // namespace vidsync
