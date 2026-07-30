// Production-equivalent plumbline distortion objective, gate, and solver for VidSync.
//
// This is NOT a reimplementation. The distortion map, the orthogonal-regression line cost, the
// acceptance gate, and the Nelder-Mead driver are transcribed VERBATIM from
// VidSync/Model Classes/VSCalibration.mm, with NSPoint replaced by a two-double struct (NSPoint is
// CGPoint, i.e. two CGFloats, i.e. two doubles on every 64-bit Mac) and with the same GSL
// nmsimplex2 minimizer production uses. Nothing about the arithmetic, the summation order, the
// parameter scaling, the step sizes, or the stopping rule is altered.
//
// Build:
//   clang++ -O2 -std=c++17 plumb_oracle.cpp -o plumb_oracle \
//     -I../../gsl-2.6-universal ../../gsl-2.6-universal/libgsl.a -framework Accelerate
//
// The GSL that gets linked matters. The app links its own bundled gsl-2.6-universal/libgsl.a
// (GSL 2.6); the system /usr/local GSL here is 2.7.1, and nmsimplex2 built against 2.7.1 does not
// follow the same trajectory. Link the bundled 2.6 or the replay is not a replay.
//
// Traceability:
//   orthogonalRegressionLineCostFunction     VSCalibration.mm:37
//   orthogonalRegressionTotalCostFunction    VSCalibration.mm:76
//   undistortPoint                           VSCalibration.mm:219
//   undistortionJacobian                     VSCalibration.mm:228
//   reasonToRejectSolvedDistortion:...       VSCalibration.mm:2243
//   calculateDistortionCorrection            VSCalibration.mm:2308
//   SCALE_FACTOR_*                           VSCalibration.h:35-47
//
// stdin protocol (whitespace separated):
//   mode                       one of: eval  solve  map
//   13 doubles                 theta in RAW units (evaluation point, or solve start override)
//   1 int                      useProductionStart: 1 = ignore theta and start where production does
//   1 double 1 double          frame width, height (for the whole-frame determinant warning)
//   1 int 1 double             maxIterations, simplex size tolerance
//   1 int                      number of lines
//   per line: 1 int count, then count pairs of x y
//   1 int                      number of extra map-query points, then that many x y pairs
//
// stdout: keyword-prefixed lines, one record per line, all doubles at %.17g.

// The app compiles VSCalibration.mm with Accelerate in scope, so GSL's own cblas declarations are
// suppressed there and the CBLAS_* enums come from Accelerate. Reproduced here so that this file
// can link against the app's own bundled gsl-2.6-universal/libgsl.a, whose headers assume exactly
// that arrangement. Linking a different GSL than the app links is itself a solver-parity failure.
#include <Accelerate/Accelerate.h>
#define __GSL_CBLAS_H__
#include <gsl/gsl_multimin.h>
#include <gsl/gsl_vector.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

// ------------------------------------------------------------------ VSCalibration.h:35-47
#define SCALE_FACTOR_X0 1.0e3
#define SCALE_FACTOR_Y0 1.0e3
#define SCALE_FACTOR_K1 5.0e-8
#define SCALE_FACTOR_K2 1.0e-14
#define SCALE_FACTOR_K3 1.0e-21
#define SCALE_FACTOR_K4 1.0e-27
#define SCALE_FACTOR_K5 1.0e-34
#define SCALE_FACTOR_K6 1.0e-40
#define SCALE_FACTOR_K7 1.0e-43
#define SCALE_FACTOR_P1 1.0e-7
#define SCALE_FACTOR_P2 1.0e-7
#define SCALE_FACTOR_P3 1.0e-7
#define SCALE_FACTOR_P4 1.0e-10

struct NSPoint { double x, y; };
static NSPoint NSMakePoint(double x, double y) { NSPoint p; p.x = x; p.y = y; return p; }

struct Plumblines {
    size_t numLines;
    NSPoint **lines;
    size_t *lineLengths;
};

// ------------------------------------------------------------------ VSCalibration.mm:219, verbatim
NSPoint undistortPoint(const NSPoint* pt, const double x0, const double y0, const double k1,
                       const double k2, const double k3, const double k4, const double k5,
                       const double k6, const double k7, const double p1, const double p2,
                       const double p3, const double p4) {
    const double xd = pt->x - x0;
    const double yd = pt->y - y0;
    const double rs = xd*xd + yd*yd;
    const double xu = x0 + xd*(1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + k4*pow(rs,4) + k5*pow(rs,5) + k6*pow(rs,6) + k7*pow(rs,7)) + (p1*(rs + 2*xd*xd) + 2*p2*xd*yd)*(1 + p3*rs + p4*rs*rs);
    const double yu = y0 + yd*(1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + k4*pow(rs,4) + k5*pow(rs,5) + k6*pow(rs,6) + k7*pow(rs,7)) + (2*p1*xd*yd + p2*(rs + 2*yd*yd))*(1 + p3*rs + p4*rs*rs);
    return NSMakePoint(xu, yu);
}

// ------------------------------------------------------------------ VSCalibration.mm:228, verbatim
void undistortionJacobian(const double xd, const double yd, const double k1, const double k2,
                          const double k3, const double k4, const double k5, const double k6,
                          const double k7, const double p1, const double p2, const double p3,
                          const double p4, double J[4]);

// ------------------------------------------------------------------ VSCalibration.mm:37, verbatim
double orthogonalRegressionLineCostFunction(NSPoint line[], const size_t numLinePoints)
{
    if (numLinePoints < 3) return 0.0;
    NSPoint centroid = NSMakePoint(0.0,0.0);
    for (int i = 0; i < numLinePoints; i++) {
        centroid.x += line[i].x;
        centroid.y += line[i].y;
    }
    centroid.x = centroid.x / (double) numLinePoints;
    centroid.y = centroid.y / (double) numLinePoints;
    double mainsum = 0.0;
    double mainsqsum = 0.0;
    for (int i = 0; i < numLinePoints; i++) {
        mainsum += (line[i].x - centroid.x) * (line[i].y - centroid.y);
        mainsqsum += (pow((line[i].x - centroid.x),2.0) - pow((line[i].y - centroid.y),2.0));
    }
    if (mainsum == 0.0 && mainsqsum == 0.0) return 0.0;
    const double theta = 0.5 * atan2(2.0 * mainsum, mainsqsum);
    const double sinTheta = sin(theta);
    const double cosTheta = cos(theta);
    double ssq = 0.0;
    for (int i = 0; i < numLinePoints; i++) {
        ssq += pow(-(line[i].x - centroid.x) * sinTheta + (line[i].y - centroid.y) * cosTheta,2.0);
    }
    return ssq;
}

// The same function again, additionally reporting the signed per-point residual and the fitted
// angle. Every arithmetic step above is reproduced unchanged; only the extra outputs are new, so
// the reported residuals are exactly the quantities production squares and sums.
double orthogonalRegressionLineDetail(NSPoint line[], const size_t numLinePoints,
                                      double *resid, double *thetaOut, NSPoint *centroidOut)
{
    if (numLinePoints < 3) { *thetaOut = NAN; return 0.0; }
    NSPoint centroid = NSMakePoint(0.0,0.0);
    for (int i = 0; i < numLinePoints; i++) { centroid.x += line[i].x; centroid.y += line[i].y; }
    centroid.x = centroid.x / (double) numLinePoints;
    centroid.y = centroid.y / (double) numLinePoints;
    double mainsum = 0.0, mainsqsum = 0.0;
    for (int i = 0; i < numLinePoints; i++) {
        mainsum += (line[i].x - centroid.x) * (line[i].y - centroid.y);
        mainsqsum += (pow((line[i].x - centroid.x),2.0) - pow((line[i].y - centroid.y),2.0));
    }
    *centroidOut = centroid;
    if (mainsum == 0.0 && mainsqsum == 0.0) {
        *thetaOut = NAN;
        for (size_t i = 0; i < numLinePoints; i++) resid[i] = 0.0;
        return 0.0;
    }
    const double theta = 0.5 * atan2(2.0 * mainsum, mainsqsum);
    const double sinTheta = sin(theta);
    const double cosTheta = cos(theta);
    double ssq = 0.0;
    for (int i = 0; i < numLinePoints; i++) {
        const double r = -(line[i].x - centroid.x) * sinTheta + (line[i].y - centroid.y) * cosTheta;
        resid[i] = r;
        ssq += pow(r,2.0);
    }
    *thetaOut = theta;
    return ssq;
}

// ------------------------------------------------------------------ VSCalibration.mm:76, verbatim
double orthogonalRegressionTotalCostFunction(const gsl_vector *v, void *params){
    Plumblines* p = (Plumblines*) params;
    double x0,y0,k1,k2,k3,k4,k5,k6,k7,p1,p2,p3,p4;
    x0 = gsl_vector_get(v,0) * SCALE_FACTOR_X0;
    y0 = gsl_vector_get(v,1) * SCALE_FACTOR_Y0;
    k1 = gsl_vector_get(v,2) * SCALE_FACTOR_K1;
    k2 = gsl_vector_get(v,3) * SCALE_FACTOR_K2;
    k3 = gsl_vector_get(v,4) * SCALE_FACTOR_K3;
    k4 = gsl_vector_get(v,5) * SCALE_FACTOR_K4;
    k5 = gsl_vector_get(v,6) * SCALE_FACTOR_K5;
    k6 = gsl_vector_get(v,7) * SCALE_FACTOR_K6;
    k7 = gsl_vector_get(v,8) * SCALE_FACTOR_K7;
    p1 = gsl_vector_get(v,9) * SCALE_FACTOR_P1;
    p2 = gsl_vector_get(v,10) * SCALE_FACTOR_P2;
    p3 = gsl_vector_get(v,11) * SCALE_FACTOR_P3;
    p4 = gsl_vector_get(v,12) * SCALE_FACTOR_P4;
    Plumblines up;
    up.numLines = p->numLines;
    up.lines = (NSPoint **) malloc(up.numLines*sizeof(NSPoint *));
    up.lineLengths = (size_t *) malloc(up.numLines*sizeof(size_t *));
    for (int i = 0; i < up.numLines; i++) {
        up.lineLengths[i] = p->lineLengths[i];
        up.lines[i] = (NSPoint *) malloc(up.lineLengths[i]*sizeof(NSPoint));
        for (int j = 0; j < up.lineLengths[i]; j++) {
            up.lines[i][j] = undistortPoint(&(p->lines[i][j]),x0,y0,k1,k2,k3,k4,k5,k6,k7,p1,p2,p3,p4);
        }
    }
    double totalSSQRCost = 0.0;
    for (int i = 0; i < up.numLines; i++) {
        totalSSQRCost += orthogonalRegressionLineCostFunction(up.lines[i], up.lineLengths[i]);
    }
    for (int i = 0; i < up.numLines; i++) free(up.lines[i]);
    free(up.lines);
    free(up.lineLengths);
    return totalSSQRCost;
}

// ------------------------------------------------------------------ eta extension and masking
//
// Everything above is production. What follows adds two things production does not have: a scalar
// anisotropic-radius parameter eta, and the ability to hold a subset of parameters at exactly zero
// while the simplex works on the rest. Neither alters the arithmetic above.
//
// eta uses the same conjugated form as oracle.cpp:60-62, U(x) = c + A^-1 B(A (x - c)) with
// A = diag(e^eta, e^-eta). At eta == 0.0 this function DELEGATES to undistortPoint, so the eta = 0
// nesting is bit-exact by construction rather than by appeal to exp(0) == 1.
//
// eta's own scaling and simplex step size have no production precedent, because production has no
// eta. SCALE_FACTOR_ETA is chosen so the fitted values (~0.008 to 0.011) sit near 1 in scaled units,
// matching the O(1)-O(100) range production's own scalings produce, and the step size below is the
// same order as the value, which is what production's 25 is relative to its typical scaled
// coefficient. Both are stated here rather than buried.
#define SCALE_FACTOR_ETA 1.0e-2
#define STEP_ETA 1.0

static NSPoint undistortPointEta(const NSPoint* pt, const double* t, const double eta) {
    if (eta == 0.0) {
        return undistortPoint(pt, t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9],
                              t[10], t[11], t[12]);
    }
    const double ax = exp(eta), ay = 1.0 / ax;
    const double xd = (pt->x - t[0]) * ax;
    const double yd = (pt->y - t[1]) * ay;
    const double rs = xd*xd + yd*yd;
    const double R = 1 + t[2]*rs + t[3]*pow(rs,2) + t[4]*pow(rs,3) + t[5]*pow(rs,4) + t[6]*pow(rs,5) + t[7]*pow(rs,6) + t[8]*pow(rs,7);
    const double T = 1 + t[11]*rs + t[12]*rs*rs;
    const double ux = xd*R + (t[9]*(rs + 2*xd*xd) + 2*t[10]*xd*yd)*T;
    const double uy = yd*R + (2*t[9]*xd*yd + t[10]*(rs + 2*yd*yd))*T;
    return NSMakePoint(t[0] + ux/ax, t[1] + uy/ay);
}

static const double SCALES14[14] = {SCALE_FACTOR_X0, SCALE_FACTOR_Y0, SCALE_FACTOR_K1,
    SCALE_FACTOR_K2, SCALE_FACTOR_K3, SCALE_FACTOR_K4, SCALE_FACTOR_K5, SCALE_FACTOR_K6,
    SCALE_FACTOR_K7, SCALE_FACTOR_P1, SCALE_FACTOR_P2, SCALE_FACTOR_P3, SCALE_FACTOR_P4,
    SCALE_FACTOR_ETA};

struct Masked {
    Plumblines* p;
    double base[14];            // full parameter vector in SCALED units; held entries stay put
    int freeIdx[14];
    int nfree;
};

// The same total cost as orthogonalRegressionTotalCostFunction, over the free coordinates only.
// With nfree == 13, the free set 0..12 and eta held at 0, it returns a bit-identical value: the
// denormalization is the same multiplication and undistortPointEta delegates.
static double maskedCost(const gsl_vector *v, void *params) {
    Masked* m = (Masked*) params;
    double s[14];
    for (int i = 0; i < 14; i++) s[i] = m->base[i];
    for (int i = 0; i < m->nfree; i++) s[m->freeIdx[i]] = gsl_vector_get(v, i);
    double t[13];
    for (int i = 0; i < 13; i++) t[i] = s[i] * SCALES14[i];
    const double eta = s[13] * SCALE_FACTOR_ETA;
    Plumblines* p = m->p;
    double totalSSQRCost = 0.0;
    for (size_t i = 0; i < p->numLines; i++) {
        NSPoint* u = (NSPoint *) malloc(p->lineLengths[i]*sizeof(NSPoint));
        for (size_t j = 0; j < p->lineLengths[i]; j++)
            u[j] = undistortPointEta(&(p->lines[i][j]), t, eta);
        totalSSQRCost += orthogonalRegressionLineCostFunction(u, p->lineLengths[i]);
        free(u);
    }
    return totalSSQRCost;
}

// ------------------------------------------------------------------ VSCalibration.mm:228, verbatim
void undistortionJacobian(const double xd, const double yd, const double k1, const double k2,
                          const double k3, const double k4, const double k5, const double k6,
                          const double k7, const double p1, const double p2, const double p3,
                          const double p4, double J[4]){
    const double s = xd*xd + yd*yd;
    const double R = 1.0 + k1*s + k2*pow(s,2) + k3*pow(s,3) + k4*pow(s,4) + k5*pow(s,5) + k6*pow(s,6) + k7*pow(s,7);
    const double Rp = k1 + 2*k2*s + 3*k3*pow(s,2) + 4*k4*pow(s,3) + 5*k5*pow(s,4) + 6*k6*pow(s,5) + 7*k7*pow(s,6);
    const double T = 1.0 + p3*s + p4*s*s;
    const double Tp = p3 + 2*p4*s;
    const double Gx = p1*(3*xd*xd + yd*yd) + 2*p2*xd*yd;
    const double Gy = 2*p1*xd*yd + p2*(xd*xd + 3*yd*yd);
    J[0] = R + 2*xd*xd*Rp + (6*p1*xd + 2*p2*yd)*T + 2*xd*Gx*Tp;
    J[1] = 2*xd*yd*Rp + (2*p1*yd + 2*p2*xd)*T + 2*yd*Gx*Tp;
    J[2] = 2*xd*yd*Rp + (2*p1*yd + 2*p2*xd)*T + 2*xd*Gy*Tp;
    J[3] = R + 2*yd*yd*Rp + (2*p1*xd + 6*p2*yd)*T + 2*yd*Gy*Tp;
}

// ------------------------------------------------------------------ VSCalibration.mm:2240-2306
static const double kMinAcceptableScaleRatio = 0.25;
static const double kMaxAcceptableScaleRatio = 4.0;

struct GateResult {
    bool ok; std::string reason; std::string warning;
    double minDetBox, scaleRatio, minDetFrame;
};

static GateResult reasonToRejectSolvedDistortion(const double *solved,
                                                 double bx, double by, double bw, double bh,
                                                 double clipW, double clipH)
{
    GateResult g; g.ok = true; g.minDetBox = INFINITY; g.scaleRatio = NAN; g.minDetFrame = INFINITY;
    static const char *paramNames[13] = {"center X","center Y","K1","K2","K3","K4","K5","K6","K7","P1","P2","P3","P4"};
    for (int i = 0; i < 13; i++) {
        if (!std::isfinite(solved[i])) {
            g.ok = false;
            g.reason = std::string("non-finite value for ") + paramNames[i];
            return g;
        }
    }
    const double x0 = solved[0];
    const double y0 = solved[1];
    const int gridSteps = 24;
    double minDeterminantInBox = INFINITY;
    double totalUndistortedRadius = 0.0;
    double totalDistortedRadius = 0.0;
    for (int i = 0; i <= gridSteps; i++) {
        for (int j = 0; j <= gridSteps; j++) {
            const double gx = bx + bw * ((double) i / gridSteps);
            const double gy = by + bh * ((double) j / gridSteps);
            double J[4];
            undistortionJacobian(gx - x0, gy - y0, solved[2], solved[3], solved[4], solved[5], solved[6], solved[7], solved[8], solved[9], solved[10], solved[11], solved[12], J);
            const double determinant = J[0]*J[3] - J[1]*J[2];
            if (!std::isfinite(determinant)) {
                g.ok = false; g.reason = "non-finite Jacobian determinant"; return g;
            }
            if (determinant < minDeterminantInBox) minDeterminantInBox = determinant;
            NSPoint gridPoint = NSMakePoint(gx, gy);
            NSPoint undistorted = undistortPoint(&gridPoint, x0, y0, solved[2], solved[3], solved[4], solved[5], solved[6], solved[7], solved[8], solved[9], solved[10], solved[11], solved[12]);
            totalUndistortedRadius += hypot(undistorted.x - x0, undistorted.y - y0);
            totalDistortedRadius += hypot(gx - x0, gy - y0);
        }
    }
    g.minDetBox = minDeterminantInBox;
    if (minDeterminantInBox <= 0.0) {
        g.ok = false; g.reason = "folds over inside the plumbline box"; return g;
    }
    if (totalDistortedRadius > 0.0) {
        const double scaleRatio = totalUndistortedRadius / totalDistortedRadius;
        g.scaleRatio = scaleRatio;
        if (scaleRatio < kMinAcceptableScaleRatio || scaleRatio > kMaxAcceptableScaleRatio) {
            g.ok = false; g.reason = "radial scale ratio outside (0.25, 4.0)"; return g;
        }
    }
    double minDeterminantInFrame = INFINITY;
    if (clipW > 0.0 && clipH > 0.0) {
        for (int i = 0; i <= gridSteps; i++) {
            for (int j = 0; j <= gridSteps; j++) {
                double J[4];
                undistortionJacobian(clipW * ((double) i / gridSteps) - x0, clipH * ((double) j / gridSteps) - y0, solved[2], solved[3], solved[4], solved[5], solved[6], solved[7], solved[8], solved[9], solved[10], solved[11], solved[12], J);
                const double determinant = J[0]*J[3] - J[1]*J[2];
                if (std::isfinite(determinant) && determinant < minDeterminantInFrame) minDeterminantInFrame = determinant;
            }
        }
        g.minDetFrame = minDeterminantInFrame;
        if (minDeterminantInFrame <= 0.0) g.warning = "folds over outside the plumbline box";
    }
    return g;
}

// ------------------------------------------------------------------ driver

static const double SCALES[13] = {SCALE_FACTOR_X0, SCALE_FACTOR_Y0, SCALE_FACTOR_K1,
    SCALE_FACTOR_K2, SCALE_FACTOR_K3, SCALE_FACTOR_K4, SCALE_FACTOR_K5, SCALE_FACTOR_K6,
    SCALE_FACTOR_K7, SCALE_FACTOR_P1, SCALE_FACTOR_P2, SCALE_FACTOR_P3, SCALE_FACTOR_P4};

static void emitEval(const double *theta, Plumblines &p, int totalPointCount)
{
    gsl_vector *v = gsl_vector_alloc(13);
    for (int i = 0; i < 13; i++) gsl_vector_set(v, i, theta[i] / SCALES[i]);
    const double sse = orthogonalRegressionTotalCostFunction(v, &p);
    gsl_vector_free(v);
    printf("SSE %.17g\n", sse);
    printf("NCOST %d\n", totalPointCount);
    printf("RMS %.17g\n", sqrt(sse / (double) totalPointCount));
    // per-line and per-point detail at exactly this theta
    double checkSum = 0.0;
    for (size_t i = 0; i < p.numLines; i++) {
        std::vector<NSPoint> u(p.lineLengths[i]);
        for (size_t j = 0; j < p.lineLengths[i]; j++) {
            u[j] = undistortPoint(&(p.lines[i][j]), theta[0], theta[1], theta[2], theta[3],
                                  theta[4], theta[5], theta[6], theta[7], theta[8], theta[9],
                                  theta[10], theta[11], theta[12]);
        }
        std::vector<double> r(p.lineLengths[i], 0.0);
        double th; NSPoint cen;
        const double lsse = orthogonalRegressionLineDetail(u.data(), p.lineLengths[i], r.data(), &th, &cen);
        checkSum += lsse;
        printf("LINE %zu %zu %.17g %.17g %.17g %.17g\n", i, p.lineLengths[i], lsse, th, cen.x, cen.y);
        for (size_t j = 0; j < p.lineLengths[i]; j++)
            printf("RESID %zu %zu %.17g %.17g %.17g\n", i, j, r[j], u[j].x, u[j].y);
    }
    printf("SSECHECK %.17g\n", checkSum);
}

int main()
{
    std::string mode;
    if (!(std::cin >> mode)) return 1;
    double theta[13];
    for (int i = 0; i < 13; i++) std::cin >> theta[i];
    int useProductionStart; std::cin >> useProductionStart;
    double frameW, frameH; std::cin >> frameW >> frameH;
    int maxIter; double sizeTol; std::cin >> maxIter >> sizeTol;
    size_t nlines; std::cin >> nlines;

    Plumblines p;
    p.numLines = nlines;
    p.lines = (NSPoint **) malloc(nlines * sizeof(NSPoint *));
    p.lineLengths = (size_t *) malloc(nlines * sizeof(size_t));
    int totalPointCount = 0;
    double minX = INFINITY, minY = INFINITY, maxX = -INFINITY, maxY = -INFINITY;
    for (size_t i = 0; i < nlines; i++) {
        size_t c; std::cin >> c;
        p.lineLengths[i] = c;
        if (c >= 3) totalPointCount += (int) c;
        p.lines[i] = (NSPoint *) malloc(c * sizeof(NSPoint));
        for (size_t j = 0; j < c; j++) {
            double x, y; std::cin >> x >> y;
            // Production reads these through -floatValue (VSCalibration.mm:2330). Every stored
            // coordinate in these documents is exactly float-representable, verified separately,
            // so the cast is applied here too and is provably lossless on this data.
            p.lines[i][j] = NSMakePoint((double)(float) x, (double)(float) y);
            minX = fmin(minX, p.lines[i][j].x); maxX = fmax(maxX, p.lines[i][j].x);
            minY = fmin(minY, p.lines[i][j].y); maxY = fmax(maxY, p.lines[i][j].y);
        }
    }
    int nq; std::cin >> nq;
    std::vector<NSPoint> q(nq);
    for (int i = 0; i < nq; i++) std::cin >> q[i].x >> q[i].y;

    // Optional trailing fields, appended so that callers written before the eta extension keep
    // working unchanged: eta in RAW units, then 14 zero/one flags marking the free parameters.
    // Absent, they default to eta = 0 and all thirteen Brown-Conrady parameters free, which is
    // exactly the pre-extension behaviour.
    double eta = 0.0;
    int freeFlags[14];
    for (int i = 0; i < 13; i++) freeFlags[i] = 1;
    freeFlags[13] = 0;
    if (std::cin >> eta) {
        int f[14];
        bool got = true;
        for (int i = 0; i < 14 && got; i++) got = (bool)(std::cin >> f[i]);
        if (got) for (int i = 0; i < 14; i++) freeFlags[i] = f[i];
    } else {
        eta = 0.0;
    }

    printf("BOX %.17g %.17g %.17g %.17g\n", minX, minY, maxX - minX, maxY - minY);
    printf("NCOSTPOINTS %d\n", totalPointCount);
    printf("ETASCALE %.17g\n", (double) SCALE_FACTOR_ETA);

    if (mode == "eval" || mode == "map") {
        if (eta != 0.0) {
            // eta-aware evaluation: the same per-line cost, the conjugated map
            double sse = 0.0;
            for (size_t i = 0; i < p.numLines; i++) {
                std::vector<NSPoint> u(p.lineLengths[i]);
                for (size_t j = 0; j < p.lineLengths[i]; j++)
                    u[j] = undistortPointEta(&(p.lines[i][j]), theta, eta);
                std::vector<double> r(p.lineLengths[i], 0.0);
                double th; NSPoint cen;
                const double lsse = orthogonalRegressionLineDetail(u.data(), p.lineLengths[i],
                                                                   r.data(), &th, &cen);
                sse += lsse;
                printf("LINE %zu %zu %.17g %.17g %.17g %.17g\n", i, p.lineLengths[i], lsse, th,
                       cen.x, cen.y);
                for (size_t j = 0; j < p.lineLengths[i]; j++)
                    printf("RESID %zu %zu %.17g %.17g %.17g\n", i, j, r[j], u[j].x, u[j].y);
            }
            printf("SSE %.17g\n", sse);
            printf("NCOST %d\n", totalPointCount);
            printf("RMS %.17g\n", sqrt(sse / (double) totalPointCount));
            printf("SSECHECK %.17g\n", sse);
            for (int i = 0; i < nq; i++) {
                NSPoint u = undistortPointEta(&q[i], theta, eta);
                printf("MAP %d %.17g %.17g\n", i, u.x, u.y);
            }
            // The gate is a 13-parameter construct; report it on the Brown-Conrady core, which is
            // what production would judge, and say so rather than inventing an eta-aware gate.
            GateResult ge = reasonToRejectSolvedDistortion(theta, minX, minY, maxX - minX,
                                                          maxY - minY, frameW, frameH);
            printf("GATE %d %.17g %.17g %.17g |%s|%s|\n", ge.ok ? 1 : 0, ge.minDetBox, ge.scaleRatio,
                   ge.minDetFrame, ge.reason.c_str(), ge.warning.c_str());
            return 0;
        }
        emitEval(theta, p, totalPointCount);
        GateResult g = reasonToRejectSolvedDistortion(theta, minX, minY, maxX - minX, maxY - minY,
                                                      frameW, frameH);
        printf("GATE %d %.17g %.17g %.17g |%s|%s|\n", g.ok ? 1 : 0, g.minDetBox, g.scaleRatio,
               g.minDetFrame, g.reason.c_str(), g.warning.c_str());
        for (int i = 0; i < nq; i++) {
            NSPoint u = undistortPoint(&q[i], theta[0], theta[1], theta[2], theta[3], theta[4],
                                       theta[5], theta[6], theta[7], theta[8], theta[9], theta[10],
                                       theta[11], theta[12]);
            printf("MAP %d %.17g %.17g\n", i, u.x, u.y);
        }
        return 0;
    }

    if (mode != "solve") { fprintf(stderr, "unknown mode %s\n", mode.c_str()); return 2; }

    // ---------------------------------------------- calculateDistortionCorrection, VSCalibration.mm:2341
    const gsl_multimin_fminimizer_type *T = gsl_multimin_fminimizer_nmsimplex2;
    gsl_multimin_fminimizer *s = NULL;
    gsl_vector *ss, *x;
    gsl_multimin_function minex_func;
    size_t iter = 0;
    int status;
    double size;
    // Full scaled start vector. Held coordinates are forced to exactly zero, so a seed can never
    // leak a value into a parameter the model does not have.
    Masked m;
    m.p = &p;
    for (int i = 0; i < 13; i++) {
        m.base[i] = useProductionStart ? 0.0 : theta[i] / SCALES14[i];
    }
    m.base[13] = eta / SCALE_FACTOR_ETA;
    if (useProductionStart) {
        m.base[0] = (frameW/2.0) / SCALE_FACTOR_X0;
        m.base[1] = (frameH/2.0) / SCALE_FACTOR_Y0;
    }
    m.nfree = 0;
    for (int i = 0; i < 14; i++) {
        if (freeFlags[i]) m.freeIdx[m.nfree++] = i;
        else m.base[i] = 0.0;
    }
    if (m.nfree == 0) { fprintf(stderr, "no free parameters\n"); return 3; }
    int nparams = m.nfree;
    x = gsl_vector_alloc(nparams);
    for (int i = 0; i < nparams; i++) gsl_vector_set(x, i, m.base[m.freeIdx[i]]);
    ss = gsl_vector_alloc(nparams);
    for (int i = 0; i < nparams; i++) {
        const int j = m.freeIdx[i];
        gsl_vector_set(ss, i, j < 2 ? 0.001 : (j == 13 ? STEP_ETA : 25.0));
    }
    minex_func.n = nparams;
    minex_func.f = maskedCost;
    minex_func.params = &m;
    s = gsl_multimin_fminimizer_alloc(T, nparams);
    gsl_multimin_fminimizer_set(s, &minex_func, x, ss);
    double initial_cost_function_value = maskedCost(x, &m);
    double final_cost_function_value = 0.0;
    size = NAN;
    do {
        iter++;
        status = gsl_multimin_fminimizer_iterate(s);
        if (status) break;
        size = gsl_multimin_fminimizer_size(s);
        status = gsl_multimin_test_size(size, sizeTol);
    } while (status == GSL_CONTINUE && iter < (size_t) maxIter);
    final_cost_function_value = s->fval;
    double sfull[14];
    for (int i = 0; i < 14; i++) sfull[i] = m.base[i];
    for (int i = 0; i < nparams; i++) sfull[m.freeIdx[i]] = gsl_vector_get(s->x, i);
    double solved[13];
    for (int i = 0; i < 13; i++) solved[i] = sfull[i] * SCALES14[i];
    const double solvedEta = sfull[13] * SCALE_FACTOR_ETA;
    printf("SOLVEDETA %.17g\n", solvedEta);
    printf("NFREE %d\n", nparams);

    printf("INITIALSSE %.17g\n", initial_cost_function_value);
    printf("FINALSSE %.17g\n", final_cost_function_value);
    printf("ITERS %zu\n", iter);
    printf("SIMPLEXSIZE %.17g\n", size);
    printf("STATUS %d\n", status);
    printf("SOLVED");
    for (int i = 0; i < 13; i++) printf(" %.17g", solved[i]);
    printf("\n");
    printf("REMAININGPERPOINT %.17g\n", sqrt(final_cost_function_value / (double) totalPointCount));
    printf("REDUCTION %.17g\n",
           (sqrt(initial_cost_function_value/totalPointCount) - sqrt(final_cost_function_value/totalPointCount))
           / sqrt(initial_cost_function_value/totalPointCount));
    GateResult g = reasonToRejectSolvedDistortion(solved, minX, minY, maxX - minX, maxY - minY,
                                                  frameW, frameH);
    printf("GATE %d %.17g %.17g %.17g |%s|%s|\n", g.ok ? 1 : 0, g.minDetBox, g.scaleRatio,
           g.minDetFrame, g.reason.c_str(), g.warning.c_str());
    gsl_vector_free(x);
    gsl_vector_free(ss);
    gsl_multimin_fminimizer_free(s);
    return 0;
}
