// Production-faithful calibration oracle for VidSync.
//
// This is NOT a reimplementation of the numerics. It calls the same libraries production calls --
// Accelerate's LAPACK dgesvd / dgetrf / dgetri and cblas_dgemm, and GSL's hybrids multiroot solver --
// through the same call sequences, with the geometry transcribed verbatim from
// VidSync/Model Classes/VSCalibration.mm. The only things reimplemented are the plain arithmetic
// helpers (VSPoint3D ops, line-plane intersection), which are unambiguous.
//
// Reads a plain-text problem description on stdin and writes results to stdout, so the Python
// harness owns all database access and comparison.
//
// Build:
//   clang++ -O2 -std=c++17 oracle.cpp -o oracle \
//     -I/usr/local/include -L/usr/local/lib -lgsl -lgslcblas \
//     -framework Accelerate
//
// Traceability:
//   undistortPoint                          VSCalibration.mm:219
//   putLeastSquaresSolutionForOverdetermined VSCalibration.mm:2511
//   arrange2DArray (column major)            VSCalibration.mm:2560
//   invert3x3Matrix                          VSCalibration.mm:1477
//   rightMultiply3x3Matrix                   VSCalibration.mm:2496
//   calculateMatrix:correctRefraction:       VSCalibration.mm:1179
//   refractionRootFunc_f                     VSCalibration.mm:370
//   refractionCorrectApparentPosition...     VSCalibration.mm:1316
//   calculateCameraPosition                  VSCalibration.mm:1129
//   intersectionOfNumber:of3DLines:          UtilityFunctions.mm:255
//   calculateCalibration front/back ordering VSCalibration.mm:1045-1064

#include <Accelerate/Accelerate.h>
// GSL ships its own cblas declarations which collide with Accelerate's. We use Accelerate's BLAS
// and LAPACK (as production does, via the Accelerate framework) and only need GSL's multiroot
// solver, so suppress GSL's cblas header by pre-defining its include guard.
#define __GSL_CBLAS_H__
#include <gsl/gsl_multiroots.h>
#include <gsl/gsl_vector.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

struct P3 { double x, y, z; };
static P3 mk(double x, double y, double z) { P3 p; p.x = x; p.y = y; p.z = z; return p; }
static P3 sub(P3 a, P3 b) { return mk(a.x - b.x, a.y - b.y, a.z - b.z); }
static double nrm(P3 p) { return std::sqrt(p.x * p.x + p.y * p.y + p.z * p.z); }
static double dot(P3 a, P3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static P3 crs(P3 a, P3 b) {
    return mk(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}
static double byName(char n, P3 p) { return n == 'x' ? p.x : (n == 'y' ? p.y : p.z); }

// ---------------------------------------------------------------- distortion (VSCalibration.mm:219)
struct Dist { double t[13]; double eta; };

static void undistort(double xin, double yin, const Dist& d, double* xo, double* yo) {
    const double x0 = d.t[0], y0 = d.t[1];
    // eta conjugation: U = c + A^-1 B(A (x-c)), A = diag(e^eta, e^-eta). eta == 0 reduces exactly
    // to the shipped 13-parameter map because ax == ay == 1 and the divisions are by 1.0.
    const double ax = std::exp(d.eta), ay = std::exp(-d.eta);
    const double xd = (xin - x0) * ax;
    const double yd = (yin - y0) * ay;
    const double rs = xd * xd + yd * yd;
    double rad = 1.0;
    for (int i = 0; i < 7; i++) rad += d.t[2 + i] * std::pow(rs, i + 1);
    const double T = 1.0 + d.t[11] * rs + d.t[12] * rs * rs;
    const double ux = xd * rad + (d.t[9] * (rs + 2 * xd * xd) + 2 * d.t[10] * xd * yd) * T;
    const double uy = yd * rad + (2 * d.t[9] * xd * yd + d.t[10] * (rs + 2 * yd * yd)) * T;
    *xo = x0 + ux / ax;
    *yo = y0 + uy / ay;
}

// ---------------------------------------------------------------- linear algebra, exact transcriptions
static void arrange2D(const std::vector<double>& A, int rows, double* a) {
    for (int v = 0; v < 9; v++)
        for (int u = 0; u < rows; u++) a[v * rows + u] = A[u * 9 + v];
}

static void leastSquaresHomogeneous(const std::vector<double>& A, int rows, double x[9]) {
    char jobu = 'N', jobvt = 'S';
    __CLPK_integer m = rows, n = 9, lda = rows, ldu = 1, ldvt = 9, info;
    std::vector<double> a(rows * 9);
    arrange2D(A, rows, a.data());
    double s[9], u[1], vt[81];
    __CLPK_integer lwork = 64 * rows * 9;
    std::vector<double> work(lwork);
    dgesvd_(&jobu, &jobvt, &m, &n, a.data(), &lda, s, u, &ldu, vt, &ldvt, work.data(), &lwork, &info);
    double c = (vt[80] < 0.0) ? -1.0 : 1.0;
    x[0] = c * vt[8];  x[1] = c * vt[35]; x[2] = c * vt[62];
    x[3] = c * vt[17]; x[4] = c * vt[44]; x[5] = c * vt[71];
    x[6] = c * vt[26]; x[7] = c * vt[53]; x[8] = c * vt[80];
    // report the singular values for diagnostics
    std::printf("SV");
    for (int i = 0; i < 9; i++) std::printf(" %.17g", s[i]);
    std::printf("\n");
}

static void invert3x3(double A[9]) {
    __CLPK_integer m = 3, n = 3, lda = 3, ipiv[3], info;
    dgetrf_(&m, &n, A, &lda, ipiv, &info);
    __CLPK_integer ni = 3, ldai = 3, lwork = 64 * 9, infoi;
    double work[64 * 9];
    dgetri_(&ni, A, &ldai, ipiv, work, &lwork, &infoi);
}

static void rmul3x3(const double A[9], const double B[9], double C[9]) {
    cblas_dgemm(CblasColMajor, CblasNoTrans, CblasNoTrans, 3, 3, 3, 1.0, A, 3, B, 3, 0.0, C, 3);
}

// ---------------------------------------------------------------- refraction (VSCalibration.mm:370)
struct RParams {
    char axisH, axisV;
    double frontSurfaceCoord, backSurfaceCoord;
    P3 realPosition, camPosition;
    double n1, n2, n3;
};

static int refractionRootFunc_f(const gsl_vector* x, void* params, gsl_vector* f) {
    const RParams* p = (RParams*)params;
    const double b1 = gsl_vector_get(x, 0), b2 = gsl_vector_get(x, 1);
    const double f1 = gsl_vector_get(x, 2), f2 = gsl_vector_get(x, 3);
    P3 backI, frontI, nrmI, negN, rpBack, rpFront;
    if (p->axisH == 'x') {
        if (p->axisV == 'y') {
            nrmI = mk(0, 0, 1);
            backI = mk(b1, b2, p->backSurfaceCoord);
            frontI = mk(f1, f2, p->frontSurfaceCoord);
            rpBack = mk(b1, b2, p->realPosition.z);
            rpFront = mk(f1, f2, p->camPosition.z);
        } else {
            nrmI = mk(0, 1, 0);
            backI = mk(b1, p->backSurfaceCoord, b2);
            frontI = mk(f1, p->frontSurfaceCoord, f2);
            rpBack = mk(b1, p->realPosition.y, b2);
            rpFront = mk(f1, p->camPosition.y, f2);
        }
    } else if (p->axisH == 'y') {
        if (p->axisV == 'x') {
            nrmI = mk(0, 0, 1);
            backI = mk(b2, b1, p->backSurfaceCoord);
            frontI = mk(f2, f1, p->frontSurfaceCoord);
            rpBack = mk(b2, b1, p->realPosition.z);
            rpFront = mk(f2, f1, p->camPosition.z);
        } else {
            nrmI = mk(1, 0, 0);
            backI = mk(p->backSurfaceCoord, b1, b2);
            frontI = mk(p->frontSurfaceCoord, f1, f2);
            rpBack = mk(p->realPosition.x, b1, b2);
            rpFront = mk(p->camPosition.x, f1, f2);
        }
    } else {
        if (p->axisV == 'x') {
            nrmI = mk(0, 1, 0);
            backI = mk(b2, p->backSurfaceCoord, b1);
            frontI = mk(f2, p->frontSurfaceCoord, f1);
            rpBack = mk(b2, p->realPosition.y, b1);
            rpFront = mk(f2, p->camPosition.y, f1);
        } else {
            nrmI = mk(1, 0, 0);
            backI = mk(p->backSurfaceCoord, b2, b1);
            frontI = mk(p->frontSurfaceCoord, f2, f1);
            rpBack = mk(p->realPosition.x, b2, b1);
            rpFront = mk(p->camPosition.x, f2, f1);
        }
    }
    negN = mk(-nrmI.x, -nrmI.y, -nrmI.z);
    double nB = nrm(sub(p->realPosition, backI));
    double nM = nrm(sub(frontI, backI));
    double nF = nrm(sub(p->camPosition, frontI));
    auto cl = [](double v) { return std::fmax(-1.0, std::fmin(1.0, v)); };
    const double tBI = (nB > 0.0) ? std::acos(cl(dot(nrmI, sub(p->realPosition, backI)) / nB)) : M_PI_2;
    const double tBO = (nM > 0.0) ? std::acos(cl(dot(negN, sub(frontI, backI)) / nM)) : M_PI_2;
    const double tFI = (nM > 0.0) ? std::acos(cl(dot(nrmI, sub(backI, frontI)) / nM)) : M_PI_2;
    const double tFO = (nF > 0.0) ? std::acos(cl(dot(negN, sub(p->camPosition, frontI)) / nF)) : M_PI_2;
    gsl_vector_set(f, 0, p->n2 * std::sin(tBO) - p->n1 * std::sin(tBI));
    gsl_vector_set(f, 1, p->n3 * std::sin(tFO) - p->n2 * std::sin(tFI));
    gsl_vector_set(f, 2, dot(crs(sub(rpFront, frontI), sub(frontI, backI)), sub(p->camPosition, frontI)));
    gsl_vector_set(f, 3, dot(crs(sub(rpBack, backI), sub(backI, frontI)), sub(p->realPosition, backI)));
    return GSL_SUCCESS;
}

// line through (a,b) meeting the plane through three points
static P3 linePlane(P3 a, P3 b, const P3 pl[3]) {
    P3 n = crs(sub(pl[1], pl[0]), sub(pl[2], pl[0]));
    P3 d = sub(b, a);
    double den = dot(n, d);
    if (std::fabs(den) < 1e-300) return a;
    double t = dot(n, sub(pl[0], a)) / den;
    return mk(a.x + t * d.x, a.y + t * d.y, a.z + t * d.z);
}

struct Node { double sx, sy, wh, wv, ah, av; int refIter, refStatus; double refResid; };

static void refractNode(Node& nd, char axisH, char axisV, double planeFront, double planeBack,
                        double thickness, double n1, double n2, P3 cam) {
    RParams p;
    p.axisH = axisH; p.axisV = axisV;
    p.frontSurfaceCoord = planeFront;
    const double frontToBack = planeBack - p.frontSurfaceCoord;
    p.backSurfaceCoord = p.frontSurfaceCoord + std::copysign(thickness, frontToBack);
    p.camPosition = cam;
    p.n1 = n1; p.n2 = n2; p.n3 = n1;
    if (axisH == 'x') p.realPosition = (axisV == 'y') ? mk(nd.wh, nd.wv, planeBack)
                                                     : mk(nd.wh, planeBack, nd.wv);
    else if (axisH == 'y') p.realPosition = (axisV == 'x') ? mk(nd.wv, nd.wh, planeBack)
                                                          : mk(planeBack, nd.wh, nd.wv);
    else p.realPosition = (axisV == 'x') ? mk(nd.wv, planeBack, nd.wh)
                                         : mk(planeBack, nd.wv, nd.wh);
    P3 pf[3], pb[3], pq[3];
    if ((axisH == 'x' && axisV == 'y') || (axisH == 'y' && axisV == 'x')) {
        pf[0] = mk(0, 0, p.frontSurfaceCoord); pf[1] = mk(1, 0, p.frontSurfaceCoord); pf[2] = mk(0, 1, p.frontSurfaceCoord);
        pb[0] = mk(0, 0, p.backSurfaceCoord);  pb[1] = mk(1, 0, p.backSurfaceCoord);  pb[2] = mk(0, 1, p.backSurfaceCoord);
        pq[0] = mk(0, 0, p.realPosition.z);    pq[1] = mk(1, 0, p.realPosition.z);    pq[2] = mk(0, 1, p.realPosition.z);
    } else if ((axisH == 'x' && axisV == 'z') || (axisH == 'z' && axisV == 'x')) {
        pf[0] = mk(0, p.frontSurfaceCoord, 0); pf[1] = mk(1, p.frontSurfaceCoord, 0); pf[2] = mk(0, p.frontSurfaceCoord, 1);
        pb[0] = mk(0, p.backSurfaceCoord, 0);  pb[1] = mk(1, p.backSurfaceCoord, 0);  pb[2] = mk(0, p.backSurfaceCoord, 1);
        pq[0] = mk(0, p.realPosition.y, 0);    pq[1] = mk(1, p.realPosition.y, 0);    pq[2] = mk(0, p.realPosition.y, 1);
    } else {
        pf[0] = mk(p.frontSurfaceCoord, 0, 0); pf[1] = mk(p.frontSurfaceCoord, 1, 0); pf[2] = mk(p.frontSurfaceCoord, 0, 1);
        pb[0] = mk(p.backSurfaceCoord, 0, 0);  pb[1] = mk(p.backSurfaceCoord, 1, 0);  pb[2] = mk(p.backSurfaceCoord, 0, 1);
        pq[0] = mk(p.realPosition.x, 0, 0);    pq[1] = mk(p.realPosition.x, 1, 0);    pq[2] = mk(p.realPosition.x, 0, 1);
    }
    P3 initFront = linePlane(p.realPosition, p.camPosition, pf);
    P3 initBack = linePlane(p.realPosition, p.camPosition, pb);
    const gsl_multiroot_fsolver_type* T = gsl_multiroot_fsolver_hybrids;
    gsl_multiroot_fsolver* s = gsl_multiroot_fsolver_alloc(T, 4);
    gsl_multiroot_function f = {&refractionRootFunc_f, 4, &p};
    gsl_vector* x = gsl_vector_alloc(4);
    gsl_vector_set(x, 0, byName(p.axisH, initBack));
    gsl_vector_set(x, 1, byName(p.axisV, initBack));
    gsl_vector_set(x, 2, byName(p.axisH, initFront));
    gsl_vector_set(x, 3, byName(p.axisV, initFront));
    gsl_multiroot_fsolver_set(s, &f, x);
    int status = 0; size_t iter = 0;
    do {
        iter++;
        status = gsl_multiroot_fsolver_iterate(s);
        if (status) break;
        status = gsl_multiroot_test_residual(s->f, 1e-7);
    } while (status == GSL_CONTINUE && iter < 1000);
    nd.refIter = (int)iter; nd.refStatus = status;
    nd.refResid = 0.0;
    for (int i = 0; i < 4; i++) nd.refResid += std::fabs(gsl_vector_get(s->f, i));
    const double c1 = gsl_vector_get(s->x, 2), c2 = gsl_vector_get(s->x, 3);
    P3 sf;
    if (axisH == 'x') sf = (axisV == 'y') ? mk(c1, c2, p.frontSurfaceCoord) : mk(c1, p.frontSurfaceCoord, c2);
    else if (axisH == 'y') sf = (axisV == 'x') ? mk(c2, c1, p.frontSurfaceCoord) : mk(p.frontSurfaceCoord, c1, c2);
    else sf = (axisV == 'x') ? mk(c2, p.frontSurfaceCoord, c1) : mk(p.frontSurfaceCoord, c2, c1);
    gsl_multiroot_fsolver_free(s);
    gsl_vector_free(x);
    P3 ap = linePlane(cam, sf, pq);
    if (axisH == 'x') { nd.ah = ap.x; nd.av = (axisV == 'y') ? ap.y : ap.z; }
    else if (axisH == 'y') { nd.ah = ap.y; nd.av = (axisV == 'x') ? ap.x : ap.z; }
    else { nd.ah = ap.z; nd.av = (axisV == 'x') ? ap.x : ap.y; }
}

// ---------------------------------------------------------------- calculateMatrix (VSCalibration.mm:1179)
static void calcMatrix(std::vector<Node>& nodes, const Dist& d, bool useApparent,
                       double p_out[9], double pinv_out[9]) {
    const size_t n = nodes.size();
    double tsx = 0, tsy = 0, twh = 0, twv = 0;
    std::vector<double> ux(n), uy(n);
    for (size_t i = 0; i < n; i++) {
        undistort(nodes[i].sx, nodes[i].sy, d, &ux[i], &uy[i]);
        tsx += ux[i]; tsy += uy[i];
        twh += useApparent ? nodes[i].ah : nodes[i].wh;
        twv += useApparent ? nodes[i].av : nodes[i].wv;
    }
    const double scx = tsx / n, scy = tsy / n, wcx = twh / n, wcy = twv / n;
    double tsn = 0, twn = 0;
    for (size_t i = 0; i < n; i++) {
        tsn += std::hypot(ux[i] - scx, uy[i] - scy);
        const double h = (useApparent ? nodes[i].ah : nodes[i].wh) - wcx;
        const double v = (useApparent ? nodes[i].av : nodes[i].wv) - wcy;
        twn += std::hypot(h, v);
    }
    const double ssf = std::sqrt(2.0) / (tsn / n);
    const double wsf = std::sqrt(2.0) / (twn / n);
    const int rows = (int)n * 2;
    std::vector<double> A(rows * 9);
    for (size_t i = 0; i < n; i++) {
        const double X = (ux[i] - scx) * ssf;
        const double Z = (uy[i] - scy) * ssf;
        const double xx = ((useApparent ? nodes[i].ah : nodes[i].wh) - wcx) * wsf;
        const double zz = ((useApparent ? nodes[i].av : nodes[i].wv) - wcy) * wsf;
        double rA[9] = {X, Z, 1, 0, 0, 0, -xx * X, -xx * Z, -xx};
        double rB[9] = {0, 0, 0, X, Z, 1, -zz * X, -zz * Z, -zz};
        for (int j = 0; j < 9; j++) {
            A[(2 * i) * 9 + j] = rA[j];
            A[(2 * i + 1) * 9 + j] = rB[j];
        }
    }
    double p[9];
    leastSquaresHomogeneous(A, rows, p);
    double normM[9] = {ssf, 0, 0, 0, ssf, 0, -ssf * scx, -ssf * scy, 1};
    double denormM[9] = {1 / wsf, 0, 0, 0, 1 / wsf, 0, wcx, wcy, 1};
    double halfway[9];
    rmul3x3(p, normM, halfway);
    rmul3x3(denormM, halfway, p);
    std::memcpy(p_out, p, 9 * sizeof(double));
    std::memcpy(pinv_out, p, 9 * sizeof(double));
    invert3x3(pinv_out);
}

// ---------------------------------------------------------------- camera position
static P3 lift(double h, double v, double depth, char ah, char av) {
    if (ah == 'x') return (av == 'y') ? mk(h, v, depth) : mk(h, depth, v);
    if (ah == 'y') return (av == 'x') ? mk(v, h, depth) : mk(depth, h, v);
    return (av == 'x') ? mk(v, depth, h) : mk(depth, v, h);
}

// production stores p as a column-major 3x3; apply it the way projectScreenPoint does
static void applyMat(const double m[9], double x, double y, double* ox, double* oy) {
    const double w = m[2] * x + m[5] * y + m[8];
    *ox = (m[0] * x + m[3] * y + m[6]) / w;
    *oy = (m[1] * x + m[4] * y + m[7]) / w;
}

static P3 cpaLines(const std::vector<std::pair<P3, P3>>& lines, double* pld) {
    double Ivv[9] = {0, 0, 0, 0, 0, 0, 0, 0, 0};
    double Ivvp[3] = {0, 0, 0};
    for (auto& L : lines) {
        double dv[3] = {L.second.x - L.first.x, L.second.y - L.first.y, L.second.z - L.first.z};
        double dn = cblas_dnrm2(3, dv, 1);
        if (dn == 0) continue;
        double v[3] = {dv[0] / dn, dv[1] / dn, dv[2] / dn};
        double Am[9] = {1, 0, 0, 0, 1, 0, 0, 0, 1};
        cblas_dger(CblasColMajor, 3, 3, -1.0, v, 1, v, 1, Am, 3);
        for (int j = 0; j < 9; j++) Ivv[j] += Am[j];
        double pt[3] = {L.first.x, L.first.y, L.first.z};
        cblas_dgemv(CblasColMajor, CblasNoTrans, 3, 3, 1.0, Am, 3, pt, 1, 1.0, Ivvp, 1);
    }
    invert3x3(Ivv);
    double out[3];
    cblas_dgemv(CblasColMajor, CblasNoTrans, 3, 3, 1.0, Ivv, 3, Ivvp, 1, 0.0, out, 1);
    P3 C = mk(out[0], out[1], out[2]);
    double tot = 0;
    for (auto& L : lines) {
        double x1x0[3] = {L.first.x - C.x, L.first.y - C.y, L.first.z - C.z};
        double x2x1[3] = {L.second.x - L.first.x, L.second.y - L.first.y, L.second.z - L.first.z};
        double a = cblas_dnrm2(3, x1x0, 1), b = cblas_dnrm2(3, x2x1, 1);
        if (b == 0) continue;
        double dp = cblas_ddot(3, x1x0, 1, x2x1, 1);
        tot += std::sqrt(std::fmax(0.0, (a * a * b * b - dp * dp) / (b * b)));
    }
    *pld = tot / lines.size();
    return C;
}

int main() {
    char axisH, axisV;
    double planeFront, planeBack, thickness, n1, n2;
    int correctRefraction, nIterOverride;
    Dist d;
    if (std::scanf(" %c %c %lf %lf %lf %lf %lf %d %d", &axisH, &axisV, &planeFront, &planeBack,
                   &thickness, &n1, &n2, &correctRefraction, &nIterOverride) != 9) return 1;
    for (int i = 0; i < 13; i++) if (std::scanf(" %lf", &d.t[i]) != 1) return 1;
    if (std::scanf(" %lf", &d.eta) != 1) return 1;
    int nf, nb;
    if (std::scanf(" %d %d", &nf, &nb) != 2) return 1;
    std::vector<Node> front(nf), back(nb);
    for (int i = 0; i < nf; i++)
        std::scanf(" %lf %lf %lf %lf", &front[i].sx, &front[i].sy, &front[i].wh, &front[i].wv);
    for (int i = 0; i < nb; i++)
        std::scanf(" %lf %lf %lf %lf", &back[i].sx, &back[i].sy, &back[i].wh, &back[i].wv);

    // Front: never refraction corrected (VSCalibration.mm:1046)
    double s2f[9], f2s[9];
    calcMatrix(front, d, false, s2f, f2s);
    std::printf("FRONT");
    for (int i = 0; i < 9; i++) std::printf(" %.17g", s2f[i]);
    std::printf("\n");
    std::printf("FRONTINV");
    for (int i = 0; i < 9; i++) std::printf(" %.17g", f2s[i]);
    std::printf("\n");

    // Back: fixed-point loop, first iteration uncorrected (VSCalibration.mm:1052-1061)
    const int maxIter = (correctRefraction ? (nIterOverride > 0 ? nIterOverride : 4) : 1);
    double s2b[9], b2s[9];
    P3 cam = mk(0, 0, 0);
    double camPLD = 0.0;
    for (int it = 0; it < maxIter; it++) {
        const bool corr = (it > 0);
        if (corr)
            for (auto& nd : back)
                refractNode(nd, axisH, axisV, planeFront, planeBack, thickness, n1, n2, cam);
        calcMatrix(back, d, corr, s2b, b2s);
        // camera position from the back nodes' sightlines through the CURRENT matrices
        std::vector<std::pair<P3, P3>> lines;
        for (auto& nd : back) {
            double uxp, uyp, fh, fv, bh, bv;
            undistort(nd.sx, nd.sy, d, &uxp, &uyp);
            applyMat(s2f, uxp, uyp, &fh, &fv);
            applyMat(s2b, uxp, uyp, &bh, &bv);
            lines.push_back({lift(fh, fv, planeFront, axisH, axisV),
                             lift(bh, bv, planeBack, axisH, axisV)});
        }
        cam = cpaLines(lines, &camPLD);
        std::printf("ITER %d corrected=%d cam %.17g %.17g %.17g pld %.17g\n",
                    it, corr ? 1 : 0, cam.x, cam.y, cam.z, camPLD);
        std::printf("BACK%d", it);
        for (int i = 0; i < 9; i++) std::printf(" %.17g", s2b[i]);
        std::printf("\n");
    }
    std::printf("BACK");
    for (int i = 0; i < 9; i++) std::printf(" %.17g", s2b[i]);
    std::printf("\n");
    std::printf("BACKINV");
    for (int i = 0; i < 9; i++) std::printf(" %.17g", b2s[i]);
    std::printf("\n");
    std::printf("CAM %.17g %.17g %.17g %.17g\n", cam.x, cam.y, cam.z, camPLD);
    for (size_t i = 0; i < back.size(); i++)
        std::printf("APP %zu %.17g %.17g %d %d %.6g\n", i, back[i].ah, back[i].av,
                    back[i].refIter, back[i].refStatus, back[i].refResid);
    return 0;
}
