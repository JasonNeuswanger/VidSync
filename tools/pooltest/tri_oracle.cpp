// Production-faithful measurement-triangulation oracle for VidSync.
//
// Replays VSPoint.m's iterative triangulation EXACTLY: the same GSL minimizer
// (gsl_multimin_fminimizer_nmsimplex2), the same 3-parameter world-coordinate parameterization, the
// same initial step sizes, the same stopping test, the same iteration cap, and the same cost function
// transcribed verbatim. The Python harness owns all database access, undistortion and calibration, so
// this program receives only camera geometry and already-undistorted screen points.
//
// The point of this oracle is that the harness's scipy least_squares 'lm' solve is an OPTIMIZER
// SUBSTITUTION even though the objective is identical. A tighter tolerance does not prove the same
// solution, so both are run and compared.
//
// Build:
//   clang++ -O2 -std=c++17 tri_oracle.cpp -o tri_oracle \
//     -I/usr/local/include -L/usr/local/lib -lgsl -lgslcblas \
//     -framework Accelerate
//
// Traceability:
//   pointSolverCostFunction_f               VSPoint.m:29-53
//   linePlaneIntersect                      VSPoint.m:55-...
//   quadratCoords2Dfrom3D                   VSEventScreenPoint.h
//   project2DPoint                          UtilityFunctions
//   calculate3DCoords (minimizer setup)     VSPoint.m:147-215
//   calculate3DCoordsLinear (CPA seed)      VSPoint.m:292-...
//   intersectionOfNumber:of3DLines:         UtilityFunctions.mm:255
//
// stdin format:
//   ncam
//   for each camera:  camx camy camz  axisH axisV  frontd  f2s[9]  ux uy
//   seedx seedy seedz
// Repeated for as many points as requested:
//   first line is the number of points, then each point block as above.
//
// stdout: one line per point
//   TRI <i> <x> <y> <z> <cost> <iters> <status> <size>

#include <Accelerate/Accelerate.h>
// GSL ships its own cblas declarations which collide with Accelerate's. We use Accelerate's LAPACK
// (as production does) and only need GSL's minimizer, so suppress GSL's cblas header by pre-defining
// its include guard. Same trick oracle.cpp uses.
#define __GSL_CBLAS_H__
#include <gsl/gsl_multimin.h>
#include <gsl/gsl_vector.h>

#include <cmath>
#include <cstdio>
#include <vector>

struct P3 { double x, y, z; };
static P3 mk(double x, double y, double z) { P3 p; p.x = x; p.y = y; p.z = z; return p; }

struct Cam {
    P3 cam;
    char ah, av;
    double frontd;
    double f2s[9];
    double ux, uy;
};

struct Params { int ncam; std::vector<Cam>* c; };

// VSPoint.m: the front quadrat plane as three points, exactly as
// putPointsInFrontQuadratPlaneIntoArray builds it from the axis convention.
static void frontPlane(char ah, char av, double d, P3 out[3]) {
    if ((ah == 'x' && av == 'y') || (ah == 'y' && av == 'x')) {
        out[0] = mk(0, 0, d); out[1] = mk(1, 0, d); out[2] = mk(0, 1, d);
    } else if ((ah == 'x' && av == 'z') || (ah == 'z' && av == 'x')) {
        out[0] = mk(0, d, 0); out[1] = mk(1, d, 0); out[2] = mk(0, d, 1);
    } else {
        out[0] = mk(d, 0, 0); out[1] = mk(d, 1, 0); out[2] = mk(d, 0, 1);
    }
}

// VSPoint.m linePlaneIntersect: parametric form solved as a 3x3 linear system through LAPACK,
// the same call production makes.
static P3 linePlaneIntersect(P3 lf, P3 lb, const P3 pl[3]) {
    __CLPK_doublereal A[9], b[3];
    b[0] = lf.x - pl[0].x; b[1] = lf.y - pl[0].y; b[2] = lf.z - pl[0].z;
    // columns: (lf-lb), (pl1-pl0), (pl2-pl0)   [column major]
    A[0] = lf.x - lb.x; A[1] = lf.y - lb.y; A[2] = lf.z - lb.z;
    A[3] = pl[1].x - pl[0].x; A[4] = pl[1].y - pl[0].y; A[5] = pl[1].z - pl[0].z;
    A[6] = pl[2].x - pl[0].x; A[7] = pl[2].y - pl[0].y; A[8] = pl[2].z - pl[0].z;
    __CLPK_integer n = 3, nrhs = 1, lda = 3, ldb = 3, info = 0, ipiv[3];
    dgesv_(&n, &nrhs, A, &lda, ipiv, b, &ldb, &info);
    const double t = b[0];
    return mk(lf.x + t * (lb.x - lf.x), lf.y + t * (lb.y - lf.y), lf.z + t * (lb.z - lf.z));
}

static double byName(char a, P3 p) { return a == 'x' ? p.x : (a == 'y' ? p.y : p.z); }

static void project2D(const double* m, double x, double y, double* ox, double* oy) {
    const double w = m[6] * x + m[7] * y + m[8];
    *ox = (m[0] * x + m[1] * y + m[2]) / w;
    *oy = (m[3] * x + m[4] * y + m[5]) / w;
}

// VSPoint.m:29-53 pointSolverCostFunction_f, verbatim in structure.
static double cost_f(const gsl_vector* v, void* params) {
    Params* p = (Params*) params;
    P3 cand = mk(gsl_vector_get(v, 0), gsl_vector_get(v, 1), gsl_vector_get(v, 2));
    double cost = 0.0;
    for (int i = 0; i < p->ncam; i++) {
        const Cam& c = (*p->c)[i];
        P3 pl[3];
        frontPlane(c.ah, c.av, c.frontd, pl);
        P3 hit = linePlaneIntersect(cand, c.cam, pl);
        const double h = byName(c.ah, hit), vv = byName(c.av, hit);
        double sx, sy;
        project2D(c.f2s, h, vv, &sx, &sy);
        cost += std::pow(sx - c.ux, 2) + std::pow(sy - c.uy, 2);
    }
    return cost;
}

int main() {
    int npts = 0;
    if (std::scanf(" %d", &npts) != 1) return 1;
    for (int ip = 0; ip < npts; ip++) {
        int ncam = 0;
        if (std::scanf(" %d", &ncam) != 1) return 1;
        std::vector<Cam> cams(ncam);
        for (int i = 0; i < ncam; i++) {
            Cam& c = cams[i];
            char ah[8], av[8];
            if (std::scanf(" %lf %lf %lf %1s %1s %lf", &c.cam.x, &c.cam.y, &c.cam.z, ah, av,
                           &c.frontd) != 6) return 1;
            c.ah = ah[0]; c.av = av[0];
            for (int k = 0; k < 9; k++)
                if (std::scanf(" %lf", &c.f2s[k]) != 1) return 1;
            if (std::scanf(" %lf %lf", &c.ux, &c.uy) != 2) return 1;
        }
        double sx, sy, sz;
        if (std::scanf(" %lf %lf %lf", &sx, &sy, &sz) != 3) return 1;

        Params par; par.ncam = ncam; par.c = &cams;
        // VSPoint.m:184-196: nmsimplex2, 3 dimensions, all initial step sizes 1
        const gsl_multimin_fminimizer_type* T = gsl_multimin_fminimizer_nmsimplex2;
        gsl_multimin_fminimizer* s = gsl_multimin_fminimizer_alloc(T, 3);
        gsl_multimin_function f = {&cost_f, 3, &par};
        gsl_vector* x = gsl_vector_alloc(3);
        gsl_vector_set(x, 0, sx); gsl_vector_set(x, 1, sy); gsl_vector_set(x, 2, sz);
        gsl_vector* ss = gsl_vector_alloc(3);
        gsl_vector_set_all(ss, 1);
        gsl_multimin_fminimizer_set(s, &f, x, ss);
        size_t iter = 0;
        int status = 0;
        double size = 0.0;
        // VSPoint.m:199-206: size test at 1e-6, cap 500
        do {
            iter++;
            status = gsl_multimin_fminimizer_iterate(s);
            if (status) break;
            size = gsl_multimin_fminimizer_size(s);
            status = gsl_multimin_test_size(size, 1e-6);
        } while (status == GSL_CONTINUE && iter < 500);
        std::printf("TRI %d %.17g %.17g %.17g %.17g %zu %d %.6g\n", ip,
                    gsl_vector_get(s->x, 0), gsl_vector_get(s->x, 1), gsl_vector_get(s->x, 2),
                    s->fval, iter, status, size);
        gsl_vector_free(x); gsl_vector_free(ss); gsl_multimin_fminimizer_free(s);
    }
    return 0;
}
