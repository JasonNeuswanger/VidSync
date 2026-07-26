/*********************************************************************************                                                                       
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2021 Jason Neuswanger
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


#import "opencv2/opencv.hpp"
#import "opencv2/imgcodecs/macosx.h"	// this is not included via the opencv.hpp above
#import "gsl/gsl_multimin.h"

#import "VSCalibration.h"
#import "VSChessboardDetector.hpp"

#pragma mark
#pragma mark C Functions for Distortion Correction


double orthogonalRegressionLineCostFunction(NSPoint line[], const size_t numLinePoints)
// This is a cost function measuring the "straightness" of a line based on orthogonal distance regression.
// It returns the sum of squared perpendicular residuals from the best-fit line.  The formula for the
// best-fit angle comes from a 2005 post on the Ask Dr. Math forum, at
// http://mathforum.org/library/drmath/view/68362.html
{
	if (numLinePoints < 3) return 0.0;  // two points are collinear by definition, and one has no line to fit
	// Find the centroid of the line, which the best-fit line passes through
	NSPoint centroid = NSMakePoint(0.0,0.0);
	for (int i = 0; i < numLinePoints; i++) {
		centroid.x += line[i].x;
		centroid.y += line[i].y;
	}
	centroid.x = centroid.x / (double) numLinePoints;
	centroid.y = centroid.y / (double) numLinePoints;
	// Calculate the numerator and denominator for the ArcTan
	double mainsum = 0.0;
	double mainsqsum = 0.0;
	for (int i = 0; i < numLinePoints; i++) {
		mainsum += (line[i].x - centroid.x) * (line[i].y - centroid.y);
		mainsqsum += (pow((line[i].x - centroid.x),2.0) - pow((line[i].y - centroid.y),2.0));
	}
	if (mainsum == 0.0 && mainsqsum == 0.0) return 0.0;  // every point is at the centroid, so atan2 would be undefined
	// Calculate the best-fit angle and sum of squared perpendicular distances.  The residuals are measured
	// about the centroid rather than about the line's x-intercept.  Both describe the same line, but the
	// intercept form is xInt = centroid.x - centroid.y/tan(theta), which diverges as theta approaches zero:
	// for an exactly horizontal line tan(theta) is 0, xInt is infinite, and infinity times sin(0) made the
	// whole cost function NaN, poisoning the entire 13-parameter fit from one bad plumbline.
	const double theta = 0.5 * atan2(2.0 * mainsum, mainsqsum);
	const double sinTheta = sin(theta);
	const double cosTheta = cos(theta);
	double ssq = 0.0;
	for (int i = 0; i < numLinePoints; i++) {
		ssq += pow(-(line[i].x - centroid.x) * sinTheta + (line[i].y - centroid.y) * cosTheta,2.0);
	}
	return ssq;
}


double orthogonalRegressionTotalCostFunction(const gsl_vector *v, void *params){
	// This function measures the total "straightness" of all the lines.  Its arguments are formatted
	// in such a way that it can be set as the function to minimize using the multimin features of the GNU
	// scientific library.  It returns the plain sum of the squared residuals from an orthogonal regression on
	// all the lines, with no normalization -- see the note at the return statement for why the old division by
	// total line length was removed, and why nothing replaced it.
	// First, interpret the "parameters," which in this case means the pointer to the struct holding the plumbline data
	Plumblines* p = (Plumblines*) params;
	// Prepare the variables being adjusted to minimize the cost function -- the distortion parameters
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
	// Build an undistorted line data structure based on the values above and the pointer to the original data
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
	// Sum the orthogonal regression cost functions over all the lines
	double totalSSQRCost = 0.0;
	for (int i = 0; i < up.numLines; i++) {
		totalSSQRCost += orthogonalRegressionLineCostFunction(up.lines[i], up.lineLengths[i]);
	}
	// Free memory, then return
	for (int i = 0; i < up.numLines; i++) free(up.lines[i]);
	free(up.lines);
	free(up.lineLengths);
	// According to Sourceforge records, sometime between February 6 and April 4, 2012, I updated VidSync from the single-parameter division model being parameterized  the method of
	// Wang et al (2009; Journal of Mathematical Imaging and Vision 35(3):165-172) to the Brown-Conrady distortion model in use today. At some point I thought dividing by length was
	// necessary to avoid shrinking all the coordinates to the origin. First I divided each line by its length, then switched to dividing by the length of all lines to avoid weighting
	// some more than others. But this division by totalPixelLength doesn't actually seem to be necessary for the current model, which, being additive, does not offer any way to shrink
	// the coordinates to zero so we don't have to worry about preventing that unruly solution.
	return totalSSQRCost;// / totalLinePixelLength;
}

NSPoint redistortPoint(const NSPoint* pt, const double x0, const double y0, const double k1, const double k2, const double k3, const double k4, const double k5, const double k6, const double k7, const double p1, const double p2, const double p3, const double p4){
	// The new undistortion function doesn't have a closed-form inverse, so we instead use Newton's Method to solve numerically for the point
	// (x,y) that, when the undistortion function is applied to it, would give the input point.  That is, we're solving for the {x,y} roots of the
	// equation undistortPoint({x,y}, x0, y0, ...) == pt, or in other words undistortPoint({x,y}, x0, y0, ...) - pt == 0.
	const double xuc = pt->x - x0;
	const double yuc = pt->y - y0;
	const gsl_multiroot_fdfsolver_type *T;
	gsl_multiroot_fdfsolver *s;
	int status;
	size_t iter = 0;
	const size_t n = 2; // the number of variables (here there are 2, x and y)
	double params[13] = {xuc, yuc, k1, k2, k3, k4, k5, k6, k7, p1, p2, p3, p4};
	gsl_multiroot_function_fdf f = {&redistortionRootFunc_f, &redistortionRootFunc_df, &redistortionRootFunc_fdf, n, params};
	gsl_vector *x = gsl_vector_alloc(n);    // Initialize the solution starting at the input/undistorted point
	// OLD NOTES:
	// Setting the starting point of the root-finding algorithm to be half-way between the distortion center and the undistorted point.
	// Using the undistorted point itself worked fine for most applications, but on a highly distorted 8 mm fisheye all the algorithms ran into
	// numerical instabilities and wouldn't make progress toward the right solution. Likewise, starting at (0,0) didn't offer enough of a
	// gradient for the algorithms to progress in the right direction. But starting about half-way to the undistorted point seems to work well.
	// However, with a value of 2.0 the calibration frame grid overlays with the 8 mm fisheye had some slight problems near the corners with
	// both methods, moreso with the Hybridsj algorithm. It seems 2.5 was the sweet spot for this lens, which is the most extreme test likely.
	// Other lenses should be more permissive and these values should work well for them too.
	//
	// Two algorithms for the redistortion have typically worked okay. Both fail to converge on a good solution (residuals in the 2 to 400 range or so,
	// as opposed to something like 1e-10 after proper convergence) for similar points. It seems this only happens when calculating far-offscreen
	// hint line points with an extremely distorted fisheye lens, points that aren't relevant to any actual measurements or displays, although they might
	// result in display glitches at the extreme corners of the image sometimes. Even with ultrawide fisheyes, the problem only appeared for some videos
	// and not others. VidSync previously used the gnewton solver based on the appearance of convergence in these scenarios, but it turns out that was
	// illusory and it was hitting the iteration limit without improving the solution instead. The hybridsj solver as used below is faster and does not
	// get hung up on those failed, irrelevant points. So I switched from gnewton back to hybridsj to prevent the program from hanging.
	//
	// NEW NOTES (2022):
	// I realized there is no need to pick just one starting point -- why not try multiple if the first one doesn't work? This has greatly
	// improved the occasional problem I had with very wide lenses, in which hint lines had jagged spots because the redistortion to project
	// them on the screen wasn't converging in this algorithm. This should not have affected any actual measurements, but it was a disconcerting
	// visual glitch. I'm trying a mix of different starting points here. The first comes from a series expansion of the function of interest,
	// and the remainder are just arbitrary guesses. In combination they eliminate most of the jagged convergence failures in hint lines and
	// related redistorted overlays, but not all. Because this glitch doesn't affect measurements it isn't worth more effort at this time.

	
	const double x_guesses[15] = {xuc - 2*p2*xuc*yuc - 3*p1*pow(xuc,2) - p1*pow(yuc,2), 0.0, xuc/2.5, xuc/4.5, xuc/2.0, xuc/1.5, xuc/0.9, xuc, xuc*1.1, xuc*1.5, xuc*2.5, xuc/2.0, xuc*2.0, xuc*1.2, xuc/1.2};
	const double y_guesses[15] = {yuc - 2*p1*xuc*yuc - p2*pow(xuc,2) - 3*p2*pow(yuc,2), 0.0, yuc/2.5, yuc/4.5, yuc/2.0, yuc/1.5, yuc/0.9, yuc, yuc*1.1, yuc*1.5, yuc*2.5, yuc*2.0, yuc/2.0, yuc/1.2, yuc*1.2};

	T = gsl_multiroot_fdfsolver_hybridsj;
	s = gsl_multiroot_fdfsolver_alloc(T, n);
	bool failed;
	for (int i=0; i < 15; i++) {
		failed = false;
		iter = 0;
		gsl_vector_set(x, 0, x_guesses[i]);
		gsl_vector_set(x, 1, y_guesses[i]);
		gsl_multiroot_fdfsolver_set(s, &f, x);
		do {
			iter++;
			status = gsl_multiroot_fdfsolver_iterate(s);
			if (status) {
				failed = true;
				break;
			}
			status = gsl_multiroot_test_residual(s->f, 1e-7);
		} while (status == GSL_CONTINUE && iter < 1000);
		// Running out of iterations with the residual still above tolerance is just as much a failure of this
		// starting guess as an error return from the iterator. Only the latter used to be counted, so a guess
		// that stalled at the iteration cap was accepted as if it had converged, and the remaining guesses were
		// never tried.
		if (status != GSL_SUCCESS) failed = true;
		if (!failed) {
			break;
		}
	}
	// If every guess failed we fall through with whatever the last one reached, which is the best available
	// answer; the caller is drawing an overlay, not measuring, so an imprecise point beats no point at all.
	
//	double resid = sqrt(pow(gsl_vector_get(s->f, 0),2) + pow(gsl_vector_get(s->f, 1),2));
	
	NSPoint result = NSMakePoint(x0 + gsl_vector_get(s->x, 0), y0 + gsl_vector_get(s->x, 1));
 
	/*
	 // Other diagnostics
	 double r = sqrt(xuc*xuc+yuc*yuc);
	 NSDate *methodFinish = [NSDate date];
	 NSTimeInterval executionTime = [methodFinish timeIntervalSinceDate:methodStart];
	 NSLog(@"redistorted (%1.1f, %1.1f) at radius %1.1f to point (%1.1f, %1.1f) in %lu iterations (time: %f)",pt->x,pt->y,r,result.x,result.y,iter,executionTime);
	 */
	gsl_multiroot_fdfsolver_free(s);
	gsl_vector_free(x);
	return result;
}



NSPoint undistortPoint(const NSPoint* pt, const double x0, const double y0, const double k1, const double k2, const double k3, const double k4, const double k5, const double k6, const double k7, const double p1, const double p2, const double p3, const double p4){
	const double xd = pt->x - x0;
	const double yd = pt->y - y0;
	const double rs = xd*xd + yd*yd;
	const double xu = x0 + xd*(1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + k4*pow(rs,4) + k5*pow(rs,5) + k6*pow(rs,6) + k7*pow(rs,7)) + (p1*(rs + 2*xd*xd) + 2*p2*xd*yd)*(1 + p3*rs + p4*rs*rs);
	const double yu = y0 + yd*(1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + k4*pow(rs,4) + k5*pow(rs,5) + k6*pow(rs,6) + k7*pow(rs,7)) + (2*p1*xd*yd + p2*(rs + 2*yd*yd))*(1 + p3*rs + p4*rs*rs);
	return NSMakePoint(xu, yu);
}

void undistortionJacobian(const double xd, const double yd, const double k1, const double k2, const double k3, const double k4, const double k5, const double k6, const double k7, const double p1, const double p2, const double p3, const double p4, double J[4]){
	// The Jacobian of undistortPoint above, evaluated at an offset (xd, yd) from the distortion centre, returned
	// row-major as {d(xu)/d(xd), d(xu)/d(yd), d(yu)/d(xd), d(yu)/d(yd)}. Note it does not depend on the centre
	// itself, only on the offset from it, because the centre cancels out of the derivative.
	//
	// It is written in terms of the same s = xd^2 + yd^2 that undistortPoint uses, so that the two stay visibly
	// consistent. An earlier version was generated in Mathematica from a model whose radial series ran in powers
	// of r rather than powers of s = r^2, so every radial term was short by one factor of r. The result evaluated
	// to very nearly the identity matrix at realistic coefficients (about 1.0003 on the diagonal where the true
	// value is 1.27 at the corner of a wide-angle frame), which starved gsl's hybridsj of curvature and caused
	// the redistortion convergence failures described in redistortPoint above. It also divided by sqrt(s), so it
	// was singular at the distortion centre; this form has no division.
	//
	// Writing R for the radial series, T for the decentering scale series, and Gx/Gy for the decentering terms:
	//   xu = xd*R(s) + Gx*T(s)                    yu = yd*R(s) + Gy*T(s)
	//   d(xu)/d(xd) = R + 2*xd^2*R' + (dGx/dxd)*T + 2*xd*Gx*T'
	// and so on, using ds/dxd = 2*xd and ds/dyd = 2*yd.

	const double s = xd*xd + yd*yd;
	const double R  = 1 + k1*s + k2*pow(s,2) + k3*pow(s,3) + k4*pow(s,4) + k5*pow(s,5) + k6*pow(s,6) + k7*pow(s,7);
	const double Rp = k1 + 2*k2*s + 3*k3*pow(s,2) + 4*k4*pow(s,3) + 5*k5*pow(s,4) + 6*k6*pow(s,5) + 7*k7*pow(s,6);
	const double T  = 1 + p3*s + p4*s*s;
	const double Tp = p3 + 2*p4*s;
	const double Gx = p1*(3*xd*xd + yd*yd) + 2*p2*xd*yd;    // == p1*(s + 2*xd^2) + 2*p2*xd*yd
	const double Gy = 2*p1*xd*yd + p2*(xd*xd + 3*yd*yd);    // == 2*p1*xd*yd + p2*(s + 2*yd^2)

	J[0] = R + 2*xd*xd*Rp + (6*p1*xd + 2*p2*yd)*T + 2*xd*Gx*Tp;
	J[1] =     2*xd*yd*Rp + (2*p1*yd + 2*p2*xd)*T + 2*yd*Gx*Tp;
	J[2] =     2*xd*yd*Rp + (2*p1*yd + 2*p2*xd)*T + 2*xd*Gy*Tp;
	J[3] = R + 2*yd*yd*Rp + (2*p1*xd + 6*p2*yd)*T + 2*yd*Gy*Tp;
}

int redistortionRootFunc_f(const gsl_vector* x, void* params, gsl_vector* f) {
	const double* p = (double*) params;
	const double xd = gsl_vector_get(x, 0);
	const double yd = gsl_vector_get(x, 1);
	const double x0 = p[0];
	const double y0 = p[1];
	const double k1 = p[2];
	const double k2 = p[3];
	const double k3 = p[4];
	const double k4 = p[5];
	const double k5 = p[6];
	const double k6 = p[7];
	const double k7 = p[8];
	const double p1 = p[9];
	const double p2 = p[10];
	const double p3 = p[11];
	const double p4 = p[12];
	const double rs = xd*xd + yd*yd; // Multiplying like this is slightly faster than pow() for simple squaring/cubing
	const double xu = xd*(1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + k4*pow(rs,4) + k5*pow(rs,5) + k6*pow(rs,6) + k7*pow(rs,7)) + (p1*(rs + 2*xd*xd) + 2*p2*xd*yd)*(1 + p3*rs + p4*rs*rs);
	const double yu = yd*(1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + k4*pow(rs,4) + k5*pow(rs,5) + k6*pow(rs,6) + k7*pow(rs,7)) + (2*p1*xd*yd + p2*(rs + 2*yd*yd))*(1 + p3*rs + p4*rs*rs);
	gsl_vector_set(f, 0, xu - x0);
	gsl_vector_set(f, 1, yu - y0);
	return GSL_SUCCESS;
}

int redistortionRootFunc_df(const gsl_vector* x, void* params, gsl_matrix* J) {
	// The residual in redistortionRootFunc_f is undistortPoint's output minus a constant target, so its Jacobian
	// is just undistortPoint's. Note p[0] and p[1] hold that target, not the distortion centre, and the Jacobian
	// does not need the centre anyway.
	double* p = (double*) params;
	double j[4];
	undistortionJacobian(gsl_vector_get(x, 0), gsl_vector_get(x, 1), p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10], p[11], p[12], j);
	gsl_matrix_set(J, 0, 0, j[0]);
	gsl_matrix_set(J, 0, 1, j[1]);
	gsl_matrix_set(J, 1, 0, j[2]);
	gsl_matrix_set(J, 1, 1, j[3]);
	return GSL_SUCCESS;
}


int redistortionRootFunc_fdf(const gsl_vector* x, void* params, gsl_vector* f, gsl_matrix* J)
{
	redistortionRootFunc_f(x, params, f);
	redistortionRootFunc_df(x, params, J);
	return GSL_SUCCESS;
}

#pragma mark
#pragma mark C Functions for Refraction Correction

typedef struct
{
	char axisHorizontal;
	char axisVertical;
	double frontSurfaceCoord;
	double backSurfaceCoord;
	VSPoint3D realPosition;
	VSPoint3D camPosition;
	double n1;  // index of refraction of the medium between the quadrat planes (typically water)
	double n2;  // index of refraction of the front quadrat plane material (such as glass)
	double n3;  // index of refraction of the material between the front quadrat plane and the camera (water or air)
} RefractionSolverParams;

void fill3Vector(gsl_vector* v, double x, double y, double z) {
	gsl_vector_set(v,0,x);
	gsl_vector_set(v,1,y);
	gsl_vector_set(v,2,z);
}

VSPoint3D VSMakePoint3D(double x, double y, double z) {
	VSPoint3D pt;
	pt.x = x;
	pt.y = y;
	pt.z = z;
	return pt;
}

VSPoint3D VSSubtractPoint3D(VSPoint3D p1, VSPoint3D p2) {
	VSPoint3D result;
	result.x = p1.x - p2.x;
	result.y = p1.y - p2.y;
	result.z = p1.z - p2.z;
	return result;
}

double VSPoint3DNorm(VSPoint3D p) {
	return sqrt(p.x*p.x + p.y*p.y + p.z*p.z);
}

double VSPoint3DDot(VSPoint3D p1, VSPoint3D p2) {
	return p1.x*p2.x + p1.y*p2.y + p1.z*p2.z;
}

VSPoint3D VSPoint3DCross(VSPoint3D p1, VSPoint3D p2) {  // cross product of two Point3Ds
	return VSMakePoint3D(p1.y*p2.z - p1.z*p2.y, p1.z*p2.x - p1.x*p2.z, p1.x*p2.y - p1.y*p2.x);
}

double VSPoint3DElementByName(char name, VSPoint3D point) {
	if (name == 'x') {
		return point.x;
	} else if (name == 'y') {
		return point.y;
	} else {
		return point.z;
	}
}

// "back" is surface 1, "front" is surface 2
// here "back" refers to the back side of the interface, and front refers to the front of the interface (NOT the front and back quadrat planes!)

int refractionRootFunc_f(const gsl_vector* x, void* params, gsl_vector* f) 
{
	const RefractionSolverParams* p = (RefractionSolverParams*) params;
	const double backSolveCoord1 = gsl_vector_get(x,0);
	const double backSolveCoord2 = gsl_vector_get(x,1);
	const double frontSolveCoord1 = gsl_vector_get(x,2);
	const double frontSolveCoord2 = gsl_vector_get(x,3);
	
	VSPoint3D backIntersection, frontIntersection, interfaceNormal, negativeInterfaceNormal, refractionPlaneBackPoint, refractionPlaneFrontPoint;
	
	if (p->axisHorizontal == 'x') {
		if (p->axisVertical == 'y') {
			interfaceNormal = VSMakePoint3D(0.0, 0.0, 1.0);
			backIntersection = VSMakePoint3D(backSolveCoord1, backSolveCoord2, p->backSurfaceCoord);
			frontIntersection = VSMakePoint3D(frontSolveCoord1, frontSolveCoord2, p->frontSurfaceCoord);
			refractionPlaneBackPoint = VSMakePoint3D(backSolveCoord1, backSolveCoord2, p->realPosition.z);
			refractionPlaneFrontPoint = VSMakePoint3D(frontSolveCoord1, frontSolveCoord2, p->camPosition.z);
		} else {    // axisVertical == z
			interfaceNormal = VSMakePoint3D(0.0, 1.0, 0.0);
			backIntersection = VSMakePoint3D(backSolveCoord1, p->backSurfaceCoord, backSolveCoord2);
			frontIntersection = VSMakePoint3D(frontSolveCoord1, p->frontSurfaceCoord, frontSolveCoord2);
			refractionPlaneBackPoint = VSMakePoint3D(backSolveCoord1, p->realPosition.y, backSolveCoord2);
			refractionPlaneFrontPoint = VSMakePoint3D(frontSolveCoord1, p->camPosition.y, frontSolveCoord2);
		}
	} else if (p->axisHorizontal == 'y') {
		if (p->axisVertical == 'x') {
			interfaceNormal = VSMakePoint3D(0.0, 0.0, 1.0);
			backIntersection = VSMakePoint3D(backSolveCoord2, backSolveCoord1, p->backSurfaceCoord);
			frontIntersection = VSMakePoint3D(frontSolveCoord2, frontSolveCoord1, p->frontSurfaceCoord);
			refractionPlaneBackPoint = VSMakePoint3D(backSolveCoord2, backSolveCoord1, p->realPosition.z);
			refractionPlaneFrontPoint = VSMakePoint3D(frontSolveCoord2, frontSolveCoord1, p->camPosition.z);
		} else {    // axisVertical == z
			interfaceNormal = VSMakePoint3D(1.0, 0.0, 0.0);
			backIntersection = VSMakePoint3D(p->backSurfaceCoord, backSolveCoord1, backSolveCoord2);
			frontIntersection = VSMakePoint3D(p->frontSurfaceCoord, frontSolveCoord1, frontSolveCoord2);
			refractionPlaneBackPoint = VSMakePoint3D(p->realPosition.x, backSolveCoord1, backSolveCoord2);
			refractionPlaneFrontPoint = VSMakePoint3D(p->camPosition.x, frontSolveCoord1, frontSolveCoord2);
		}
	} else {    // axisHorizontal == z
		if (p->axisVertical == 'x') {
			interfaceNormal = VSMakePoint3D(0.0, 1.0, 0.0);
			backIntersection = VSMakePoint3D(backSolveCoord2, p->backSurfaceCoord, backSolveCoord1);
			frontIntersection = VSMakePoint3D(frontSolveCoord2, p->frontSurfaceCoord, frontSolveCoord1);
			refractionPlaneBackPoint = VSMakePoint3D(backSolveCoord2, p->realPosition.y, backSolveCoord1);
			refractionPlaneFrontPoint = VSMakePoint3D(frontSolveCoord2, p->camPosition.y, frontSolveCoord1);
		} else {    // axisVertical == y
			interfaceNormal = VSMakePoint3D(1.0, 0.0, 0.0);
			backIntersection = VSMakePoint3D(p->backSurfaceCoord, backSolveCoord2, backSolveCoord1);
			frontIntersection = VSMakePoint3D(p->frontSurfaceCoord, frontSolveCoord2, frontSolveCoord1);
			refractionPlaneBackPoint = VSMakePoint3D(p->realPosition.x, backSolveCoord2, backSolveCoord1);
			refractionPlaneFrontPoint = VSMakePoint3D(p->camPosition.x, frontSolveCoord2, frontSolveCoord1);
		}
	}
	
	negativeInterfaceNormal = VSMakePoint3D(interfaceNormal.x * -1.0, interfaceNormal.y * -1.0, interfaceNormal.z * -1.0);
	
	double normBack  = VSPoint3DNorm(VSSubtractPoint3D(p->realPosition, backIntersection));
	double normMid   = VSPoint3DNorm(VSSubtractPoint3D(frontIntersection, backIntersection));
	double normFront = VSPoint3DNorm(VSSubtractPoint3D(p->camPosition, frontIntersection));
	const double thetaBackIn   = (normBack  > 0.0) ? acos(fmax(-1.0, fmin(1.0, VSPoint3DDot(interfaceNormal,         VSSubtractPoint3D(p->realPosition,    backIntersection))  / normBack ))) : M_PI_2;
	const double thetaBackOut  = (normMid   > 0.0) ? acos(fmax(-1.0, fmin(1.0, VSPoint3DDot(negativeInterfaceNormal, VSSubtractPoint3D(frontIntersection,   backIntersection))  / normMid  ))) : M_PI_2;
	const double thetaFrontIn  = (normMid   > 0.0) ? acos(fmax(-1.0, fmin(1.0, VSPoint3DDot(interfaceNormal,         VSSubtractPoint3D(backIntersection,    frontIntersection)) / normMid  ))) : M_PI_2;
	const double thetaFrontOut = (normFront > 0.0) ? acos(fmax(-1.0, fmin(1.0, VSPoint3DDot(negativeInterfaceNormal, VSSubtractPoint3D(p->camPosition,       frontIntersection)) / normFront))) : M_PI_2;
	
	double rootFunction1, rootFunction2, rootFunction3, rootFunction4;
	rootFunction1 = p->n2 * sin(thetaBackOut) - p->n1 * sin(thetaBackIn);       // Snell's law for the first intersection
	rootFunction2 = p->n3 * sin(thetaFrontOut) - p->n2 * sin(thetaFrontIn);     // Snell's law for the second intersection
	rootFunction3 = VSPoint3DDot(VSPoint3DCross(VSSubtractPoint3D(refractionPlaneFrontPoint,frontIntersection),VSSubtractPoint3D(frontIntersection,backIntersection)),VSSubtractPoint3D(p->camPosition,frontIntersection));
	rootFunction4 = VSPoint3DDot(VSPoint3DCross(VSSubtractPoint3D(refractionPlaneBackPoint,backIntersection),VSSubtractPoint3D(backIntersection,frontIntersection)),VSSubtractPoint3D(p->realPosition,backIntersection));
	
	gsl_vector_set(f,0,rootFunction1);
	gsl_vector_set(f,1,rootFunction2);
	gsl_vector_set(f,2,rootFunction3);
	gsl_vector_set(f,3,rootFunction4);
	
	return GSL_SUCCESS;
}

#pragma mark
#pragma mark VSCalibratin Class

@implementation VSCalibration

@dynamic videoClip;

@dynamic axisHorizontal;
@dynamic axisVertical;
@dynamic planeCoordFront;
@dynamic planeCoordBack;

@dynamic quadratNodesFront;
@dynamic quadratNodesBack;
@dynamic pointsFront;
@dynamic pointsBack;
@dynamic distortionLines;

@synthesize autodetectedPoints;
@synthesize holdOutDiagonals;

@dynamic matrixQuadratFrontToScreen;
@dynamic matrixQuadratBackToScreen;
@dynamic matrixScreenToQuadratFront;
@dynamic matrixScreenToQuadratBack;

@dynamic cameraX;
@dynamic cameraY;
@dynamic cameraZ;
@dynamic cameraMeanPLD;

@dynamic residualFrontLeastSquares;
@dynamic residualBackLeastSquares;
@dynamic residualFrontPixel;
@dynamic residualBackPixel;
@dynamic residualFrontWorld;
@dynamic residualBackWorld;

@dynamic distortionCenterX;
@dynamic distortionCenterY;
@dynamic distortionK1;
@dynamic distortionK2;
@dynamic distortionK3;
@dynamic distortionK4;
@dynamic distortionK5;
@dynamic distortionK6;
@dynamic distortionK7;
@dynamic distortionP1;
@dynamic distortionP2;
@dynamic distortionP3;
@dynamic distortionP4;
@dynamic distortionReductionAchieved;
@dynamic distortionRemainingPerPoint;

@dynamic shouldCorrectRefraction;
@dynamic frontQuadratSurfaceThickness;
@dynamic frontQuadratSurfaceRefractiveIndex;
@dynamic mediumRefractiveIndex;

#pragma mark
#pragma mark User Input Handling


+ (NSSet *) keyPathsForValuesAffectingAxisFrontToBack
{
	return [NSSet setWithObjects:@"axisHorizontal", @"axisVertical", nil];
}

- (NSString *) axisFrontToBack
{	
	if ([self.axisHorizontal isEqualToString:@"x"]) {
		if ([self.axisVertical isEqualToString:@"y"]) {
			return @"z";
		} else {
			return @"y";
		}
	} else if ([self.axisHorizontal isEqualToString:@"y"]) {
		if ([self.axisVertical isEqualToString:@"x"]) {
			return @"z";
		} else {
			return @"x";
		}
	} else {
		if ([self.axisVertical isEqualToString:@"x"]) {
			return @"y";
		} else {
			return @"x";
		}
	}
}

- (void) resetFrameAndBeginCalibration
{
	[self createPointsFromQuadratDescription:@"Both"];
}

- (void) resetFrontFrameOnly
{
	[self createPointsFromQuadratDescription:@"Front"];
}

- (void) resetBackFrameOnly
{
	[self createPointsFromQuadratDescription:@"Back"];
}

- (void) createPointsFromQuadratDescription:(NSString *)whichSurface
{
	bool doFront, doBack;
	if ([whichSurface isEqualToString:@"Front"]) {
		doFront = YES;
		doBack = NO;
	} else if ([whichSurface isEqualToString:@"Back"]) {
		doFront = NO;
		doBack = YES;
	} else {
		doFront = YES;
		doBack = YES;
	}
	NSScanner *lineScanner;
	NSCharacterSet *lineBreak = [NSCharacterSet newlineCharacterSet];
	NSString *currentLine;
	VSCalibrationPoint *newPoint;
	if (doFront) {
		int frontIndex = 1;
		self.pointsFront = nil;
		NSScanner *frontScanner = [NSScanner scannerWithString:[self.quadratNodesFront string]];
		while ([frontScanner scanUpToCharactersFromSet:lineBreak intoString:&currentLine]){
			lineScanner = [NSScanner scannerWithString:currentLine];
			[lineScanner setCharactersToBeSkipped:[NSCharacterSet characterSetWithCharactersInString:@", "]];
			float hCoord,vCoord;
			if ([lineScanner scanFloat:&hCoord] && [lineScanner scanFloat:&vCoord]) {
				newPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSCalibrationPointFront" inManagedObjectContext:[self managedObjectContext]];
				newPoint.calibration = self;
				newPoint.index = [NSNumber numberWithInt:frontIndex];
				newPoint.worldHcoord = [NSNumber numberWithFloat:hCoord];
				newPoint.worldVcoord = [NSNumber numberWithFloat:vCoord];
				frontIndex += 1;
			}
		}
	}
	if (doBack) {
		int backIndex = 1;
		self.pointsBack = nil;
		NSScanner *backScanner = [NSScanner scannerWithString:[self.quadratNodesBack string]];
		while ([backScanner scanUpToCharactersFromSet:lineBreak intoString:&currentLine]){
			lineScanner = [NSScanner scannerWithString:currentLine];
			[lineScanner setCharactersToBeSkipped:[NSCharacterSet characterSetWithCharactersInString:@", "]];
			float hCoord,vCoord;
			if ([lineScanner scanFloat:&hCoord] && [lineScanner scanFloat:&vCoord]) {
				newPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSCalibrationPointBack" inManagedObjectContext:[self managedObjectContext]];
				newPoint.calibration = self;
				newPoint.index = [NSNumber numberWithInt:backIndex];
				newPoint.worldHcoord = [NSNumber numberWithFloat:hCoord];
				newPoint.worldVcoord = [NSNumber numberWithFloat:vCoord];
				backIndex += 1;
			}
		}
	}
	[self.videoClip.windowController refreshOverlay];
}

- (void) processClickOnSurface:(NSString *)whichSurface withCoords:(NSPoint)videoCoords
{
	VSCalibrationPoint *pointToChange;
	NSArrayController *arrayController = nil;
	if ([whichSurface isEqualToString:@"Front Frame Surface"]) {
		arrayController = self.videoClip.project.document.calibScreenPtFrontArrayController;
	} else if ([whichSurface isEqualToString:@"Back Surface"]) {
		arrayController = self.videoClip.project.document.calibScreenPtBackArrayController;
	}
	NSUInteger numberOfPoints = [[arrayController arrangedObjects] count];
	if (numberOfPoints == 0) {
		[UtilityFunctions InformUser:[NSString stringWithFormat:@"Your click was ignored because you haven't set the world coordinates for any calibration points on the %@ yet. Please set them and try again.",whichSurface] withTitle:@"Click Ignored"];
	} else {
		if (numberOfPoints == 0) return;
		pointToChange = nil;
		NSUInteger pointIndex = 0;
		VSCalibrationPoint *testPoint;
		while (pointToChange == nil && pointIndex < numberOfPoints) {
			testPoint = [[arrayController arrangedObjects] objectAtIndex:pointIndex];
			if ([testPoint.screenX intValue] == 0 && [testPoint.screenY intValue] == 0) {
				pointToChange = testPoint;
			}
			pointIndex += 1;
		}
		if (pointToChange != nil) {
			pointToChange.screenX = [NSNumber numberWithFloat:videoCoords.x];
			pointToChange.screenY = [NSNumber numberWithFloat:videoCoords.y];
			[arrayController setSelectedObjects:[NSArray arrayWithObject:pointToChange]];
		}
		[self.videoClip.windowController refreshOverlay];
	}
}

#pragma mark
#pragma mark Import/Export Data

- (void) saveQuadratDescriptionToFile
{
	NSSavePanel *savePanel = [NSSavePanel savePanel];
	NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"mainFileSaveDirectory"];
	BOOL directoryExists;
	if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) [savePanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
	[savePanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncQuadrat",nil]];
	if ([savePanel runModal]) {
		// Built explicitly rather than with arrayWithObjects:, which stops at the first nil. Once
		// shouldCorrectRefraction can be nil to mean "the user has not decided yet", that would silently
		// truncate the file and drop the thickness and refractive indices with it. Exporting only the first
		// four entries in that case is deliberate: an unanswered frame has no refraction settings to record,
		// and every reader here already treats a short file as one without them.
		NSMutableArray *quadratDescription = [NSMutableArray arrayWithObjects:
											  ([self.quadratNodesFront string] != nil) ? [self.quadratNodesFront string] : @"",
											  ([self.quadratNodesBack string] != nil) ? [self.quadratNodesBack string] : @"",
											  (self.planeCoordFront != nil) ? self.planeCoordFront : [NSNumber numberWithInt:0],
											  (self.planeCoordBack != nil) ? self.planeCoordBack : [NSNumber numberWithInt:0],
											  nil];
		if (self.shouldCorrectRefraction != nil) {
			[quadratDescription addObject:self.shouldCorrectRefraction];
			[quadratDescription addObject:(self.frontQuadratSurfaceThickness != nil) ? self.frontQuadratSurfaceThickness : [NSNumber numberWithDouble:0.0]];
			[quadratDescription addObject:(self.frontQuadratSurfaceRefractiveIndex != nil) ? self.frontQuadratSurfaceRefractiveIndex : [NSNumber numberWithDouble:1.0]];
			[quadratDescription addObject:(self.mediumRefractiveIndex != nil) ? self.mediumRefractiveIndex : [NSNumber numberWithDouble:1.0]];
		}
		[quadratDescription writeToFile:[[savePanel URL] path] atomically:NO];
	}
}

- (void) loadQuadratDescriptionFromFile
{
	NSString *filePath;
	NSOpenPanel *openPanel = [NSOpenPanel openPanel];
	NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"mainFileSaveDirectory"];
	BOOL directoryExists;
	if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) [openPanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
	[openPanel setCanChooseFiles:YES];
	[openPanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncQuadrat",nil]];
	[openPanel setCanChooseDirectories:NO];
	[openPanel setAllowsMultipleSelection:NO];
	if ([openPanel runModal]) {
		filePath = [[[openPanel URLs] objectAtIndex:0] path];
		NSArray *quadratDescription = [[NSArray alloc] initWithContentsOfFile:filePath];
		if (![quadratDescription isKindOfClass:[NSArray class]] || [quadratDescription count] < 4) {
			[UtilityFunctions InformUser:@"The quadrat file could not be read or is from an unsupported version." withTitle:@"Invalid File"];
			return;
		}
		self.quadratNodesFront = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:0]];
		self.quadratNodesBack = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:1]];
		self.planeCoordFront = [quadratDescription objectAtIndex:2];
		self.planeCoordBack = [quadratDescription objectAtIndex:3];
		if ([quadratDescription count] > 7) {
			self.shouldCorrectRefraction = [quadratDescription objectAtIndex:4];
			self.frontQuadratSurfaceThickness = [quadratDescription objectAtIndex:5];
			self.frontQuadratSurfaceRefractiveIndex = [quadratDescription objectAtIndex:6];
			self.mediumRefractiveIndex = [quadratDescription objectAtIndex:7];
		}
	}
}

- (BOOL) hasQuadratNodeCoordinates
{
	NSCharacterSet *blank = [NSCharacterSet whitespaceAndNewlineCharacterSet];
	return ([[[self.quadratNodesFront string] stringByTrimmingCharactersInSet:blank] length] > 0
		 || [[[self.quadratNodesBack string] stringByTrimmingCharactersInSet:blank] length] > 0);
}

- (void) loadQuadratDescriptionExample
{
	// Loading the example replaces both node coordinate lists wholesale, and it is a single click right next to
	// the import and export buttons, so it is easy to hit by mistake after typing in a frame's coordinates.
	if ([self hasQuadratNodeCoordinates]) {
		BOOL shouldOverwrite = [UtilityFunctions ConfirmAction:@"Loading the example will replace the calibration frame node coordinates you have already entered, for both the front and back surfaces. This cannot be undone." withTitle:@"Overwrite your frame coordinates with the example?"];
		if (!shouldOverwrite) return;
	}
	NSString *filePath = [[NSBundle mainBundle] pathForResource:@"Example Quadrat" ofType:@"VidSyncQuadrat"];
	NSArray *quadratDescription = [[NSArray alloc] initWithContentsOfFile:filePath];
	if (![quadratDescription isKindOfClass:[NSArray class]] || [quadratDescription count] < 4) {
		[UtilityFunctions InformUser:@"The bundled example calibration frame description could not be read." withTitle:@"Example Unavailable"];
		return;
	}
	self.quadratNodesFront = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:0]];
	self.quadratNodesBack = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:1]];
	self.planeCoordFront = [quadratDescription objectAtIndex:2];
	self.planeCoordBack = [quadratDescription objectAtIndex:3];
	if ([quadratDescription count] > 7) {
		self.shouldCorrectRefraction = [quadratDescription objectAtIndex:4];
		self.frontQuadratSurfaceThickness = [quadratDescription objectAtIndex:5];
		self.frontQuadratSurfaceRefractiveIndex = [quadratDescription objectAtIndex:6];
		self.mediumRefractiveIndex = [quadratDescription objectAtIndex:7];
	}
}

- (IBAction) export3DCalibrationToFile:(id)sender 
{
	NSSavePanel *savePanel = [NSSavePanel savePanel];
	NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"mainFileSaveDirectory"];
	BOOL directoryExists;
	if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) [savePanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
	[savePanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncCalibration",nil]];
	if ([savePanel runModal]) {
		NSArray *pointsFrontArray = [NSArray array];
		NSArray *pointsBackArray = [NSArray array];
		for (VSCalibrationPoint *point in self.pointsFront) {
			pointsFrontArray = [pointsFrontArray arrayByAddingObject:[NSArray arrayWithObjects:point.screenX,point.screenY,point.worldHcoord,point.worldVcoord,point.index,nil]];
		}
		for (VSCalibrationPoint *point in self.pointsBack) {
			pointsBackArray = [pointsBackArray arrayByAddingObject:[NSArray arrayWithObjects:point.screenX,point.screenY,point.worldHcoord,point.worldVcoord,point.index,nil]];
		}
		NSNumber *isMasterClip = [NSNumber numberWithBool:[self.videoClip.isMasterClipOf isEqualTo:self.videoClip.project]];	// YES if this is the master clip's calibration, NO otherwise
		
		// Built explicitly rather than with arrayWithObjects:, which stops at the first nil and would drop
		// everything after it. That is why the importer's length checks exist, and why the log line below
		// blames "some object in the list was null". Each entry now has a defined fallback, and the refraction
		// block is appended only when the user has answered the refraction question, matching the quadrat
		// description format and the importer's existing "more than 13 entries" test.
		NSMutableArray *fullCalibration = [NSMutableArray arrayWithObjects:
							   ([self.quadratNodesFront string] != nil) ? [self.quadratNodesFront string] : @"",
							   ([self.quadratNodesBack string] != nil) ? [self.quadratNodesBack string] : @"",
							   (self.planeCoordFront != nil) ? self.planeCoordFront : [NSNumber numberWithInt:0],
							   (self.planeCoordBack != nil) ? self.planeCoordBack : [NSNumber numberWithInt:0],
							   (self.axisHorizontal != nil) ? self.axisHorizontal : @"x",
							   (self.axisVertical != nil) ? self.axisVertical : @"z",
							   pointsFrontArray,
							   pointsBackArray,
							   isMasterClip,
							   (self.videoClip.project.calibrationTimecode != nil) ? self.videoClip.project.calibrationTimecode : @"",
							   nil
							   ];
		if (self.shouldCorrectRefraction != nil) {
			[fullCalibration addObject:self.shouldCorrectRefraction];
			[fullCalibration addObject:(self.frontQuadratSurfaceThickness != nil) ? self.frontQuadratSurfaceThickness : [NSNumber numberWithDouble:0.0]];
			[fullCalibration addObject:(self.frontQuadratSurfaceRefractiveIndex != nil) ? self.frontQuadratSurfaceRefractiveIndex : [NSNumber numberWithDouble:1.0]];
			[fullCalibration addObject:(self.mediumRefractiveIndex != nil) ? self.mediumRefractiveIndex : [NSNumber numberWithDouble:1.0]];
		}
		if (![fullCalibration writeToFile:[[savePanel URL] path] atomically:YES]) NSLog(@"Error writing calibration file.");
	}
}

- (IBAction) import3DCalibrationFromFile:(id)sender
{
	NSString *filePath;
	NSOpenPanel *openPanel = [NSOpenPanel openPanel];
	NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"mainFileSaveDirectory"];
	BOOL directoryExists;
	if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) [openPanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
	[openPanel setCanChooseFiles:YES];
	[openPanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncCalibration",nil]];
	[openPanel setCanChooseDirectories:NO];
	[openPanel setAllowsMultipleSelection:NO];
	if ([openPanel runModal]) {
		filePath = [[[openPanel URLs] objectAtIndex:0] path];
		NSArray *fullCalibration = [[NSArray alloc] initWithContentsOfFile:filePath];
		// NSLog(@"fullCalibration has %lu entries, which are %@",(unsigned long)[fullCalibration count],fullCalibration);
		if (![fullCalibration isKindOfClass:[NSArray class]] || [fullCalibration count] < 10) {
			[UtilityFunctions InformUser:@"The calibration file could not be read or is from an unsupported version." withTitle:@"Invalid File"];
			return;
		}
		self.quadratNodesFront = [[NSAttributedString alloc] initWithString:[fullCalibration objectAtIndex:0]];
		self.quadratNodesBack = [[NSAttributedString alloc] initWithString:[fullCalibration objectAtIndex:1]];
		self.planeCoordFront = [fullCalibration objectAtIndex:2];
		self.planeCoordBack = [fullCalibration objectAtIndex:3];
		self.axisHorizontal = [fullCalibration objectAtIndex:4];
		self.axisVertical = [fullCalibration objectAtIndex:5];
		if ([fullCalibration count] > 13) {
			self.shouldCorrectRefraction = [fullCalibration objectAtIndex:10];
			self.frontQuadratSurfaceThickness = [fullCalibration objectAtIndex:11];
			self.frontQuadratSurfaceRefractiveIndex = [fullCalibration objectAtIndex:12];
			self.mediumRefractiveIndex = [fullCalibration objectAtIndex:13];
		}
		VSCalibrationPoint *newPoint;
		for (VSCalibrationPoint *pointToDelete in self.pointsFront) [self.managedObjectContext deleteObject:pointToDelete];		// remove the old points if there are any
		for (NSArray *pointArray in [fullCalibration objectAtIndex:6]) {	// Loop through the array for the front calibration points, and create them
			if (![pointArray isKindOfClass:[NSArray class]] || [pointArray count] < 5) continue;
			newPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSCalibrationPointFront" inManagedObjectContext:[self managedObjectContext]];
			newPoint.calibration = self;
			newPoint.screenX = [pointArray objectAtIndex:0];
			newPoint.screenY = [pointArray objectAtIndex:1];
			newPoint.worldHcoord = [pointArray objectAtIndex:2];
			newPoint.worldVcoord = [pointArray objectAtIndex:3];
			newPoint.index = [pointArray objectAtIndex:4];
		}
		for (VSCalibrationPoint *pointToDelete in self.pointsBack) [self.managedObjectContext deleteObject:pointToDelete];		// remove the old points if there are any
		for (NSArray *pointArray in [fullCalibration objectAtIndex:7]) {	// Loop through the array for the back calibration points, and create them
			if (![pointArray isKindOfClass:[NSArray class]] || [pointArray count] < 5) continue;
			newPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSCalibrationPointBack" inManagedObjectContext:[self managedObjectContext]];
			newPoint.calibration = self;
			newPoint.screenX = [pointArray objectAtIndex:0];
			newPoint.screenY = [pointArray objectAtIndex:1];
			newPoint.worldHcoord = [pointArray objectAtIndex:2];
			newPoint.worldVcoord = [pointArray objectAtIndex:3];
			newPoint.index = [pointArray objectAtIndex:4];
		}
		[self.managedObjectContext processPendingChanges];
		// If we're loading a calibration from a masterClip and it has a different calibrationTime than this project, ask the user about setting this project's calibration time to the loaded calibration's.
		if ([[fullCalibration objectAtIndex:8] boolValue] && ![self.videoClip.project.calibrationTimecode isEqualToString:[fullCalibration objectAtIndex:9]]) {
			bool setCalibrationTime = [UtilityFunctions ConfirmAction:@"The calibration you've loaded comes from a master clip, and includes a calibration time.  Do you want to set this project's calibration time to equal that one?" withTitle:@"Set calibration time?"];
			if (setCalibrationTime) self.videoClip.project.calibrationTimecode = [fullCalibration objectAtIndex:9];		// user clicked yes
		}
		[self calculateCalibration];
		[self.videoClip.project.document goToCalibrationTime:self];
	}
}


- (IBAction) exportDistortionToFile:(id)sender
{
	NSSavePanel *savePanel = [NSSavePanel savePanel];
	NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"mainFileSaveDirectory"];
	BOOL directoryExists;
	if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) [savePanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
	[savePanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncDistortion",nil]];
	if ([savePanel runModal]) {
		NSMutableArray *distortionLinesArray = [NSMutableArray array];
		for (VSDistortionLine *line in self.distortionLines) {
			NSMutableArray *distortionPointsArray = [NSMutableArray array];
			NSArray *sortedPoints = [[line.distortionPoints allObjects] sortedArrayUsingDescriptors:[NSArray arrayWithObject:[NSSortDescriptor sortDescriptorWithKey:@"index" ascending:YES]]];
			for (VSDistortionPoint *point in sortedPoints) {
				[distortionPointsArray addObject:[NSArray arrayWithObjects:point.screenX,point.screenY,point.index,nil]];
			}
			[distortionLinesArray addObject:[NSArray arrayWithObjects:line.timecode,distortionPointsArray,nil]];
		}
		NSArray *fullDistortion = [NSArray arrayWithObjects:
							  self.distortionCenterX,
							  self.distortionCenterY,
							  self.distortionK1,
							  self.distortionK2,
							  self.distortionK3,
							  self.distortionK4,
							  self.distortionK5,
							  self.distortionK6,
							  self.distortionK7,
							  self.distortionP1,
							  self.distortionP2,
							  self.distortionP3,
							  self.distortionP4,
							  distortionLinesArray,
							  nil];
		[fullDistortion writeToFile:[[savePanel URL] path] atomically:YES];
	}
}

- (IBAction) importDistortionFromFile:(id)sender;
{
	NSString *filePath;
	NSOpenPanel *openPanel = [NSOpenPanel openPanel];
	NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"mainFileSaveDirectory"];
	BOOL directoryExists;
	if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) [openPanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
	[openPanel setCanChooseFiles:YES];
	[openPanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncDistortion",nil]];
	[openPanel setCanChooseDirectories:NO];
	[openPanel setAllowsMultipleSelection:NO];
	if ([openPanel runModal]) {
		filePath = [[[openPanel URLs] objectAtIndex:0] path];
		NSArray *fullDistortion = [[NSArray alloc] initWithContentsOfFile:filePath];
		BOOL shouldOverwrite;
		if ([self.distortionLines count] > 0) {
			NSAlert *confirmOverwriteAlert = [NSAlert new];
			[confirmOverwriteAlert setMessageText:@"Overwrite current plumblines and parameters?"];
			[confirmOverwriteAlert setInformativeText:@"You can choose to overwrite any existing plumblines and parameters with new values from the file, or simply add the plumblines from the file to the list above."];
			[confirmOverwriteAlert addButtonWithTitle:@"Overwrite Plumblines and Parameters"];
			[confirmOverwriteAlert addButtonWithTitle:@"Just Add to Existing Plumblines"];
			[confirmOverwriteAlert setAlertStyle:NSAlertStyleCritical];
			NSModalResponse confirmOverwriteResponse = [confirmOverwriteAlert runModal];
			shouldOverwrite = (confirmOverwriteResponse == NSAlertFirstButtonReturn);
		} else {
			shouldOverwrite = YES; // If there was nothing to overwrite, simulate the user clicking "Overwrite" without prompting for it.
		}
		if (![fullDistortion isKindOfClass:[NSArray class]] || [fullDistortion count] < 9) {
			[UtilityFunctions InformUser:@"The distortion file could not be read or is from an unsupported version." withTitle:@"Invalid File"];
			return;
		}
		NSInteger numEntries = [fullDistortion count];
		NSInteger linesIndex = (numEntries > 13) ? 13 : 8; // extended format (14+ entries) puts lines at index 13; legacy format puts them at index 8
		if (shouldOverwrite) { // user clicked overwrite -- delete old distortion lines AND overwrite parameters
			self.distortionCenterX = [fullDistortion objectAtIndex:0];
			self.distortionCenterY = [fullDistortion objectAtIndex:1];
			self.distortionK1 = [fullDistortion objectAtIndex:2];
			self.distortionK2 = [fullDistortion objectAtIndex:3];
			self.distortionK3 = [fullDistortion objectAtIndex:4];
			if (numEntries > 12) {
				self.distortionK4 = [fullDistortion objectAtIndex:5];
				self.distortionK5 = [fullDistortion objectAtIndex:6];
				self.distortionK6 = [fullDistortion objectAtIndex:7];
				self.distortionK7 = [fullDistortion objectAtIndex:8];
				self.distortionP1 = [fullDistortion objectAtIndex:9];
				self.distortionP2 = [fullDistortion objectAtIndex:10];
				self.distortionP3 = [fullDistortion objectAtIndex:11];
				self.distortionP4 = [fullDistortion objectAtIndex:12];
			} else {
				self.distortionP1 = [fullDistortion objectAtIndex:5];
				self.distortionP2 = [fullDistortion objectAtIndex:6];
				self.distortionP3 = [fullDistortion objectAtIndex:7];
			}
			for (VSDistortionLine *lineToDelete in self.distortionLines) [self.managedObjectContext deleteObject:lineToDelete];		// remove the old points if there are any
		}
		VSDistortionLine *newLine;
		VSDistortionPoint *newPoint;
		for (NSArray *lineArray in [fullDistortion objectAtIndex:linesIndex]) {	// Regardless of overwrite setting, we now add points
			newLine = [NSEntityDescription insertNewObjectForEntityForName:@"VSDistortionLine" inManagedObjectContext:[self managedObjectContext]];
			newLine.calibration = self;
			newLine.timecode = [lineArray objectAtIndex:0];
			for (NSArray *pointArray in [lineArray objectAtIndex:1]) {
				newPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSDistortionPoint" inManagedObjectContext:[self managedObjectContext]];
				newPoint.distortionLine = newLine;
				newPoint.screenX = [pointArray objectAtIndex:0];
				newPoint.screenY = [pointArray objectAtIndex:1];
				newPoint.index = [pointArray objectAtIndex:2];
			}
			
		}
		[self.managedObjectContext processPendingChanges];
		[self.videoClip.windowController refreshOverlay];
	}
}


#pragma mark
#pragma mark Main Calculations

- (void) calculateCalibration
{
	BOOL calibrateFront = NO;
	BOOL calibrateBack = NO;
	
	// Check which surface(s) have enough points (empty or not) to be calibrated
	
	if ([self.pointsFront count] >= 4 && [self.pointsBack count] >= 4) {
		calibrateFront = YES;
		calibrateBack = YES;
	} else if ([self.pointsFront count] >= 4 || [self.pointsBack count] >= 4) {
		NSString *whichSurface = ([self.pointsFront count] >= 4) ? @"Front" : @"Back";
		NSAlert *tooFewPointsAlert = [NSAlert new];
		[tooFewPointsAlert setMessageText:@"Too few points for 3-D calibration"];
		[tooFewPointsAlert setInformativeText:[NSString stringWithFormat:@"To calibrate for 3-D measurement, you need at least 4 points on both surfaces and you only have points for the %@ surface.\n\nDo you want to proceed with a 2-D calibration on that surface, or cancel and enter points on the other surface for 3-D analysis?",whichSurface]];
		[tooFewPointsAlert addButtonWithTitle:@"Cancel"];
		[tooFewPointsAlert addButtonWithTitle:@"Proceed with 2-D calibration"];
		[tooFewPointsAlert setAlertStyle:NSAlertStyleCritical];
		NSInteger alertResult = [tooFewPointsAlert runModal];
		if (alertResult == NSAlertSecondButtonReturn) {
			([self.pointsFront count] >= 4) ? calibrateFront = YES : calibrateBack = YES;
		}
	} else {
		NSAlert *tooFewPointsAlert = [NSAlert new];
		[tooFewPointsAlert setMessageText:@"Too few points for calibration"];
		[tooFewPointsAlert setInformativeText:@"You need at least 4 points on both calibration frame surfaces for 3-D calibration (or on one surface for 2-D calibration)."];
		[tooFewPointsAlert addButtonWithTitle:@"Ok"];
		[tooFewPointsAlert setAlertStyle:NSAlertStyleCritical];
		[tooFewPointsAlert runModal];
	}
	
	// Check that all the points on the surface(s) being calibrated have both screen and qudarat coordinates
	
	int numIncompletePoints = 0;
	if (calibrateFront) for (VSCalibrationPoint *calPoint in self.pointsFront) if ([calPoint.screenX intValue] == 0 && [calPoint.screenY intValue] == 0) numIncompletePoints += 1;
	if (calibrateBack) for (VSCalibrationPoint *calPoint in self.pointsBack) if ([calPoint.screenX intValue] == 0 && [calPoint.screenY intValue] == 0) numIncompletePoints += 1;
	if (numIncompletePoints > 0) {
		calibrateFront = NO;
		calibrateBack = NO;
		NSAlert *tooFewPointsAlert = [NSAlert new];
		[tooFewPointsAlert setMessageText:@"Calibration points are incomplete"];
		[tooFewPointsAlert setInformativeText:[NSString stringWithFormat:@"There are %i calibration points in the table for which you haven't clicked the video to establish screen coordinates.\n\nEither establish coordinates for those points, or, if a point is not clearly visible to click, just delete it from the list instead of guessing its position.",numIncompletePoints]];
		[tooFewPointsAlert addButtonWithTitle:@"Ok"];
		[tooFewPointsAlert setAlertStyle:NSAlertStyleCritical];
		[tooFewPointsAlert runModal];
	}
	
	// The refraction question only arises for a 3D calibration, where the back surface is seen through the front
	// one. shouldCorrectRefraction is nil when the user has never been asked, which is distinct from having been
	// asked and said no. Refusing to calibrate until it is answered is the point: the setting is easy to
	// overlook, it is off unless chosen, and appendix A of Neuswanger et al. (2016) puts the resulting error at
	// 0.1 to 1 mm, described there as substantially affecting 3D measurements. Answering is remembered with the
	// calibration and travels with an exported frame description, so anyone reusing the same hardware answers
	// once rather than once per project.
	if (calibrateFront && calibrateBack && self.shouldCorrectRefraction == nil) {
		NSAlert *refractionQuestion = [NSAlert new];
		[refractionQuestion setMessageText:@"Does light from the back frame surface pass through a solid front surface?"];
		[refractionQuestion setInformativeText:@"VidSync needs to know before it can calibrate in 3D.\n\nIf your calibration frame has a transparent front face, such as a clear acrylic or glass sheet with the front nodes marked on it, light from the back nodes is refracted twice on its way to the camera and their apparent positions shift. Correcting for that requires the front face's thickness and refractive index, which you can enter under Refraction Correction Settings.\n\nIf your frame is an open wireframe, or the front and back surfaces are not separated by any solid material, no correction is needed.\n\nThis choice is saved with the calibration and is included when you export the frame description, so you only need to make it once per hardware setup."];
		[refractionQuestion addButtonWithTitle:@"Correct for Refraction"];
		[refractionQuestion addButtonWithTitle:@"No Solid Front Surface"];
		[refractionQuestion addButtonWithTitle:@"Cancel"];
		[[[refractionQuestion buttons] objectAtIndex:2] setKeyEquivalent:@"\033"];   // escape dismisses without answering
		[refractionQuestion setAlertStyle:NSAlertStyleInformational];
		NSModalResponse answer = [refractionQuestion runModal];
		if (answer == NSAlertThirdButtonReturn) return;   // Cancel: leave it unanswered and calibrate nothing
		self.shouldCorrectRefraction = [NSNumber numberWithBool:(answer == NSAlertFirstButtonReturn)];
		if ([self.shouldCorrectRefraction boolValue] && [self.frontQuadratSurfaceThickness doubleValue] <= 0.0) {
			[UtilityFunctions InformUser:@"Refraction correction is now on, but the front surface thickness is still zero, which makes the correction do nothing. Enter the thickness and refractive indices under Refraction Correction Settings, then calibrate again." withTitle:@"Enter the front surface thickness"];
			return;
		}
	}

	// If the points passed all the tests, run the calibration on the appropriate clips. Refraction correcton on the back surface is ignored if it is the only surface.

	if (calibrateFront) {
		[self calculateMatrix:@"Front" correctRefraction:NO];
		[self calculateFCMMatrix:@"Front"];
		[self calculatePixelResiduals:@"Front"];
		[self calculateWorldResiduals:@"Front"];
	}
	
	if (calibrateBack) {
		BOOL shouldCorrectRefraction = [self.shouldCorrectRefraction boolValue] && calibrateFront;  // Only correct refraction if set to, and if we're doing both front & back
		BOOL correctRefractionThisIteration = NO;
		int maxIterations = (shouldCorrectRefraction) ? 4 : 1;
		for (int i = 0; i < maxIterations; i++) {
			if (i > 0) correctRefractionThisIteration = YES;
			[self calculateMatrix:@"Back" correctRefraction:correctRefractionThisIteration];
			[self calculateFCMMatrix:@"Back"];														// update the cached, row-major vector forms of the matrices
			if (calibrateFront) [self calculateCameraPosition]; // can only get the front camera position if both clips have been calibrated
		}
		[self calculatePixelResiduals:@"Back"];
		[self calculateWorldResiduals:@"Back"];
	}
	
	[self.videoClip.windowController.overlayView calculateQuadratCoordinateGrids];		// and the cached quadrat coordinate grid
	
	if (calibrateFront || calibrateBack) {
		[self.videoClip.project.document recalculateAllPoints:self];
		[self.videoClip.windowController refreshOverlay];
		[self.videoClip.project.document.calibrationInputTabView selectLastTabViewItem:nil];	// Switch over to the "Results" tab after calculating the calibration.
	}
	
}

- (BOOL) frontIsCalibrated
{
	return (self.matrixScreenToQuadratFront != nil && self.matrixQuadratFrontToScreen != nil);
}

- (BOOL) backIsCalibrated
{
	return (self.matrixScreenToQuadratBack != nil && self.matrixQuadratBackToScreen != nil);
}

- (void) calculatePixelResiduals:(NSString *)whichSurface
{
	// Calculates the mean distance between the screen point clicked for a quadrat point, and the projection of that quadrat point's coordinates onto the screen using
	// the matrix result from the overall calibration, and redistorting so that result is directly comparable to the clicked point.
	
	NSPoint quadratPoint, projectedScreenPoint;
	float xdiff,ydiff;
	float totalResidual = 0.0;
	NSSet *__weak points = ([whichSurface isEqualToString:@"Front"]) ? self.pointsFront : self.pointsBack;
	for (VSCalibrationPoint *point in points) {
		quadratPoint = NSMakePoint([point.apparentWorldHcoord floatValue],[point.apparentWorldVcoord floatValue]);
		projectedScreenPoint = [self projectToScreenFromPoint:quadratPoint onQuadratSurface:whichSurface redistort:TRUE];
		xdiff = projectedScreenPoint.x - [point.screenX floatValue];
		ydiff = projectedScreenPoint.y - [point.screenY floatValue];
		totalResidual += sqrt(xdiff*xdiff + ydiff*ydiff);
	}
	long numPoints = ([whichSurface isEqualToString:@"Front"]) ? [self.pointsFront count] : [self.pointsBack count];
	if (numPoints == 0) return;  // no calibration points; residual is undefined
	NSNumber *residualPerPoint = [NSNumber numberWithFloat:(totalResidual / numPoints)];
	([whichSurface isEqualToString:@"Front"]) ? self.residualFrontPixel = residualPerPoint : self.residualBackPixel = residualPerPoint;
}

- (void) calculateWorldResiduals:(NSString *)whichSurface    
{
	// This one takes the clicked screen point, projects it onto the quadrat surface using the matrix resulting from the calibration, and compares it to the world point
	// that quadrat dot was supposed to represent.
	NSPoint screenPoint, projectedQuadratPoint;
	float xdiff,ydiff;
	float totalResidual = 0.0;
	NSSet *points = ([whichSurface isEqualToString:@"Front"]) ? self.pointsFront : self.pointsBack;
	for (VSCalibrationPoint *point in points) {
		screenPoint = NSMakePoint([point.screenX floatValue],[point.screenY floatValue]);
		projectedQuadratPoint = [self projectScreenPoint:screenPoint toQuadratSurface:whichSurface];
		xdiff = projectedQuadratPoint.x - [point.apparentWorldHcoord floatValue];
		ydiff = projectedQuadratPoint.y - [point.apparentWorldVcoord floatValue];
		totalResidual += sqrt(xdiff*xdiff + ydiff*ydiff);
	}
	long numPoints = [points count];
	if (numPoints == 0) return;  // no calibration points; residual is undefined
	NSNumber *residualPerPoint = [NSNumber numberWithFloat:(totalResidual / numPoints)];
	([whichSurface isEqualToString:@"Front"]) ? self.residualFrontWorld = residualPerPoint : self.residualBackWorld = residualPerPoint;
}

- (void) calculateCameraPosition
{
	// I create a grid of simulated clicked screen points evenly covering the entire video, from each edge/corner and evenly spaced through the middle.
	// I find the 3D lines created by projecting each clicked point into the front and back quadrat coordinate systems.
	// Those lines all theoretically converge at the camera's position, but due to small numerical/calibration errors they don't exactly converge.
	// I use the mean of all the pairwise intersections of all these lines to get the best estimate of the camera's position.
	// float tempPointIncrement = 0.01;
	// int numLines = (1.0/tempPointIncrement + 1)*(1.0/tempPointIncrement + 1);
	size_t numLines = [self.pointsBack count];
	VSLine3D lines[numLines];
	int k = 0;
	for (VSCalibrationPoint *backPoint in self.pointsBack) {
		VSEventScreenPoint *tempScreenPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSEventScreenPoint" inManagedObjectContext:[self managedObjectContext]];
		tempScreenPoint.videoClip = self.videoClip;
		tempScreenPoint.screenX = backPoint.screenX;
		tempScreenPoint.screenY = backPoint.screenY;
		lines[k] = [tempScreenPoint computeLine3D:NO];
		[[self managedObjectContext] deleteObject:tempScreenPoint];
		k += 1;
	}
	
	double pld; // Mean point-line distance from all the intersection lines to the camera position
	VSPoint3D cameraPoint = [UtilityFunctions intersectionOfNumber:numLines of3DLines:lines meanPLD:&pld];
	
	self.cameraX = [NSNumber numberWithDouble:cameraPoint.x];
	self.cameraY = [NSNumber numberWithDouble:cameraPoint.y];
	self.cameraZ = [NSNumber numberWithDouble:cameraPoint.z];
	self.cameraMeanPLD = [NSNumber numberWithDouble:pld];
}

- (NSArray *) candidateCameraPositionsForRefinement
{
	NSArray *allPositions = [NSArray array];
	double halfwidth = 0.0005;    // half the width of the cubic lattice in each direction -- THIS SUCKS BECAUSE IT DEPENDS ON MY UNITS ANYWAY
	double halfnumpoints = 1;       // the number of points across the cubic lattice in each direction
	VSPoint3D tempCameraPoint;
	for (double x = -halfwidth; x <= halfwidth; x += halfwidth/halfnumpoints) {
		for (double y = -halfwidth; y <= halfwidth; y += halfwidth/halfnumpoints) {
			for (double z = -halfwidth; z <= halfwidth; z += halfwidth/halfnumpoints) {
				tempCameraPoint.x = [self.cameraX doubleValue] + x;
				tempCameraPoint.y = [self.cameraY doubleValue] + y;
				tempCameraPoint.z = [self.cameraZ doubleValue] + z;
				allPositions = [allPositions arrayByAddingObject:[NSArray arrayWithObjects:[NSNumber numberWithDouble:tempCameraPoint.x],[NSNumber numberWithDouble:tempCameraPoint.y],[NSNumber numberWithDouble:tempCameraPoint.z],nil]];
			}
		}
	}
	
	return allPositions;
}

- (void) calculateMatrix:(NSString *)whichMatrix correctRefraction:(BOOL)correctRefraction
{
	// This function implements the normalized Direct Linear Transformation algorithm described in Multiple View Geometry in Computer Vision by Hartley & Zisserman.
	// It also uses a custom refraction correction function to adjust the positions of the back points.
	
	NSSet *points;
	if ([whichMatrix isEqualToString:@"Front"]) {
		points = self.pointsFront;
	} else {
		points = self.pointsBack;
	}
	
	for (VSCalibrationPoint *point in points) {
		if ([whichMatrix isEqualToString:@"Back"] && correctRefraction) {
			[self refractionCorrectApparentPositionOfBackQuadratPoint:point];
		} else {
			point.apparentWorldHcoord = point.worldHcoord;
			point.apparentWorldVcoord = point.worldVcoord;
		}
	}
	
	// The first step is to condition all the points so they're centered on the origin and their average distance from it is the square root of 2.  Condition both the world (quadrat face) and screen coordinates.
	// Note that I'm not calculating the inverses directly from the normalized version of the projection matrix.  There's no need.  It's easier to do the inverses from the final de-normalized projection matrix,
	// and that matrix is conditioned well enough that its inverse can be calculated just fine.
	
	double totalScreenX = 0.0;
	double totalScreenY = 0.0;
	double totalWorldH = 0.0;
	double totalWorldV = 0.0;
	NSPoint undistortedTempPoint;
	for (VSCalibrationPoint *point in points) {
		undistortedTempPoint = [self undistortPoint:NSMakePoint([point.screenX doubleValue],[point.screenY doubleValue])];
		totalScreenX += undistortedTempPoint.x;
		totalScreenY += undistortedTempPoint.y;
		totalWorldH += [point.apparentWorldHcoord doubleValue];
		totalWorldV += [point.apparentWorldVcoord doubleValue];
	}
	
	NSPoint screenCentroid,worldCentroid;
	screenCentroid = NSMakePoint(totalScreenX/[points count],totalScreenY/[points count]);
	worldCentroid = NSMakePoint(totalWorldH/[points count],totalWorldV/[points count]);
	
	double totalScreenNorm = 0.0;
	double totalWorldNorm = 0.0;
	double temppt[2];
	for (VSCalibrationPoint *point in points) {
		undistortedTempPoint = [self undistortPoint:NSMakePoint([point.screenX doubleValue],[point.screenY doubleValue])];
		temppt[0] = undistortedTempPoint.x - screenCentroid.x;
		temppt[1] = undistortedTempPoint.y - screenCentroid.y;
		totalScreenNorm += cblas_dnrm2(2,temppt,1);
		temppt[0] = [point.apparentWorldHcoord doubleValue] - worldCentroid.x;
		temppt[1] = [point.apparentWorldVcoord doubleValue] - worldCentroid.y;
		totalWorldNorm += cblas_dnrm2(2,temppt,1);
	}
	if (totalScreenNorm == 0.0 || totalWorldNorm == 0.0) return;  // all points are identical; normalization is undefined
	const double screenScaleFactor = sqrt(2.0) / (totalScreenNorm / [points count]);
	const double worldScaleFactor = sqrt(2.0) / (totalWorldNorm / [points count]);
	
	NSMutableSet *conditionedPoints = [NSMutableSet new];
	for (VSCalibrationPoint *point in points) {
		undistortedTempPoint = [self undistortPoint:NSMakePoint([point.screenX doubleValue],[point.screenY doubleValue])];
		[conditionedPoints addObject:[NSArray arrayWithObjects:
								[NSNumber numberWithDouble:(undistortedTempPoint.x-screenCentroid.x)*screenScaleFactor],                      // Screen X
								[NSNumber numberWithDouble:(undistortedTempPoint.y-screenCentroid.y)*screenScaleFactor],                      // Screen Y
								[NSNumber numberWithDouble:([point.apparentWorldHcoord doubleValue]-worldCentroid.x)*worldScaleFactor],               // World H
								[NSNumber numberWithDouble:([point.apparentWorldVcoord doubleValue]-worldCentroid.y)*worldScaleFactor],               // World V
								nil]
		 ];
	}
	
	// This section creates a C array, named A, to hold the linear system describing the screen-to-quadrat point correspondences in normalized coordinates.
	// This sets up the matrix rows as described in equation (4.3) of Multiple View Geometry in Computer Vision, except the variable names are different and
	// the sign of one of the rows is arbitrarily flipped (following the older code I got from Lon), but that makes no difference at all because it's representing
	// an equation that's equal to zero on the other side.
	
	double X,Z,x,z;
	int numRows = (int) [points count] * 2;
	int i = 0;
	double A[numRows][9];
	// Fill in the matrix A in an intuitive, row-major, two-dimensional form just to keep the code intuitive
	for (NSMutableArray *point in conditionedPoints) {
		X = [[point objectAtIndex:0] doubleValue];     // Note that there's no need to deal with distortion here because it's dealt with when constructing the conditioned points.
		Z = [[point objectAtIndex:1] doubleValue];
		x = [[point objectAtIndex:2] doubleValue];
		z = [[point objectAtIndex:3] doubleValue];
		double rowA[9] = {X, Z, 1, 0, 0, 0, -x*X, -x*Z, -x};
		double rowB[9] = {0, 0, 0, X, Z, 1, -z*X, -z*Z, -z};
		for (int j = 0; j < 9; j++) {
			A[i][j] = rowA[j];
			A[i+1][j] = rowB[j];
		}
		i += 2;
	}
	
	double a[numRows*9];			// Hold a column-major version of the linear system A for use in the main calculations
	double a_r[numRows*9];			// Hold a copy of a for cblas_dgemv to use in the residual calcuation A*x
	[VSCalibration arrange2DArray:A withRows:numRows intoColumnMajorVector:a];
	memcpy(a_r, a, numRows * 9 * sizeof (double));
	
	double p[9];					// Holds the projection matrix (screen coordinates to quadrat coordinates) as a 9-element vector
	double pinv[9];					// Holds the inverse of the projection matrix (quadrat coordinates to screen coordinates) as a 9-element vector
	double x_r[9];					// Holds a copy of p for cblas_dgemv to use in the residual calculation A*x
	[VSCalibration putLeastSquaresSolutionForOverdeterminedSystem:A withRows:numRows intoOutputMatrix:p];
	
	// Now we have solved for the Screen -> Quadrat projection matrix in normalized coordinates.  We need to get the matrix for regular, non-normalized coordinates.  We do this by taking the normalized projection
	// matrix, right-multiplying it by a matrix that normalizes screen coordinates, and left-multiplying it by a matrix that de-normalizes quadrat coordinates.  These multiplying matrices are just simple 3x3 translation/scaling
	// matrices, written here in 1D column-major form.  This procedure OVERWRITES the original p matrix with the result.
	
	double normalizingMatrix[9] = {screenScaleFactor, 0, 0, 0, screenScaleFactor, 0, -screenScaleFactor*screenCentroid.x, -screenScaleFactor*screenCentroid.y, 1};       // Normalizes screen coordinates.
	double denormalizingMatrix[9] = {1/worldScaleFactor, 0, 0, 0, 1/worldScaleFactor, 0, worldCentroid.x, worldCentroid.y, 1};                                          // De-normalizes quadrat coordinates.
	double halfway[9];
	memcpy(x_r, p, 9 * sizeof (double));			// copy normalized p into x_r for residual before denormalization overwrites it
	[VSCalibration rightMultiply3x3Matrix:p trans:CblasNoTrans by3x3Matrix:normalizingMatrix trans:CblasNoTrans intoResultingMatrix:halfway];
	[VSCalibration rightMultiply3x3Matrix:denormalizingMatrix trans:CblasNoTrans by3x3Matrix:halfway trans:CblasNoTrans intoResultingMatrix:p];

	// Now we can calculate the inverse of the new p as normal in the non-normalized coordinates.

	memcpy(pinv, p, 9 * sizeof (double));			// copy p into pinv for inversion
	[VSCalibration invert3x3Matrix:pinv];	// place the inverse of p into pinv
	
	double residual = [self leastSquaresResidualWithA:a_r x:x_r rowsA:numRows];	// the least squares residual of the calibration
	
	if ([whichMatrix isEqualToString:@"Front"]) {
		self.matrixScreenToQuadratFront = [VSCalibration createMatrixOfNSArraysFromCMatrix:p];
		self.matrixQuadratFrontToScreen = [VSCalibration createMatrixOfNSArraysFromCMatrix:pinv];
		self.residualFrontLeastSquares = [NSNumber numberWithDouble:(residual / [self.pointsFront count])];
	} else {
		self.matrixScreenToQuadratBack = [VSCalibration createMatrixOfNSArraysFromCMatrix:p];
		self.matrixQuadratBackToScreen = [VSCalibration createMatrixOfNSArraysFromCMatrix:pinv];
		self.residualBackLeastSquares = [NSNumber numberWithDouble:(residual / [self.pointsBack count])];
	}
	
	[[self managedObjectContext] processPendingChanges];
	[self calculateFCMMatrix:whichMatrix];
	
}

- (void) refractionCorrectApparentPositionOfBackQuadratPoint:(VSCalibrationPoint*)point
{
	double frontSurfaceThickness = [self.frontQuadratSurfaceThickness doubleValue]; // 0.009525;
	
	RefractionSolverParams p;
	if ([self.axisHorizontal length] == 0 || [self.axisVertical length] == 0) return;
	p.axisHorizontal = [self.axisHorizontal characterAtIndex:0];
	p.axisVertical   = [self.axisVertical characterAtIndex:0];
	p.frontSurfaceCoord = [self.planeCoordFront doubleValue];
	// The two surfaces here are the camera-side and back-plane-side faces of the front frame pane, not the
	// front and back frame planes (see the note above refractionRootFunc_f). So the pane's thickness has to be
	// applied in whichever direction the back frame plane lies, which is not necessarily the +axis direction:
	// nothing stops a user from putting the front plane at 0 and the back plane at -0.439 instead of +0.439.
	// Adding an unsigned thickness in that case modelled the pane on the camera side of the front plane, which
	// applies the correction with inverted geometry and roughly doubles the error it exists to remove.
	const double frontToBack = [self.planeCoordBack doubleValue] - p.frontSurfaceCoord;
	p.backSurfaceCoord = p.frontSurfaceCoord + copysign(frontSurfaceThickness, frontToBack);
	p.camPosition = VSMakePoint3D([self.cameraX doubleValue],[self.cameraY doubleValue],[self.cameraZ doubleValue]);
	p.n1 = [self.mediumRefractiveIndex doubleValue];  // 1.3364;  // index of refraction of the medium between the quadrat planes (typically water)
	p.n2 = [self.frontQuadratSurfaceRefractiveIndex doubleValue]; // 1.585;  // index of refraction of the front quadrat plane material (such as glass)
	p.n3 = p.n1;  // index of refraction of the material between the front quadrat plane and the camera (should always be the same as p.n1)
	
	if (p.axisHorizontal == 'x') {
		if (p.axisVertical == 'y') {
			p.realPosition = VSMakePoint3D([point.worldHcoord doubleValue], [point.worldVcoord doubleValue], [self.planeCoordBack doubleValue]);
		} else {    // axisVertical == z
			p.realPosition = VSMakePoint3D([point.worldHcoord doubleValue], [self.planeCoordBack doubleValue], [point.worldVcoord doubleValue]);
		}
	} else if (p.axisHorizontal == 'y') {
		if (p.axisVertical == 'x') {
			p.realPosition = VSMakePoint3D([point.worldVcoord doubleValue], [point.worldHcoord doubleValue], [self.planeCoordBack doubleValue]);
		} else {    // axisVertical == z
			p.realPosition = VSMakePoint3D([self.planeCoordBack doubleValue], [point.worldHcoord doubleValue], [point.worldVcoord doubleValue]);
		}
	} else {    // axisHorizontal == z
		if (p.axisVertical == 'x') {
			p.realPosition = VSMakePoint3D([point.worldVcoord doubleValue], [self.planeCoordBack doubleValue], [point.worldHcoord doubleValue]);
		} else {    // axisVertical == y
			p.realPosition = VSMakePoint3D([self.planeCoordBack doubleValue], [point.worldVcoord doubleValue], [point.worldHcoord doubleValue]);
		}
	}
	
	VSLine3D initLine;
	initLine.front = p.realPosition;
	initLine.back = p.camPosition;
	VSPoint3D pointsDefiningFrontPlane[3];          // front surface of the front plane of the quadrat
	VSPoint3D pointsDefiningBackPlane[3];           // back surface of the front plane of the quadrat (separated by frontSurfaceThickness from the back plane)
	VSPoint3D pointsDefiningQuadratBackPlane[3];    // front surface of the back plane of the quadrat
	
	if ((p.axisHorizontal == 'x' && p.axisVertical == 'y') || (p.axisHorizontal == 'y' && p.axisVertical == 'x')) {
		pointsDefiningFrontPlane[0] = VSMakePoint3D(0.0, 0.0, p.frontSurfaceCoord);
		pointsDefiningFrontPlane[1] = VSMakePoint3D(1.0, 0.0, p.frontSurfaceCoord);
		pointsDefiningFrontPlane[2] = VSMakePoint3D(0.0, 1.0, p.frontSurfaceCoord);
		pointsDefiningBackPlane[0]  = VSMakePoint3D(0.0, 0.0, p.backSurfaceCoord);
		pointsDefiningBackPlane[1]  = VSMakePoint3D(1.0, 0.0, p.backSurfaceCoord);
		pointsDefiningBackPlane[2]  = VSMakePoint3D(0.0, 1.0, p.backSurfaceCoord);
		pointsDefiningQuadratBackPlane[0]  = VSMakePoint3D(0.0, 0.0, p.realPosition.z);
		pointsDefiningQuadratBackPlane[1]  = VSMakePoint3D(1.0, 0.0, p.realPosition.z);
		pointsDefiningQuadratBackPlane[2]  = VSMakePoint3D(0.0, 1.0, p.realPosition.z);
	} else if ((p.axisHorizontal == 'x' && p.axisVertical == 'z') || (p.axisHorizontal == 'z' && p.axisVertical == 'x')) {
		pointsDefiningFrontPlane[0] = VSMakePoint3D(0.0, p.frontSurfaceCoord, 0.0);
		pointsDefiningFrontPlane[1] = VSMakePoint3D(1.0, p.frontSurfaceCoord, 0.0);
		pointsDefiningFrontPlane[2] = VSMakePoint3D(0.0, p.frontSurfaceCoord, 1.0);
		pointsDefiningBackPlane[0]  = VSMakePoint3D(0.0, p.backSurfaceCoord, 0.0);
		pointsDefiningBackPlane[1]  = VSMakePoint3D(1.0, p.backSurfaceCoord, 0.0);
		pointsDefiningBackPlane[2]  = VSMakePoint3D(0.0, p.backSurfaceCoord, 1.0);
		pointsDefiningQuadratBackPlane[0]  = VSMakePoint3D(0.0, p.realPosition.y, 0.0);
		pointsDefiningQuadratBackPlane[1]  = VSMakePoint3D(1.0, p.realPosition.y, 0.0);
		pointsDefiningQuadratBackPlane[2]  = VSMakePoint3D(0.0, p.realPosition.y, 1.0);
	} else if ((p.axisHorizontal == 'y' && p.axisVertical == 'z') || (p.axisHorizontal == 'z' && p.axisVertical == 'y')) {
		pointsDefiningFrontPlane[0] = VSMakePoint3D(p.frontSurfaceCoord, 0.0, 0.0);
		pointsDefiningFrontPlane[1] = VSMakePoint3D(p.frontSurfaceCoord, 1.0, 0.0);
		pointsDefiningFrontPlane[2] = VSMakePoint3D(p.frontSurfaceCoord, 0.0, 1.0);
		pointsDefiningBackPlane[0]  = VSMakePoint3D(p.backSurfaceCoord, 0.0, 0.0);
		pointsDefiningBackPlane[1]  = VSMakePoint3D(p.backSurfaceCoord, 1.0, 0.0);
		pointsDefiningBackPlane[2]  = VSMakePoint3D(p.backSurfaceCoord, 0.0, 1.0);
		pointsDefiningQuadratBackPlane[0]  = VSMakePoint3D(p.realPosition.x, 0.0, 0.0);
		pointsDefiningQuadratBackPlane[1]  = VSMakePoint3D(p.realPosition.x, 1.0, 0.0);
		pointsDefiningQuadratBackPlane[2]  = VSMakePoint3D(p.realPosition.x, 0.0, 1.0);
	}
	
	VSPoint3D initialFrontPoint3D = [UtilityFunctions intersectionOfLine:initLine withPlaneDefinedByPoints:pointsDefiningFrontPlane];
	VSPoint3D initialBackPoint3D = [UtilityFunctions intersectionOfLine:initLine withPlaneDefinedByPoints:pointsDefiningBackPlane];
	
	// Solve for the roots to find where the refracted line-of-sight from the back quadrat point intersects both surface of the front quadrat face
	const gsl_multiroot_fsolver_type *T = gsl_multiroot_fsolver_hybrids;
	gsl_multiroot_fsolver *s = gsl_multiroot_fsolver_alloc(T, 4);
	gsl_multiroot_function f = {&refractionRootFunc_f, 4, &p};
	gsl_vector *x = gsl_vector_alloc(4);    // Initial values
	gsl_vector_set(x, 0, VSPoint3DElementByName(p.axisHorizontal, initialBackPoint3D));
	gsl_vector_set(x, 1, VSPoint3DElementByName(p.axisVertical, initialBackPoint3D));
	gsl_vector_set(x, 2, VSPoint3DElementByName(p.axisHorizontal, initialFrontPoint3D));
	gsl_vector_set(x, 3, VSPoint3DElementByName(p.axisVertical, initialFrontPoint3D));
	gsl_multiroot_fsolver_set(s, &f, x);
	int status;
	size_t iter = 0;
	do {
		iter++;
		status = gsl_multiroot_fsolver_iterate(s);
		if (status) break;
		status = gsl_multiroot_test_residual(s->f, 1e-7);
	} while (status == GSL_CONTINUE && iter < 1000);
	
	// Process the minimizaton result to get the 3-D point at which the line of sight from the back quadrat point intersects the front surface of the front face of the quadrat
	VSPoint3D solvedFrontIntersection;
	const double solvedFrontCoord1 = gsl_vector_get(s->x,2);   // I don't actually use the solved back surface coord (remember, it's not the back quadrat plane, but the back surface of the quadrat front)
	const double solvedFrontCoord2 = gsl_vector_get(s->x,3);   // for calculating the apparent position.  It's just part of the process of solving for the front surface coord.
	if (p.axisHorizontal == 'x') {
		if (p.axisVertical == 'y') {
			solvedFrontIntersection = VSMakePoint3D(solvedFrontCoord1, solvedFrontCoord2, p.frontSurfaceCoord);
		} else {    // axisVertical == z
			solvedFrontIntersection = VSMakePoint3D(solvedFrontCoord1, p.frontSurfaceCoord, solvedFrontCoord2);
		}
	} else if (p.axisHorizontal == 'y') {
		if (p.axisVertical == 'x') {
			solvedFrontIntersection = VSMakePoint3D(solvedFrontCoord2, solvedFrontCoord1, p.frontSurfaceCoord);
		} else {    // axisVertical == z
			solvedFrontIntersection = VSMakePoint3D(p.frontSurfaceCoord, solvedFrontCoord1, solvedFrontCoord2);
		}
	} else {    // axisHorizontal == z
		if (p.axisVertical == 'x') {
			solvedFrontIntersection = VSMakePoint3D(solvedFrontCoord2, p.frontSurfaceCoord, solvedFrontCoord1);
		} else {    // axisVertical == y
			solvedFrontIntersection = VSMakePoint3D(p.frontSurfaceCoord, solvedFrontCoord2, solvedFrontCoord1);
		}
	}
	// Free the memory used by the solver
	gsl_multiroot_fsolver_free (s);
	gsl_vector_free(x);
	
	// Calculate the final back point
	VSLine3D lineOfSight;
	lineOfSight.front = p.camPosition;
	lineOfSight.back = solvedFrontIntersection;
	VSPoint3D apparentPosition3D = [UtilityFunctions intersectionOfLine:lineOfSight withPlaneDefinedByPoints:pointsDefiningQuadratBackPlane];
	// NSLog(@"For real position (%1.3f, %1.3f, %1.3f), solved 3-D position is: (%1.8f, %1.8f, %1.8f)",p.realPosition.x,p.realPosition.y,p.realPosition.z,apparentPosition3D.x,apparentPosition3D.y,apparentPosition3D.z);
	NSPoint apparentPosition2D;
	if (p.axisHorizontal == 'x') {
		if (p.axisVertical == 'y') {
			apparentPosition2D = NSMakePoint(apparentPosition3D.x, apparentPosition3D.y);
		} else {    // axisVertical == z
			apparentPosition2D = NSMakePoint(apparentPosition3D.x, apparentPosition3D.z);
		}
	} else if (p.axisHorizontal == 'y') {
		if (p.axisVertical == 'x') {
			apparentPosition2D = NSMakePoint(apparentPosition3D.y, apparentPosition3D.x);
		} else {    // axisVertical == z
			apparentPosition2D = NSMakePoint(apparentPosition3D.y, apparentPosition3D.z);
		}
	} else {    // axisHorizontal == z
		if (p.axisVertical == 'x') {
			apparentPosition2D = NSMakePoint(apparentPosition3D.z, apparentPosition3D.x);
		} else {    // axisVertical == y
			apparentPosition2D = NSMakePoint(apparentPosition3D.z, apparentPosition3D.y);
		}
	}
	// Finally, fill in the apparent position properties of the VSCalibrationPoint using the solved, refracted position
	point.apparentWorldHcoord = [NSNumber numberWithDouble:apparentPosition2D.x];
	point.apparentWorldVcoord = [NSNumber numberWithDouble:apparentPosition2D.y];
}

+ (void) invert3x3Matrix:(double[9])A
{
	// before dgtrf_, A contains the m x n matrix A to be factored; after dgetrf_ it contains L and U, without storing the unit diagonals of L
	// after dgetri_, it contains the inverse of A (this is effectively passed by reference, so it has the effect of inverting the original matrix variable that's passed in
	
	// dgetrf_ calculates the lu factorization, A=P*L*U where P is a permutation matrix, L is lower triangular with unit diagonals, and U is upper triangular
	// This function is needed to generate the pivot indices and the input matrix for dgetri_.
	__CLPK_integer m_f = 3;						// number of rows in the matrix A
	__CLPK_integer n_f = 3;						// number of columns in the matrix A
	__CLPK_integer lda_f = 3;					// leading dimension of A
	__CLPK_integer ipiv_fi[3];					// output parameter: integer array of pivot indices (needed for input to dgetri_
	__CLPK_integer info_f;						// output parameter: if 0, success; if -i, ith argument had an illegal value; if >0, irrelevant
	dgetrf_(&m_f,&n_f,A,&lda_f,ipiv_fi,&info_f);
	
	// Now call dgetri_ to calculate the inverse, using a_fi and ipiv_fi from above and the values defined below
	__CLPK_integer n_i = 3;						// order of the matrix
	__CLPK_integer lda_i = 3;					// leading dimension of matrix A
	__CLPK_doublereal work_i[64*9];				// workspace array; I'm not sure what it's used for exactly
	__CLPK_integer lwork_i = 64*9;				// length of the work array; borrowing this value from a working example of sgelss
	__CLPK_integer info_i;						// output parameter; if 0; success; if -i, ith argument had illegal value; if >0, matrix is singular and has no inverse
	dgetri_(&n_i,A,&lda_i,ipiv_fi,work_i,&lwork_i,&info_i);
	
}


+ (NSArray *) createMatrixOfNSArraysFromCMatrix:(double[9])p					// Used for storing the projection matrices in Core Data.
{
	double m[3][3] = {				// This conversion into a 2-dimensional c matrix is totally frivolous, and is a relic of an earlier
		{p[0],p[3],p[6]},			// version of the calculation in which it was more necessary.  However, now my calibrations are stored
		{p[1],p[4],p[7]},			// as 2D arrays in the data model, so I might as well keep it this way and just do the conversions.
		{p[2],p[5],p[8]}
	};
	return [NSArray arrayWithObjects:
		   [NSArray arrayWithObjects:
		    [NSNumber numberWithDouble:m[0][0]],
		    [NSNumber numberWithDouble:m[0][1]],
		    [NSNumber numberWithDouble:m[0][2]],nil
		    ],
		   [NSArray arrayWithObjects:
		    [NSNumber numberWithDouble:m[1][0]],
		    [NSNumber numberWithDouble:m[1][1]],
		    [NSNumber numberWithDouble:m[1][2]],nil
		    ],
		   [NSArray arrayWithObjects:
		    [NSNumber numberWithDouble:m[2][0]],
		    [NSNumber numberWithDouble:m[2][1]],
		    [NSNumber numberWithDouble:m[2][2]],nil
		    ],nil];
}

- (double) leastSquaresResidualWithA:(double*)a_r x:(double[9])x_r rowsA:(int)rowsA
{
	// Now we calculate the residuals.  The calibration above was all about finding x such that A*x=0, but since it's an overdetermined system we can't quite get to 0.
	// So we used a least squares method to minimize |A*x|.  The residual for this clip/surface is the value we ended up with for that minimum, |A*x|.
	// The value of A is a_r, calculated in above, and x is x_r, also calculated above.  Both are already in column-major form.
	// The cblas_dgemv routine actually calculates alpha*A*x + beta*Y, and in this case alpha, beta, and Y are all 0 on input.  Y contains the result on output.
	
	int m_r = rowsA;							// rows in the matrix A
	int n_r = 9;								// columns in the matrix A
	double alpha_r = 1.0;						// scaler multiplier for A, set to 1.0 for no effect
	int lda_r = rowsA;							// the leading dimension of A
	int incX_r = 1;								// increment for X, should always be 1 in my case
	double beta_r = 0.0;						// scalar multiplier for y's initial value; set to 0 for this simple multiplication
	double y_r[rowsA];								// vector to hold the results of the computation
	int incY_r = 1;								// increment for Y, should always be 1 in my case
	
	cblas_dgemv(CblasColMajor, CblasNoTrans, m_r, n_r, alpha_r, a_r, lda_r, x_r, incX_r, beta_r, y_r, incY_r);	// Compute the residual vector (9 elements; stored in y_r)
	
	return cblas_dnrm2(rowsA,y_r,1);		// the residual is the 2-norm of y_r
}

#pragma mark
#pragma mark Result: Projection Functions


- (NSPoint) projectScreenPoint:(NSPoint)screenPoint toQuadratSurface:(NSString *)surface    // this one automatically undistorts the point
{	
	NSPoint undistortedPoint = [self undistortPoint:screenPoint];
	NSPoint projectedPoint;
	if ([surface isEqualToString:@"Front"]) {
		if (matrixScreenToQuadratFrontFCM[0] == 0.0) [self calculateFCMMatrix:surface];
		projectedPoint = [UtilityFunctions project2DPoint:undistortedPoint usingMatrix:matrixScreenToQuadratFrontFCM];
	} else {																												// if not Front surface, must be Back
		if (matrixScreenToQuadratBackFCM[0] == 0.0) [self calculateFCMMatrix:surface];
		projectedPoint = [UtilityFunctions project2DPoint:undistortedPoint usingMatrix:matrixScreenToQuadratBackFCM];
	}
	return projectedPoint;
}

- (NSPoint) projectToScreenFromPoint:(NSPoint)quadratPoint onQuadratSurface:(NSString *)surface redistort:(BOOL)redistort
{
	NSPoint undistortedScreenPoint;
	if ([surface isEqualToString:@"Front"]) {
		if (matrixQuadratFrontToScreenFCM[0] == 0.0) [self calculateFCMMatrix:surface];
		undistortedScreenPoint = [UtilityFunctions project2DPoint:quadratPoint usingMatrix:matrixQuadratFrontToScreenFCM];
	} else {																												// if not Front surface, must be Back
		if (matrixQuadratBackToScreenFCM[0] == 0.0) [self calculateFCMMatrix:surface];
		undistortedScreenPoint = [UtilityFunctions project2DPoint:quadratPoint usingMatrix:matrixQuadratBackToScreenFCM];
	}
	if (redistort) {
		return [self distortPoint:undistortedScreenPoint];
	} else {
		return undistortedScreenPoint;
	}
}

#pragma mark
#pragma mark Distortion Correction

- (BOOL) hasDistortionCorrection
{
	return (self.distortionCenterX != nil && self.distortionCenterY != nil && self.distortionK1 != nil && [self.distortionK1 floatValue] != 0.0);
}

/*
 It's important that I keep distortPoint and undistortPoint straight in the code, so I don't double-distort or double-undistort anything by accident.
 Therefore, I'm keeping track here of eactly where I use them.
 
 undistortPoint
 - [VSCalibration calculateMatrix]				applied to calibration screen points before calculating the projection matrices
 - [VSCalibration projectScreenPoint:toQuadratSurface:]
 
 distortPoint
 - [VSCalibration projectToScreenFromPoint:onQuadratSurface:]
 - [VSHintLine bezierPathForLineWithInterval:]					used to translate undistorted, straight hintlines into real distorted ones
 */

- (NSPoint) distortPoint:(NSPoint)undistortedPoint
{
	if (![self hasDistortionCorrection]) return undistortedPoint;		// just return the original point if there's no distortion correction yet
	return redistortPoint(
					  &undistortedPoint,
					  [self.distortionCenterX doubleValue],
					  [self.distortionCenterY doubleValue],
					  [self.distortionK1 doubleValue],
					  [self.distortionK2 doubleValue],
					  [self.distortionK3 doubleValue],
					  [self.distortionK4 doubleValue],
					  [self.distortionK5 doubleValue],
					  [self.distortionK6 doubleValue],
					  [self.distortionK7 doubleValue],
					  [self.distortionP1 doubleValue],
					  [self.distortionP2 doubleValue],
					  [self.distortionP3 doubleValue],
					  [self.distortionP4 doubleValue]
					  );
}

- (NSPoint) undistortPoint:(NSPoint)distortedPoint  // Undistorts a point with this calibration's saved lambda value.
{
	if (![self hasDistortionCorrection]) return distortedPoint;			// just return the original point if there's no distortion correction yet
	return undistortPoint(
					  &distortedPoint,
					  [self.distortionCenterX doubleValue],
					  [self.distortionCenterY doubleValue],
					  [self.distortionK1 doubleValue],
					  [self.distortionK2 doubleValue],
					  [self.distortionK3 doubleValue],
					  [self.distortionK4 doubleValue],
					  [self.distortionK5 doubleValue],
					  [self.distortionK6 doubleValue],
					  [self.distortionK7 doubleValue],
					  [self.distortionP1 doubleValue],
					  [self.distortionP2 doubleValue],
					  [self.distortionP3 doubleValue],
					  [self.distortionP4 doubleValue]
					  );
}

 - (cv::Point2f) centroidOfCvPoints:(std::vector<cv::Point2f> &)points
 {
	 if (points.empty()) return cv::Point2f(0.0f, 0.0f);
	 double xtot = 0.0;
	 double ytot = 0.0;
	 for (int i=0; i<points.size(); i++) {
	 xtot += points[i].x;
	 ytot += points[i].y;
	 }
	 double xmean = xtot / (double) points.size();
	 double ymean = ytot / (double) points.size();
	 return cv::Point2f(xmean,ymean);
 }

- (int) indexOfNearestPointTo:(cv::Point2f)position inCvPoints:(std::vector<cv::Point2f> &)points bestDistance:(double *)bestDistance
{
	int bestIndex = 0;
	double tempBestDistance = 100000.0;  // Start out with the "best" distance longer than any real points can have, so it's replaced ASAP.
	double distance,a,b;
	for (int i=0; i<points.size(); i++) {
		a = position.x - points[i].x;
		b = position.y - points[i].y;
		distance = sqrt(a*a + b*b);
		if (distance < tempBestDistance && distance > 0.0001) {    // Exclude distance ~0 so I don't select the same point as the closest.
			tempBestDistance = distance;
			bestIndex = i;
		}
	}
	if (bestDistance != nil) {
		*bestDistance = tempBestDistance;
	}
	return bestIndex;
}

- (int) indexOfPointEqualTo:(cv::Point2f &)position inCvPoints:(std::vector<cv::Point2f> &)points
{
	for (int i = 0; i < (int)points.size(); i++) {
		if (position.x == points[i].x && position.y == points[i].y) return i;
	}
	return [self indexOfNearestPointTo:position inCvPoints:points bestDistance:nil];
}

- (std::vector<cv::Point2f>) buildLineFromPoints:(std::vector<cv::Point2f> &)allPoints byExtending:(int)startPointInd inDirectionOf:(int)dirPointInd
{
	// Maximum distance from the next point to its candidate position, as a fraction of the distance between previous points.
	const double distanceTolerance =  [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"chessboardDetectionCandidateDistanceTolerance"] doubleValue];
	
	// set the minimum pixels from the edge of the image for a detected corner to count; prevents non-corner detections right on the edge of the image
	const float minDistanceFromEdge = 4.0;
	const float maxX = (float) [self.videoClip clipWidth] - minDistanceFromEdge;
	const float maxY = (float) [self.videoClip clipHeight] - minDistanceFromEdge;
	const float minX = minDistanceFromEdge;
	const float minY = minDistanceFromEdge;
	
	std::vector<cv::Point2f>linePoints;
		
	linePoints.push_back(allPoints[startPointInd]);
	linePoints.push_back(allPoints[dirPointInd]);
	
	double xdiff,ydiff,xcandidate,ycandidate,bestDistance,maxBestDistance;
	int nextIndex;
	int prevIndex = dirPointInd;
	int i = 2;
	bool foundNext = true;
	while (foundNext) {
		xdiff = linePoints[i-1].x - linePoints[i-2].x;
		ydiff = linePoints[i-1].y - linePoints[i-2].y;
		maxBestDistance = distanceTolerance * sqrt(xdiff*xdiff + ydiff*ydiff);
		xcandidate = linePoints[i-1].x + xdiff;
		ycandidate = linePoints[i-1].y + ydiff;
		nextIndex = [self indexOfNearestPointTo:cv::Point2f(xcandidate,ycandidate) inCvPoints:allPoints bestDistance:&bestDistance];
		if (minX < allPoints[nextIndex].x && allPoints[nextIndex].x < maxX && minY < allPoints[nextIndex].y && allPoints[nextIndex].y < maxY) { // check that point isn't too close to edge of screen
			// We add a new point if the closest point to the candidate next point position is within an appropriate distance of it, and is not the previous point itself.
			if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
				foundNext = true;
				linePoints.push_back(allPoints[nextIndex]);
				prevIndex = nextIndex;
				i++;    // After this loop breaks, 'i' will be 1 greater than the highest index of the highest actual point, equal to the total # of points
			} else {    // No point was found in the expected position of a next point... see if we can find one by jumping a bad point.  Otherwise, end of the line.
				xcandidate = linePoints[i-1].x + (2.0 * xdiff);
				ycandidate = linePoints[i-1].y + (2.0 * ydiff);
				nextIndex = [self indexOfNearestPointTo:cv::Point2f(xcandidate,ycandidate) inCvPoints:allPoints bestDistance:&bestDistance];
				if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
					foundNext = true;
					linePoints.push_back(allPoints[nextIndex]);
					prevIndex = nextIndex;
					i++;    // After this loop breaks, i will be 1 greater than the highest index of the highest actual point, equal to the total # of points
				} else {
					foundNext = false;
				}
			}
		} else { // stop if point was too close to edge of screen
			//            NSLog(@"End of line -- point found was too close to edge of screen.");
			foundNext = false;
		}
	}
	// Reverse the elements of linePoints.  Before this, indices of the line points go from 0 to i-1
	std::vector<cv::Point2f>reversedFirstHalf;
	for (int j=0; j<i; j++) {
		reversedFirstHalf.push_back(linePoints[(i-1) - j]);
	}
	for (int k=0; k<i; k++) {
		linePoints[k] = reversedFirstHalf[k];
	}
	// Now begin building the second half of the line from the middle, adding to the reversed first half so it automatically goes the other direction.
	foundNext = true;
	while (foundNext) {
		xdiff = linePoints[i-1].x - linePoints[i-2].x;
		ydiff = linePoints[i-1].y - linePoints[i-2].y;
		maxBestDistance = distanceTolerance * sqrt(xdiff*xdiff + ydiff*ydiff);
		xcandidate = linePoints[i-1].x + xdiff;
		ycandidate = linePoints[i-1].y + ydiff;
		nextIndex = [self indexOfNearestPointTo:cv::Point2f(xcandidate,ycandidate) inCvPoints:allPoints bestDistance:&bestDistance];
		if (minX < allPoints[nextIndex].x && allPoints[nextIndex].x < maxX && minY < allPoints[nextIndex].y && allPoints[nextIndex].y < maxY) { // check that point isn't too close to edge of screen
			if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
				foundNext = true;
				linePoints.push_back(allPoints[nextIndex]);
				prevIndex = nextIndex;
				i++;
			} else {
				xcandidate = linePoints[i-1].x + (2.0 * xdiff);
				ycandidate = linePoints[i-1].y + (2.0 * ydiff);
				nextIndex = [self indexOfNearestPointTo:cv::Point2f(xcandidate,ycandidate) inCvPoints:allPoints bestDistance:&bestDistance];
				if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
					foundNext = true;
					linePoints.push_back(allPoints[nextIndex]);
					prevIndex = nextIndex;
					i++;    // After this loop breaks, i will be 1 greater than the highest index of the highest actual point, equal to the total # of points
				} else {
					foundNext = false;
				}
			}
		} else {    // stop if point was too close to edge of screen
			foundNext = false;
		}
	}
	return linePoints; // return value i is the length of the line
}

- (void) removeAllPlumblines
{
	for (VSDistortionLine *line in self.distortionLines) [[self managedObjectContext] deleteObject:line];
	[[self managedObjectContext] processPendingChanges];
	[self.videoClip.windowController refreshOverlay];
}


- (void) autodetectChessboardPlumblines
{
	// Dispatch to whichever detection method the user has selected. Both methods remain in the build
	// so they can be run against the same frame and compared; the Legacy method stays the default
	// until the Lattice method has been shown to match or beat it across a corpus of real frames.
	NSString *method = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"plumblineDetectionMethod"];
	if ([method isEqualToString:@"Lattice"]) {
		[self autodetectChessboardPlumblinesLattice];
	} else {
		[self autodetectChessboardPlumblinesLegacy];
	}
}

// Shortest run of lattice corners worth emitting as a plumbline. Short lines carry little
// information about distortion but count equally in the orthogonal-regression cost, so the
// floor is a little above the legacy method's.
static const int kMinPlumblinePoints = 6;

- (void) autodetectChessboardPlumblinesLattice
{
	// Stage A only so far: detect the corners and show them. Lattice basis estimation and grid
	// assembly come next; until they land this method deliberately creates no plumblines, so that
	// the corner detection can be judged on its own against the legacy method's point cloud.

	// Make sure the user can see the detected points rather than wondering whether anything happened.
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithBool:TRUE] forKey:@"showDistortionOverlay"];

	CGImageRef videoFrameCG = [self.videoClip.project.document stillCGImageFromVSVideoClip:self.videoClip atMasterTime:[self.videoClip.project.document currentMasterTime] showOverlay:FALSE];
	// Do NOT release videoFrameCG; see the ownership note in autodetectChessboardPlumblinesLegacy.
	cv::Mat videoFrameImage;
	CGImageToMat(videoFrameCG, videoFrameImage); // included from <opencv2/imgcodecs/macosx.h>
	cv::Mat gray;
	if (videoFrameImage.channels() == 1) {
		gray = videoFrameImage;
	} else {
		cvtColor(videoFrameImage, gray, cv::COLOR_BGR2GRAY);
	}

	vidsync::CornerDetectionResult detection = vidsync::detectChessboardCorners(gray);

	// If the user has drawn exactly one line with exactly two points, treat it as a hint about
	// where the board is and which way its grid runs, overriding the automatic search. This is
	// the same seeding convention the legacy method uses, and it is the escape hatch for the
	// frames where no automatic board-finder will pick the right region.
	// Unlike the legacy method this does not delete the seed line after reading it: nothing is
	// produced yet, so consuming the hint would just force the user to redraw it every run. The
	// deletion belongs with the code that creates plumblines.
	vidsync::LatticeSeedHint hint;
	if ([self.distortionLines count] == 1 && [[[self.distortionLines anyObject] distortionPoints] count] == 2) {
		NSArray *seedPoints = [[[self.distortionLines anyObject] distortionPoints] allObjects];
		VSDistortionPoint *seedPoint1 = [seedPoints objectAtIndex:0];
		VSDistortionPoint *seedPoint2 = [seedPoints objectAtIndex:1];
		// Seed points are stored in VidSync coordinates; the detector works in OpenCV's.
		hint.provided = true;
		hint.from = cv::Point2f([seedPoint1.screenX floatValue], (float)[self.videoClip clipHeight] - [seedPoint1.screenY floatValue]);
		hint.to = cv::Point2f([seedPoint2.screenX floatValue], (float)[self.videoClip clipHeight] - [seedPoint2.screenY floatValue]);
	}

	vidsync::SeedLattice seed = vidsync::findSeedLattice(detection.corners, detection.estimatedCellSize,
														 cv::Size(gray.cols, gray.rows), hint);

	vidsync::GrownLattice lattice;
	vidsync::RefinementResult refinement;
	std::vector<vidsync::Plumbline> plumblines;
	if (seed.valid) {
		lattice = vidsync::growLattice(detection.corners, seed, cv::Size(gray.cols, gray.rows));
		if (lattice.valid) {
			// Refinement can append corners it finds in the image, so it works on the detection's
			// own corner vector and the lattice it returns indexes into the enlarged one.
			refinement = vidsync::refineLattice(detection.corners, lattice, gray);
			lattice = refinement.lattice;
			plumblines = vidsync::extractPlumblines(detection.corners, lattice, kMinPlumblinePoints);
		}
	}

	// Show whatever we got furthest with, so a failure always leaves something to diagnose from.
	// OpenCV puts the origin at the top left; VidSync puts it at the bottom left.
	const double clipHeight = [self.videoClip clipHeight];
	self.autodetectedPoints = [NSMutableSet setWithCapacity:detection.corners.size()];
	if (lattice.valid) {
		for (size_t i = 0; i < lattice.cornerIndex.size(); i++) {
			const cv::Point2f p = detection.corners[lattice.cornerIndex[i]].position;
			[self.autodetectedPoints addObject:[NSValue valueWithPoint:NSMakePoint(p.x, clipHeight - p.y)]];
		}
	} else if (seed.valid) {
		for (size_t i = 0; i < seed.cornerIndex.size(); i++) {
			const cv::Point2f p = detection.corners[seed.cornerIndex[i]].position;
			[self.autodetectedPoints addObject:[NSValue valueWithPoint:NSMakePoint(p.x, clipHeight - p.y)]];
		}
	} else {
		for (size_t i = 0; i < detection.corners.size(); i++) {
			const cv::Point2f p = detection.corners[i].position;
			[self.autodetectedPoints addObject:[NSValue valueWithPoint:NSMakePoint(p.x, clipHeight - p.y)]];
		}
	}

	// Now that plumblines are actually being produced, the two-point seed line has served its
	// purpose and would otherwise be left behind as a stray two-point line in the fit.
	if (hint.provided && !plumblines.empty()) {
		[[self managedObjectContext] deleteObject:[self.distortionLines anyObject]];
	}

	NSUInteger pointsCreated = 0;
	for (size_t i = 0; i < plumblines.size(); i++) {
		std::vector<cv::Point2f> flipped;
		flipped.reserve(plumblines[i].points.size());
		for (size_t k = 0; k < plumblines[i].points.size(); k++) {
			flipped.push_back(cv::Point2f(plumblines[i].points[k].x,
										  (float)clipHeight - plumblines[i].points[k].y));
		}
		pointsCreated += flipped.size();
		[self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithPoints:&flipped];
	}

	// Keep the lattice diagonals aside so the next distortion solve can be checked against
	// directions it was not fitted to. Cleared when no lattice was built, so a stale set from a
	// previous run cannot be reported against fresh parameters.
	if (lattice.valid) {
		std::vector<std::vector<cv::Point2f> > diagonals = vidsync::extractDiagonalRuns(detection.corners, lattice, kMinPlumblinePoints);
		NSMutableArray *stored = [NSMutableArray arrayWithCapacity:diagonals.size()];
		for (size_t i = 0; i < diagonals.size(); i++) {
			NSMutableArray *run = [NSMutableArray arrayWithCapacity:diagonals[i].size()];
			for (size_t k = 0; k < diagonals[i].size(); k++) {
				[run addObject:[NSValue valueWithPoint:NSMakePoint(diagonals[i][k].x, clipHeight - diagonals[i][k].y)]];
			}
			[stored addObject:run];
		}
		self.holdOutDiagonals = stored;
	} else {
		self.holdOutDiagonals = nil;
	}

	if (!plumblines.empty()) self.videoClip.project.distortionDisplayMode = @"Uncorrected";
	[self.videoClip.windowController refreshOverlay];

	NSAlert *alert = [[NSAlert alloc] init];
	if (!plumblines.empty()) {
		[alert setMessageText:[NSString stringWithFormat:@"Created %lu plumblines from %lu corners.", (unsigned long)plumblines.size(), (unsigned long)pointsCreated]];
		[alert setAlertStyle:NSAlertStyleInformational];
	} else if (seed.valid) {
		[alert setMessageText:@"Found the board but could not build plumblines from it."];
		[alert setAlertStyle:NSAlertStyleWarning];
	} else {
		[alert setMessageText:[NSString stringWithFormat:@"No lattice found among %lu corners.", (unsigned long)detection.corners.size()]];
		[alert setAlertStyle:NSAlertStyleWarning];
	}
	[alert setInformativeText:[NSString stringWithFormat:@"%@\n\n%@\n\n%@\n\nCorner detection: %d saddle candidates, %d rejected by the cheap appearance pass, %lu accepted.%@\n\nPlumblines are appended to any already present, so you can reposition the board and run this again at another timecode to cover more of the frame.",
							   [NSString stringWithUTF8String:seed.status.c_str()],
							   lattice.valid ? [NSString stringWithUTF8String:lattice.status.c_str()] : @"Grid growth did not run.",
							   refinement.passes > 0 ? [NSString stringWithUTF8String:refinement.status.c_str()] : @"Refinement did not run.",
							   detection.saddleCandidateCount,
							   detection.prefilterRejectedCount,
							   (unsigned long)detection.corners.size(),
							   hint.provided ? @"\n\nUsed your two-point line as a seed hint, and removed it after use." : @""]];
	[alert addButtonWithTitle:@"Ok"];
	[alert runModal];
}

- (void) autodetectChessboardPlumblinesLegacy
{
	// Make sure user can see whatever's being autodetected, and doesn't think no plumblines were found when actually just the display is turned off.
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithBool:TRUE] forKey:@"showDistortionOverlay"];
	
	const int maxNumCorners =  [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"chessboardDetectionMaxNumCorners"] intValue];
	// Minimum allowed Euclidean distance between detected corners, in pixels.
	const double minDistance =  [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"chessboardDetectionMinDistance"] doubleValue];
	// If the quality score of the best corner is 1500 and qualityLevel=0.01, all corners scoring below 1500*0.01 = 15 are ignored
	const double qualityLevel =  [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"chessboardDetectionQualityLevel"] doubleValue];
	const int minLineLength = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"chessboardDetectionMinLineLength"] intValue];
	const int cornerSubPixWindowSize = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"chessboardDetectionCornerSubPixwindowSize"] intValue];
	// const bool showDirectOpenCVOutputWindow = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showDirectOpenCVOutputWindow"] boolValue];
	
	// I'm not using these three parameters below, which would have the feature finder use cvCornerHarris instead of cvCornerMinEigenVal for corner detection.
	// I'm sticking with the default (cvCornerMinEigenVal) because it works just fine.  I couldn't find much info on the difference between the two, but I found one
	// blog post in which the Harris method didn't pick up as my corners as the default method:  http://fahmifahim.wordpress.com/2010/10/22/opencv-corner-detection/
	const int blockSize = 3;
	bool useHarris = false;
	const double harrisK = 0.04;
		
	CGImageRef videoFrameCG = [self.videoClip.project.document stillCGImageFromVSVideoClip:self.videoClip atMasterTime:[self.videoClip.project.document currentMasterTime] showOverlay:FALSE];
	cv::Mat videoFrameImage;
	CGImageToMat(videoFrameCG, videoFrameImage); // included from <opencv2/imgcodecs/macosx.h>
	// Do NOT release videoFrameCG. stillCGImageFromVSVideoClip: returns the result of
	// -[NSImage CGImageForProposedRect:context:hints:], which follows the Get Rule and does not
	// transfer ownership; the image is owned by the NSImage's backing NSCGImageSnapshotRep, which
	// releases it when that autoreleased NSImage deallocs. Releasing here freed the image early and
	// crashed later in -[NSCGImageSnapshotRep dealloc] on the next autorelease pool drain. The
	// Create reference from copyCGImageAtTime: is already balanced inside stillCGImageFromVSVideoClip:.
	videoFrameImage.reshape(1);	// convert to single-channel for feature tracking
	cvtColor(videoFrameImage, videoFrameImage, cv::COLOR_BGR2GRAY);
	
	std::vector<cv::Point2f> foundCorners;
		
	// Find the corner positions -- they'll be pretty much the only good "features to track" when the chessboard takes up the entire screen.
	cv::goodFeaturesToTrack(videoFrameImage, foundCorners, maxNumCorners, qualityLevel, minDistance, cv::noArray(), blockSize, useHarris, harrisK);
	
	// Running cvFindCornerSubPix with a high window size like (15,15) corrected some severe mislocations around one of my squares that (5,5) did not.
	cv::cornerSubPix(videoFrameImage, foundCorners, cv::Size(cornerSubPixWindowSize,cornerSubPixWindowSize), cv::Size(-1,-1), cv::TermCriteria(cv::TermCriteria::EPS, 50, 0.01));

	// Since OpenCV flips the y-coordinate (from top left instead of bottom left), flip it back here right away so it doesn't confuse later calculations.
	for (int i = 0; i < foundCorners.size(); i++) foundCorners[i].y = [self.videoClip clipHeight] - foundCorners[i].y;
		
	// Store the autodetected corners for temporarly display overlaying the main window.
	
	self.autodetectedPoints = [NSMutableSet setWithCapacity:foundCorners.size()];
	for (int i = 0; i < foundCorners.size(); i++) {
		[self.autodetectedPoints addObject:[NSValue valueWithPoint:NSMakePoint(foundCorners[i].x,foundCorners[i].y)]];
	}
	if (foundCorners.empty()) return;  // no corners detected; nothing to build lines from

	// Build the first distortion line
	int centerIndex, nextIndex;
	// Manually seed the start of the line creation algorithm if the user has entered exactly one line with exactly two points as the seed.
	if ([self.distortionLines count] == 1 && [[[self.distortionLines anyObject] distortionPoints] count] == 2) {
		VSDistortionLine *seedLine = [self.distortionLines anyObject];
		NSArray *seedPoints = [[seedLine distortionPoints] allObjects];
		VSDistortionPoint *seedPoint1 = [seedPoints objectAtIndex:0];
		VSDistortionPoint *seedPoint2 = [seedPoints objectAtIndex:1];
		cv::Point2f seedPointCv1 = cv::Point2f([seedPoint1.screenX doubleValue],[seedPoint1.screenY doubleValue]);
		cv::Point2f seedPointCv2 = cv::Point2f([seedPoint2.screenX doubleValue],[seedPoint2.screenY doubleValue]);
		centerIndex = [self indexOfNearestPointTo:seedPointCv1 inCvPoints:foundCorners bestDistance:nil];
		nextIndex = [self indexOfNearestPointTo:seedPointCv2 inCvPoints:foundCorners bestDistance:nil];
		[[self managedObjectContext] deleteObject:seedLine];    // Delete the seed after using it
	} else {    // Otherwise, start the line creation algorithm from the center point to the nearest other point
		cv::Point2f centroid = [self centroidOfCvPoints:foundCorners]; // geometrical center of all the detected point (NOT the centermost point)
		centerIndex = [self indexOfNearestPointTo:centroid inCvPoints:foundCorners bestDistance:nil];
		nextIndex = [self indexOfNearestPointTo:foundCorners[centerIndex] inCvPoints:foundCorners bestDistance:nil];
	}
	std::vector<cv::Point2f> firstLine = [self buildLineFromPoints:foundCorners byExtending:centerIndex inDirectionOf:nextIndex];
	if (firstLine.size() < 2) return;  // too few aligned corners to build a valid grid line

	// I'm not adding the first line to the object model here, because it would be duplicated later when crossing the crossing lines, and it's easier to just not add it here
	// than to skip over adding it there.
	
	// After calculating the first line, now go all up and down it calculating other lines.
	
	cv::Point2f vec, newDir, rotatedTargetGuess;
	int baseIndex = 0;
	// This whole block below is a copy of the loop below it, but with the line order switched, just to avoid skipping the first crossing line on the end.
	vec = cv::Point2f(firstLine[0].x - firstLine[1].x,firstLine[0].y - firstLine[1].y);
	newDir = cv::Point2f(-vec.y,vec.x);
	rotatedTargetGuess = cv::Point2f(firstLine[0].x + newDir.x, firstLine[0].y + newDir.y);
	nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inCvPoints:foundCorners bestDistance:nil];
	baseIndex = [self indexOfPointEqualTo:firstLine[0] inCvPoints:foundCorners];
	std::vector<cv::Point2f> crossingLine = [self buildLineFromPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
	if (crossingLine.size() > minLineLength) {
		[self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithPoints:&crossingLine];
	}
	
	// Now, this loop does the remainder of the line.
	
	std::vector<cv::Point2f> midCrossingLine;
	for (int i=1; i<firstLine.size(); i++) {
		vec = cv::Point2f(firstLine[i].x - firstLine[i-1].x,firstLine[i].y - firstLine[i-1].y);
		newDir = cv::Point2f(-vec.y,vec.x);
		rotatedTargetGuess = cv::Point2f(firstLine[i].x + newDir.x, firstLine[i].y + newDir.y);
		nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inCvPoints:foundCorners bestDistance:nil];
		baseIndex = [self indexOfPointEqualTo:firstLine[i] inCvPoints:foundCorners];
		std::vector<cv::Point2f> crossingLine = [self buildLineFromPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
		if (crossingLine.size() > minLineLength) {
			[self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithPoints:&crossingLine];
		}
		if (i == floor(firstLine.size()/2.0)) {   // When we get to the middle, store a copy of the middle crossing line to use for generating the ones crossing the crossing lines
			// This used to also add crossingLine to the model a second time, duplicating the middle line in
			// the distortion fit (and sneaking it in even when it was shorter than minLineLength). It also
			// rebuilt an identical line instead of copying the one just computed.
			midCrossingLine = crossingLine;
		}
	}
	
	// Now build the set of crossing lines for the middle crossing line, completing the grid.  We start with the whole block and the indices switched, to catch the first line.
	if (midCrossingLine.size() < 2) return;  // midCrossingLine was not populated or too short; guard against empty vector access

	vec = cv::Point2f(midCrossingLine[0].x - midCrossingLine[1].x,midCrossingLine[0].y - midCrossingLine[1].y);
	newDir = cv::Point2f(-vec.y,vec.x);
	rotatedTargetGuess = cv::Point2f(midCrossingLine[0].x + newDir.x, midCrossingLine[0].y + newDir.y);
	nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inCvPoints:foundCorners bestDistance:nil];
	baseIndex = [self indexOfPointEqualTo:midCrossingLine[0] inCvPoints:foundCorners];
	crossingLine = [self buildLineFromPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
	if (crossingLine.size() > minLineLength) {
		[self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithPoints:&crossingLine];
	}
	
	for (int i=1; i<midCrossingLine.size(); i++) {
		vec = cv::Point2f(midCrossingLine[i].x - midCrossingLine[i-1].x,midCrossingLine[i].y - midCrossingLine[i-1].y);
		newDir = cv::Point2f(-vec.y,vec.x);
		rotatedTargetGuess = cv::Point2f(midCrossingLine[i].x + newDir.x, midCrossingLine[i].y + newDir.y);
		nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inCvPoints:foundCorners bestDistance:nil];
		baseIndex = [self indexOfPointEqualTo:midCrossingLine[i] inCvPoints:foundCorners];
		crossingLine = [self buildLineFromPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
		if (crossingLine.size() > minLineLength) {
			[self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithPoints:&crossingLine];
		}
	}

	self.videoClip.project.distortionDisplayMode = @"Uncorrected";
	[self.videoClip.windowController refreshOverlay];
}

- (NSPoint) snapToFeatureNearestToClick:(NSPoint)clickedPoint;
{
	const int maxNumCorners =  1;
	const double minDistance =  1920.0; // Minimum Euclidean distance between detected corners
	const double qualityLevel =  0.999999;
	// New parameters for this function
	const int cornerSubPixWindowSize = 10;   // was 3 originally; experimenting with bigger values
	const double snapSearchHalfWidth = (double) cornerSubPixWindowSize + 3.0;   // Search image any smaller than this and OpenCV gives errors in subpixel refinement
	
	CGImageRef videoFrameCG = [self.videoClip.project.document stillCGImageFromVSVideoClip:self.videoClip atMasterTime:[self.videoClip.project.document currentMasterTime] showOverlay:FALSE];
	
	NSPoint snapSearchOrigin = NSMakePoint(clickedPoint.x - snapSearchHalfWidth,([self.videoClip clipHeight] - clickedPoint.y) - snapSearchHalfWidth);
	CGRect snapSearchRect = CGRectMake(snapSearchOrigin.x, snapSearchOrigin.y, snapSearchHalfWidth*2, snapSearchHalfWidth*2);
	
	CGImageRef localVideoFrameCG = CGImageCreateWithImageInRect(videoFrameCG,snapSearchRect);
	
	cv::Mat videoFrameImage;
	CGImageToMat(localVideoFrameCG, videoFrameImage); // included from <opencv2/imgcodecs/macosx.h>
	CGImageRelease(localVideoFrameCG);
	
	videoFrameImage.reshape(1);
	cvtColor(videoFrameImage, videoFrameImage, cv::COLOR_BGR2GRAY);
	
	// DEPRECATED cv::Point2f *foundCorners = (cv::Point2f*)malloc((maxNumCorners + 1) * sizeof(cv::Point2f));
	std::vector<cv::Point2f> foundCornersVec;
	
	// cv::Exception: OpenCV(4.5.1-dev) /Users/Jason/Downloads/opencv-master/modules/imgproc/src/corner.cpp:254: error: (-215:Assertion failed) src.type() == CV_8UC1 || src.type() == CV_32FC1 in function 'cornerEigenValsVecs'
	
	cv::goodFeaturesToTrack(videoFrameImage, foundCornersVec, maxNumCorners, qualityLevel, minDistance, cv::noArray(), 3, false, 0.04);
	
	//	IplImage *videoFrameIpl = (IplImage *) [UtilityFunctions CreateIplImageFromCGImage:localVideoFrameCG];
	//	CFRelease(localVideoFrameCG);
	//	IplImage* videoFrameSingleChannelIpl = cvCreateImage(cvGetSize(videoFrameIpl), videoFrameIpl->depth, 1);
	//	cvSetImageCOI(videoFrameIpl, 1);
	//	cvCopy(videoFrameIpl, videoFrameSingleChannelIpl);
	//
	//	int numCorners = maxNumCorners;  // Max # of corners to find.  On return, it is replaced by the # actually found.
	//	cv::Point2f *foundCorners = (cv::Point2f*)malloc((maxNumCorners + 1) * sizeof(cv::Point2f));
	//	IplImage *eigImage = cvCreateImage(cvGetSize(videoFrameIpl),IPL_DEPTH_32F, 1);
	//	IplImage *tempImage = cvCreateImage(cvGetSize(videoFrameIpl),IPL_DEPTH_32F, 1);
	//
	//	// Find the corner positions -- they'll be pretty much the only good "features to track" when the chessboard takes up the entire screen.
	//	cvGoodFeaturesToTrack(videoFrameSingleChannelIpl, eigImage, tempImage, foundCorners, &numCorners, qualityLevel, minDistance, NULL, 3, 0, 0.04);
	//
	//	// Running cvFindCornerSubPix with a high window size like (15,15) corrected some severe mislocations around one of my squares that (5,5) did not.
	// But (15,15) has some trouble getting drawn off to other things. So trying (10, 10).
	// Only run the subpixel refinement if we're not right on the edge of the image; otherwise it crashes the program from an array size mismatch.
	
	if (foundCornersVec.size() > 0 && clickedPoint.x > snapSearchHalfWidth && clickedPoint.y > snapSearchHalfWidth && clickedPoint.x < ([self.videoClip clipWidth] - snapSearchHalfWidth) && clickedPoint.y < ([self.videoClip clipWidth] - snapSearchHalfWidth)) {
		// cvFindCornerSubPix(videoFrameSingleChannelIpl, foundCorners, numCorners, cvSize(cornerSubPixWindowSize,cornerSubPixWindowSize), cvSize(-1,-1), cvTermCriteria( CV_TERMCRIT_ITER | CV_TERMCRIT_EPS, 20, 0.01 ));
		cv::cornerSubPix(videoFrameImage, foundCornersVec, cv::Size(cornerSubPixWindowSize,cornerSubPixWindowSize), cv::Size(-1,-1), cv::TermCriteria(cv::TermCriteria::EPS, 50, 0.01));
	}
	if (foundCornersVec.size() == 0) return clickedPoint;  // no corner found in search area; return the original click point unmodified
	NSPoint snappedPoint = NSMakePoint(snapSearchOrigin.x + foundCornersVec[0].x,([self.videoClip clipHeight] - (snapSearchOrigin.y + foundCornersVec[0].y)));
	return snappedPoint;
}

// Measures how straight the held-back lattice diagonals come out under the parameters just
// solved. Those diagonals pass through the same corners as the rows and columns, but the
// constraint that they in particular are collinear was never optimized against, so this
// reports whether the model straightens a direction it was not fitted to.
//
// It is not a true out-of-sample test, since the corners themselves were used; what is held
// out is the constraint, not the data. So it will catch a model that has bent the image in a
// way that keeps rows and columns straight while distorting other directions, which the fit's
// own residual structurally cannot see, but not overfitting to the corner positions.
//
// Cost is negligible: one pass with the final parameters, where the solver has already done
// thousands. undistortPoint is closed form, unlike redistortPoint, so nothing iterates here.
- (void) measureHoldOutStraightness
{
	if ([self.holdOutDiagonals count] == 0) return;
	double totalSquaredResidual = 0.0;
	NSUInteger totalPoints = 0;
	for (NSArray *run in self.holdOutDiagonals) {
		const NSUInteger count = [run count];
		if (count < 3) continue;   // two points are collinear by definition
		NSPoint *undistorted = (NSPoint *) malloc(count * sizeof(NSPoint));
		for (NSUInteger k = 0; k < count; k++) {
			undistorted[k] = [self undistortPoint:[[run objectAtIndex:k] pointValue]];
		}
		totalSquaredResidual += orthogonalRegressionLineCostFunction(undistorted, count);
		totalPoints += count;
		free(undistorted);
	}
	if (totalPoints == 0) return;
	const double residualPerPoint = sqrt(totalSquaredResidual / (double)totalPoints);
	// Written through the entity rather than as a property, so the app still runs against a
	// document model that predates this attribute; the value is simply not recorded then.
	// The displayed value is read through -distortionHoldOutResidualOrNil rather than the
	// attribute, so that it survives a document model without the attribute. That accessor is a
	// plain method and generates no change notification of its own, so one is sent by hand or
	// the bound field would keep showing the previous calibration's figure.
	[self willChangeValueForKey:@"distortionHoldOutResidualOrNil"];
	if ([[[self entity] attributesByName] objectForKey:@"distortionHoldOutResidual"] != nil) {
		[self setValue:[NSNumber numberWithDouble:residualPerPoint] forKey:@"distortionHoldOutResidual"];
	}
	[self didChangeValueForKey:@"distortionHoldOutResidualOrNil"];
}

- (NSNumber *) distortionHoldOutResidualOrNil
{
	if ([[[self entity] attributesByName] objectForKey:@"distortionHoldOutResidual"] == nil) return nil;
	return [self valueForKey:@"distortionHoldOutResidual"];
}

// Bounds for judging whether a solved distortion model is a usable correction or a mathematical artifact.
// The plumbline cost function is degenerate: because it only asks that certain runs of points come out
// collinear, and says nothing about scale, it has minima that shrink the whole image toward the distortion
// centre or blow it up, either of which makes every line trivially straight. Fitting synthetic boards at
// 0.30 px corner noise found such solutions reaching a residual of 0.0025 px per point, far below the noise
// floor, with the image collapsed to under a pixel across. Nelder-Mead started from all-zero parameters has
// not been observed to find them, so this is a guard against a latent hazard rather than a known failure --
// but nothing prevented one from being stored silently, and a more aggressive optimizer would find them.
//
// The determinant of the undistortion map's Jacobian is the discriminating measure. Over the region the
// plumblines actually cover it came out within [0.85, 1.6] for every good fit measured, and went negative --
// meaning the map folds the image over itself and is not invertible -- for every collapsed or exploded one.
static const double kMinAcceptableScaleRatio = 0.25;   // good fits measured 0.99 to 1.12; pathological ones 0.002, 8, 43, 1.6e6
static const double kMaxAcceptableScaleRatio = 4.0;    // generous enough for a genuine fisheye, whose edge correction can approach 2.7x

- (NSString *) reasonToRejectSolvedDistortion:(const double *)solved overPlumblineBox:(NSRect)box warning:(NSString **)outWarning
{
	if (outWarning != NULL) *outWarning = nil;
	static const char *paramNames[13] = {"center X","center Y","K1","K2","K3","K4","K5","K6","K7","P1","P2","P3","P4"};
	for (int i = 0; i < 13; i++) {
		if (!isfinite(solved[i])) return [NSString stringWithFormat:@"The solver produced a value that is not a finite number for %s.", paramNames[i]];
	}
	const double x0 = solved[0];
	const double y0 = solved[1];

	// Sample the map over the region the plumblines actually constrain. Everything outside that region is
	// extrapolation by a degree-7 polynomial, so it is checked separately and only warned about.
	const int gridSteps = 24;
	double minDeterminantInBox = INFINITY;
	double totalUndistortedRadius = 0.0;
	double totalDistortedRadius = 0.0;
	for (int i = 0; i <= gridSteps; i++) {
		for (int j = 0; j <= gridSteps; j++) {
			const double gx = NSMinX(box) + NSWidth(box) * ((double) i / gridSteps);
			const double gy = NSMinY(box) + NSHeight(box) * ((double) j / gridSteps);
			double J[4];
			undistortionJacobian(gx - x0, gy - y0, solved[2], solved[3], solved[4], solved[5], solved[6], solved[7], solved[8], solved[9], solved[10], solved[11], solved[12], J);
			const double determinant = J[0]*J[3] - J[1]*J[2];
			if (!isfinite(determinant)) return @"The correction's Jacobian determinant is not a finite number, so the model is not usable.";
			if (determinant < minDeterminantInBox) minDeterminantInBox = determinant;
			NSPoint gridPoint = NSMakePoint(gx, gy);
			NSPoint undistorted = undistortPoint(&gridPoint, x0, y0, solved[2], solved[3], solved[4], solved[5], solved[6], solved[7], solved[8], solved[9], solved[10], solved[11], solved[12]);
			totalUndistortedRadius += hypot(undistorted.x - x0, undistorted.y - y0);
			totalDistortedRadius += hypot(gx - x0, gy - y0);
		}
	}

	if (minDeterminantInBox <= 0.0) {
		return [NSString stringWithFormat:@"The correction folds the image over itself within the area your plumblines cover, so it is not a valid, reversible mapping. The smallest Jacobian determinant there is %1.3g, and it must stay above zero.", minDeterminantInBox];
	}
	if (totalDistortedRadius > 0.0) {
		const double scaleRatio = totalUndistortedRadius / totalDistortedRadius;
		if (scaleRatio < kMinAcceptableScaleRatio || scaleRatio > kMaxAcceptableScaleRatio) {
			return [NSString stringWithFormat:@"The correction rescales the image by a factor of %1.3g about the distortion centre, which is far outside the plausible range of %1.2g to %1.2g. Straightening the plumblines by shrinking or expanding the whole image is a known degenerate solution of this fit rather than a real lens correction.", scaleRatio, kMinAcceptableScaleRatio, kMaxAcceptableScaleRatio];
		}
	}

	// Now the same determinant check over the whole frame. A good fit can legitimately fail this while passing
	// the check above, because the high-order radial terms are unconstrained wherever the board never reached
	// and a degree-7 polynomial extrapolates badly. That does not invalidate the calibration, but it does mean
	// measurements in those areas run through a correction that is locally non-invertible, so say so.
	double minDeterminantInFrame = INFINITY;
	const double clipW = [self.videoClip clipWidth];
	const double clipH = [self.videoClip clipHeight];
	if (clipW > 0.0 && clipH > 0.0) {
		for (int i = 0; i <= gridSteps; i++) {
			for (int j = 0; j <= gridSteps; j++) {
				double J[4];
				undistortionJacobian(clipW * ((double) i / gridSteps) - x0, clipH * ((double) j / gridSteps) - y0, solved[2], solved[3], solved[4], solved[5], solved[6], solved[7], solved[8], solved[9], solved[10], solved[11], solved[12], J);
				const double determinant = J[0]*J[3] - J[1]*J[2];
				if (isfinite(determinant) && determinant < minDeterminantInFrame) minDeterminantInFrame = determinant;
			}
		}
		if (minDeterminantInFrame <= 0.0 && outWarning != NULL) {
			*outWarning = [NSString stringWithFormat:@"The correction is valid where your plumblines cover, but it folds over somewhere outside that area (smallest Jacobian determinant across the full frame is %1.3g). Measurements near the edges or corners your chessboard never reached are being corrected by extrapolation and may be unreliable. Adding plumblines that reach farther into the corners, at another timecode with the board repositioned, is the fix.", minDeterminantInFrame];
		}
	}
	return nil;
}

- (void) calculateDistortionCorrection
{
	NSArray *plumbLines = [self.distortionLines allObjects];
	NSSortDescriptor *pointIndexSortDescriptor = [[NSSortDescriptor alloc] initWithKey:@"index" ascending:YES];
	
	// Copy the plumblines from the Core Data storage into a structure that can be passed to the GNU Scientific Library multimin function
	
	Plumblines p;
	p.numLines = [plumbLines count];
	p.lines = (NSPoint **) malloc(p.numLines*sizeof(NSPoint *));
	p.lineLengths = (size_t *) malloc(p.numLines*sizeof(size_t *));
	// Total # of points on plumblines that can actually contribute a residual, for use calculating the average
	// remaining distortion per point. Runs shorter than three points are collinear by definition and contribute
	// nothing to the cost, so counting them would silently deflate the reported per-point residual by treating
	// them as perfectly straightened. This will double-count screen points used in both horizontal and vertical
	// lines. That is by design.
	int totalPointCount = 0;
	for (int i = 0; i < p.numLines; i++) {
		NSArray *pointsInLine = [[[[plumbLines objectAtIndex:i] distortionPoints] allObjects] sortedArrayUsingDescriptors:[NSArray arrayWithObject:pointIndexSortDescriptor]];
		p.lineLengths[i] = [pointsInLine count];
		if (p.lineLengths[i] >= 3) totalPointCount += p.lineLengths[i];
		p.lines[i] = (NSPoint *) malloc(p.lineLengths[i]*sizeof(NSPoint));
		for (int j = 0; j < p.lineLengths[i]; j++) p.lines[i][j] = NSMakePoint([[[pointsInLine objectAtIndex:j] screenX] floatValue],[[[pointsInLine objectAtIndex:j] screenY] floatValue]);
	}

	if (totalPointCount == 0) {   // with nothing to fit, the per-point residuals below would divide by zero
		for (int i = 0; i < p.numLines; i++) free(p.lines[i]);
		free(p.lines);
		free(p.lineLengths);
		[UtilityFunctions InformUser:@"There are no plumblines with enough points to fit a distortion model to. A plumbline needs at least three points to say anything about straightness. Detect or draw some longer plumblines first." withTitle:@"Nothing to fit"];
		return;
	}

	// Set up and perform the minimization
	
	const gsl_multimin_fminimizer_type *T = gsl_multimin_fminimizer_nmsimplex2;
	gsl_multimin_fminimizer *s = NULL;
	gsl_vector *ss, *x;
	gsl_multimin_function minex_func;
	
	size_t iter = 0;
	int status;
	double size;
	
	/* Starting point */
	int nparams = 13;
	x = gsl_vector_alloc(nparams);
	gsl_vector_set(x, 0, ([self.videoClip clipWidth]/2.0) / SCALE_FACTOR_X0);       // Initialize the distortion center to be
	gsl_vector_set(x, 1, ([self.videoClip clipHeight]/2.0) / SCALE_FACTOR_Y0);      // at the center of the screen as a first guess
	gsl_vector_set(x, 2, 0.0);  // Note: All the parameters need to have initial default values of zero
	gsl_vector_set(x, 3, 0.0);  // for the cost function's first iteration to be "no distortion correction at all"
	gsl_vector_set(x, 4, 0.0);  // and therefore provide an initial_cost_function_value corresponding to no correction
	gsl_vector_set(x, 5, 0.0);  // instead of an incorrect correction.
	gsl_vector_set(x, 6, 0.0);
	gsl_vector_set(x, 7, 0.0);
	gsl_vector_set(x, 8, 0.0);
	gsl_vector_set(x, 9, 0.0);
	gsl_vector_set(x, 10, 0.0);
	gsl_vector_set(x, 11, 0.0);
	gsl_vector_set(x, 12, 0.0);
	/* Set initial step sizes to 1 */
	ss = gsl_vector_alloc(nparams);            // ss is short for "step sizes"
	gsl_vector_set_all(ss,25);        // I was doing well with 0.25 before; now, 25 seems better.
	gsl_vector_set(ss, 0, 0.001);
	gsl_vector_set(ss, 1, 0.001);
	
	/* Initialize method and iterate */
	minex_func.n = nparams;                                     // Number of variables being adjusted for the minimization (distortion parameters)
	minex_func.f = orthogonalRegressionTotalCostFunction;       // The cost function to minimize (defined at the top of VSCalibration.mm)
	minex_func.params = &p;                                     // The *params argument of the cost function -- this holds the line data, not the distortion parameters.
	
	s = gsl_multimin_fminimizer_alloc(T, nparams);
	gsl_multimin_fminimizer_set(s, &minex_func, x, ss);
	
	// Evaluate the cost at the starting point, which is "no distortion correction at all" because every
	// coefficient starts at zero. This used to be read out of the simplex as s->fval on iteration 1, which is
	// the best vertex after one iteration has already improved on the start, so the reduction reported below
	// understated what the fit achieved. It also left the variable uninitialized if the very first iterate
	// returned an error status and broke out of the loop.
	double initial_cost_function_value = orthogonalRegressionTotalCostFunction(x, &p);
	double final_cost_function_value = 0.0;
	do {
		iter++;
		status = gsl_multimin_fminimizer_iterate(s);
		if (status) break;
		size = gsl_multimin_fminimizer_size(s);
		status = gsl_multimin_test_size(size, 1e-10);                        // Here we set the minimum characteristic size of the simplex as a possible stopping criterion, used 1e-10 before

		// Diagnostic code within the loop -- leave here, commented, in case the function ever gives me problems
		if (status == GSL_SUCCESS || status == GSL_CONTINUE)
		{
			/*
			 NSLog(@"Iteration step: %5d %.3f %.3f %10.5e %10.5e %10.5e %10.5e %10.5e %10.5e %10.5e %10.5e %10.5e %10.5e Cost Function f() = %7.10f size = %.20f\n",
			 (int) iter, gsl_vector_get(s->x, 0) * SCALE_FACTOR_X0, gsl_vector_get(s->x, 1) * SCALE_FACTOR_Y0,gsl_vector_get(s->x, 2) * SCALE_FACTOR_K1,
			 gsl_vector_get(s->x, 3) * SCALE_FACTOR_K2,gsl_vector_get(s->x, 4) * SCALE_FACTOR_K3,gsl_vector_get(s->x, 5) * SCALE_FACTOR_K4,gsl_vector_get(s->x, 6) * SCALE_FACTOR_K5,gsl_vector_get(s->x, 7) * SCALE_FACTOR_K6,gsl_vector_get(s->x, 8) * SCALE_FACTOR_K7,gsl_vector_get(s->x, 9) * SCALE_FACTOR_P1,gsl_vector_get(s->x, 10) * SCALE_FACTOR_P2,gsl_vector_get(s->x, 11) * SCALE_FACTOR_P3,s->fval,size);
			 */
			
		}
		
	} while (status == GSL_CONTINUE && iter < 10000);  // Generally takes less than 7,000 iterations but don't want to limit it unnecessarily
	// The min step size set above of 1e-10 is what actually stops the algorithm usually
	
	final_cost_function_value = s->fval;

	// Pull the solution out of the simplex, denormalized, so it can be judged before anything is committed.
	const double scaleFactors[13] = {SCALE_FACTOR_X0, SCALE_FACTOR_Y0, SCALE_FACTOR_K1, SCALE_FACTOR_K2, SCALE_FACTOR_K3, SCALE_FACTOR_K4, SCALE_FACTOR_K5, SCALE_FACTOR_K6, SCALE_FACTOR_K7, SCALE_FACTOR_P1, SCALE_FACTOR_P2, SCALE_FACTOR_P3, SCALE_FACTOR_P4};
	double solved[13];
	for (int i = 0; i < 13; i++) solved[i] = gsl_vector_get(s->x, i) * scaleFactors[i];

	// The bounding box of the plumbline points is the region the fit actually constrains, and the only region
	// over which the solved model can be judged rather than extrapolated. Computed here while p is still alive.
	NSRect plumblineBox = NSZeroRect;
	if (totalPointCount > 0) {
		double minX = INFINITY, minY = INFINITY, maxX = -INFINITY, maxY = -INFINITY;
		for (int i = 0; i < p.numLines; i++) {
			for (int j = 0; j < p.lineLengths[i]; j++) {
				minX = fmin(minX, p.lines[i][j].x);   maxX = fmax(maxX, p.lines[i][j].x);
				minY = fmin(minY, p.lines[i][j].y);   maxY = fmax(maxY, p.lines[i][j].y);
			}
		}
		plumblineBox = NSMakeRect(minX, minY, maxX - minX, maxY - minY);
	}

	NSString *extrapolationWarning = nil;
	NSString *rejectionReason = [self reasonToRejectSolvedDistortion:solved overPlumblineBox:plumblineBox warning:&extrapolationWarning];

	gsl_vector_free(x);
	gsl_vector_free(ss);
	gsl_multimin_fminimizer_free (s);

	for (int i = 0; i < p.numLines; i++) free(p.lines[i]);
	free(p.lines);
	free(p.lineLengths);

	if (rejectionReason != nil) {
		// Leave the previously stored parameters, whatever they were, untouched. Storing a solution that fails
		// these checks would silently corrupt every measurement made afterward, and the fit's own residual
		// cannot detect it: a collapsed map makes the plumblines straighter than the noise floor allows, and
		// even the held-out diagonal check passes, because collapsing straightens the diagonals too.
		NSAlert *alert = [NSAlert new];
		[alert setMessageText:@"Distortion correction rejected"];
		[alert setInformativeText:[NSString stringWithFormat:@"%@\n\nYour previous distortion parameters have been left in place. Try again with more plumblines, spread more widely over the frame, or with fewer radial terms.", rejectionReason]];
		[alert addButtonWithTitle:@"Ok"];
		[alert setAlertStyle:NSAlertStyleCritical];
		[alert runModal];
		return;
	}

	self.distortionCenterX = [NSNumber numberWithDouble:solved[0]];
	self.distortionCenterY = [NSNumber numberWithDouble:solved[1]];
	self.distortionK1 = [NSNumber numberWithDouble:solved[2]];
	self.distortionK2 = [NSNumber numberWithDouble:solved[3]];
	self.distortionK3 = [NSNumber numberWithDouble:solved[4]];
	self.distortionK4 = [NSNumber numberWithDouble:solved[5]];
	self.distortionK5 = [NSNumber numberWithDouble:solved[6]];
	self.distortionK6 = [NSNumber numberWithDouble:solved[7]];
	self.distortionK7 = [NSNumber numberWithDouble:solved[8]];
	self.distortionP1 = [NSNumber numberWithDouble:solved[9]];
	self.distortionP2 = [NSNumber numberWithDouble:solved[10]];
	self.distortionP3 = [NSNumber numberWithDouble:solved[11]];
	self.distortionP4 = [NSNumber numberWithDouble:solved[12]];
	/*
	 NSLog(@"Setting paramaters to (x0,y0) = (%1@,%1@), K1=%10@, K2=%10@, K3=%10@, K4=%10@, K5=%10@, K6=%10@, K7=%10@, P1=%10@, P2=%10@, P3=%10@, P4=%10@",self.distortionCenterX,self.distortionCenterY,self.distortionK1,self.distortionK2,self.distortionK3,self.distortionK4,self.distortionK5,self.distortionK6,self.distortionK7,self.distortionP1,self.distortionP2,self.distortionP3,self.distortionP4);
	 NSLog(@"Final cost function value for %@ after %lu interations (last step size %10.5e) is %1.3f\n\n",self.videoClip.clipName,iter,size,final_cost_function_value);
	 */
	double initial_RMS_error, final_RMS_error;
	initial_RMS_error = sqrt(initial_cost_function_value/totalPointCount);
	final_RMS_error=sqrt(final_cost_function_value/totalPointCount);
	self.distortionReductionAchieved = (initial_RMS_error > 0.0)
		? [NSNumber numberWithDouble:(initial_RMS_error - final_RMS_error) / initial_RMS_error]
		: [NSNumber numberWithDouble:0.0];  // guard: no initial error means 0% reduction
	self.distortionRemainingPerPoint = [NSNumber numberWithDouble:final_RMS_error];
	[self measureHoldOutStraightness];
	/*
	 NSLog(@"Distortion cost function was reduced by %1.2f percent.",100*(initial_cost_function_value - final_cost_function_value) / initial_cost_function_value);
	 */
	self.videoClip.project.distortionDisplayMode = @"Corrected";
	[self.videoClip.windowController refreshOverlay];

	// The solution was good enough to keep, but may still be unreliable outside the board's coverage.
	if (extrapolationWarning != nil) {
		[UtilityFunctions InformUser:extrapolationWarning withTitle:@"Distortion correction accepted, with a caveat"];
	}
}

#pragma mark
#pragma mark Utilitarian Class Functions

+ (void) rightMultiply3x3Matrix:(double[9])A trans:(enum CBLAS_TRANSPOSE)transA by3x3Matrix:(double[9])B trans:(enum CBLAS_TRANSPOSE)transB intoResultingMatrix:(double[9])C
{
	// The cblas_dgemm routine calculates alpha * A * B + beta * C, and places the result in C
	const int M = 3;			// rows in A and C
	const int N = 3;			// columns in B and C
	const int K = 3;			// columns in A and rows in B
	const double alpha = 1.0;	// scalar multiplier for A
	const int lda = 3;			// leading dimension of A
	const int ldb = 3;			// leading dimension of B
	const double beta = 0.0;	// scalar multiplier for C
	const int ldc = 3;			// leading dimension of C
	cblas_dgemm(CblasColMajor,transA,transB, M, N, K, alpha, A, lda, B, ldb, beta, C, ldc);
}


+ (void) putLeastSquaresSolutionForOverdeterminedSystem:(double[][9])A withRows:(int)numRows intoOutputMatrix:(double[9])x
{
	// Finds the least-squares best fit non-trivial solution to A*x = 0, where A has exactly 9 columns (used for my 2D projective transformations)
	// The input value of A should be a numrows-by-9 C array, which is converted herein to a column-major Fortran-compatible array for Lapack.
	// Use Lapack's sgesvd function to find the projective transformation, which is the least-squares estimate of the non-trivial solution to A*x=0.
	// The least-squares estimate is equal to the right-singular vector of A corresponding to the smallest singular value.
	// For details, see http://en.wikipedia.org/wiki/Singular_value_decomposition#Total_least_squares_minimization
	// Note: The reason I'm not using an overdetermined Ax=b system least-squares solver like sgelss is that it returns the trivial x=0 solution when b=0.
	char jobu = 'N';							// sets the job of 'u' regarding left-singular vectors: 'N' means don't compute them
	char jobvt = 'S';							// sets the job of 'vt': 'S' means the right-singular vectors are placed in the array vt
	__CLPK_integer m = numRows;					// rows in the matrix A
	__CLPK_integer n = 9;						// columns in the matrix A
	__CLPK_doublereal a[numRows*9];				// contains the m x n matrix A on input; values are destroyed on output given my values of jobu and jobvt
	__CLPK_integer lda = numRows;				// the first dimension of A
	__CLPK_doublereal s[9];						// output parameter: matrix for the singular values of A, sorted such that S(i) >= S(i+1)
	__CLPK_doublereal u[1];						// output parameter: unused because jobu = 'N'
	__CLPK_integer ldu = 1;						// the first dimension of u: unused because jobu = 'N'
	__CLPK_doublereal vt[81];					// output parameter: because jobvt = 'S', contains the 9 right-singular vectors of A stored row-wise
	__CLPK_integer ldvt = 9;					// the first dimension of vt
	__CLPK_doublereal work[64*numRows*9];		// workspace array; I'm not sure what it's used for exactly
	__CLPK_integer lwork = 64*numRows*9;		// length of the work array; borrowing this value from a working example of sgelss
	__CLPK_integer info;						// output parameter: if 0, success; if -i, ith argument had illegal value; if >0, failed to converge
	
	[VSCalibration arrange2DArray:A withRows:numRows intoColumnMajorVector:a];
	
	dgesvd_(&jobu, &jobvt, &m, &n, a, &lda, s, u, &ldu, vt, &ldvt, work, &lwork, &info);
	
	// The dgesvd_ function seems to randomly return either the correct values or the correct values multiplied by -1.  This sort of makes sense, because
	// the answer times -1 should still minimize the least squares.  Which solution sgesvd_ provides probably depends on some internal random number generation,
	// although that's strange because I always get the same (positive or negative) answer if I call the function over and over in the same program run.
	// I have to restart the program to "roll the dice" and see if I'll get a different answer.  However, because I know that the bottom right element of the
	// projection matrix is always close to +1 and never negative, I can use it to check for the negative answer and fix it when it turns up (below).
	
	double c = 1.0;
	if (vt[80] < 0.0) c = -1.0;
	
	x[0] = c * vt[8];
	x[1] = c * vt[35];
	x[2] = c * vt[62];
	x[3] = c * vt[17];
	x[4] = c * vt[44];
	x[5] = c * vt[71];
	x[6] = c * vt[26];
	x[7] = c * vt[53];
	x[8] = c * vt[80];
	
}


+ (void) arrange2DArray:(double[][9])A withRows:(int)numRows intoColumnMajorVector:(double[])a
{
	// Perhaps I should do something like a memcpy here since I typically want to create a new copy of the array
	
	// Make sure I initialize the variables A and a with the correct sizes (must have 9 columns) wherever I call this from
	// Put the values from A into a one-dimensional Fortran column-major form for use in Clapack.
	for (int v=0; v < 9; v++) {
		for (int u=0; u < numRows; u++) {
			a[v*numRows+u] = A[u][v];
		}
	}
}

- (void) calculateFCMMatrix:(NSString *)whichSurface
{
	// Put the values of each projection matrix into a one-dimensional Fortran column-major form for use in Lapack
	for (int v=0; v < 3; v++) {
		for (int u=0; u < 3; u++) {
			if ([whichSurface isEqualToString:@"Front"]) {
				if (self.matrixScreenToQuadratFront != nil) {
					matrixQuadratFrontToScreenFCM[v*3+u] = [[[self.matrixQuadratFrontToScreen objectAtIndex:u] objectAtIndex:v] doubleValue];
					matrixScreenToQuadratFrontFCM[v*3+u] = [[[self.matrixScreenToQuadratFront objectAtIndex:u] objectAtIndex:v] doubleValue];
				}
			} else {
				if (self.matrixScreenToQuadratBack != nil) {
					matrixQuadratBackToScreenFCM[v*3+u] = [[[self.matrixQuadratBackToScreen objectAtIndex:u] objectAtIndex:v] doubleValue];
					matrixScreenToQuadratBackFCM[v*3+u] = [[[self.matrixScreenToQuadratBack objectAtIndex:u] objectAtIndex:v] doubleValue];
				}
			}
		}
	}
}

- (void) putQuadratFrontToScreenFCMMatrixInArray:(double[9])arr
{
	for (int i = 0; i < 9; i++) arr[i] = matrixQuadratFrontToScreenFCM[i];
}

- (NSXMLNode *) representationAsXMLNode	
{
	const BOOL includeScreenCoords = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeScreenCoordsInExports"] boolValue];
	
	NSNumberFormatter *nf = [[NSNumberFormatter alloc] init];
	[nf setFormatterBehavior:NSNumberFormatterBehavior10_4];
	[nf setNumberStyle:NSNumberFormatterDecimalStyle];
	[nf setGroupingSeparator:@""];      // Custom number formatter here with a much higher precision for important parameters
	[nf setMinimumFractionDigits:50];   // especially the higher-order distortionK3 that begins out beyond 15 decimal places
	
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"calibration"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"cameraX" stringValue:[nf stringFromNumber:self.cameraX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"cameraY" stringValue:[nf stringFromNumber:self.cameraY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"cameraZ" stringValue:[nf stringFromNumber:self.cameraZ]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionCenterX" stringValue:[nf stringFromNumber:self.distortionCenterX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionCenterY" stringValue:[nf stringFromNumber:self.distortionCenterY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK1" stringValue:[nf stringFromNumber:self.distortionK1]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK2" stringValue:[nf stringFromNumber:self.distortionK2]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK3" stringValue:[nf stringFromNumber:self.distortionK3]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK4" stringValue:[nf stringFromNumber:self.distortionK4]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK5" stringValue:[nf stringFromNumber:self.distortionK5]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK6" stringValue:[nf stringFromNumber:self.distortionK6]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK7" stringValue:[nf stringFromNumber:self.distortionK7]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionP1" stringValue:[nf stringFromNumber:self.distortionP1]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionP2" stringValue:[nf stringFromNumber:self.distortionP2]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionP3" stringValue:[nf stringFromNumber:self.distortionP3]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionP4" stringValue:[nf stringFromNumber:self.distortionP4]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"matrixScreenToQuadratFront" stringValue:[self matrixAsOutputString:self.matrixScreenToQuadratFront]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"matrixScreenToQuadratBack" stringValue:[self matrixAsOutputString:self.matrixScreenToQuadratBack]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"matrixQuadratFrontToScreen" stringValue:[self matrixAsOutputString:self.matrixQuadratFrontToScreen]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"matrixQuadratBackToScreen" stringValue:[self matrixAsOutputString:self.matrixQuadratBackToScreen]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"residualFrontLeastSquares" stringValue:[nf stringFromNumber:self.residualFrontLeastSquares]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"residualBackLeastSquares" stringValue:[nf stringFromNumber:self.residualBackLeastSquares]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"residualFrontPixel" stringValue:[nf stringFromNumber:self.residualFrontPixel]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"residualBackPixel" stringValue:[nf stringFromNumber:self.residualBackPixel]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"residualFrontWorld" stringValue:[nf stringFromNumber:self.residualFrontWorld]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"residualBackWorld" stringValue:[nf stringFromNumber:self.residualBackWorld]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionReductionAchieved" stringValue:[nf stringFromNumber:self.distortionReductionAchieved]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionRemainingPerPoint" stringValue:[nf stringFromNumber:self.distortionRemainingPerPoint]]];
	if (includeScreenCoords) {
		NSXMLElement *distortionLines = [[NSXMLElement alloc] initWithName:@"distortionLines"];
		NSXMLElement *frontCalibrationPoints = [[NSXMLElement alloc] initWithName:@"frontCalibrationPoints"];
		NSXMLElement *backCalibrationPoints = [[NSXMLElement alloc] initWithName:@"backCalibrationPoints"];
		for (VSDistortionLine *distortionLine in self.distortionLines) [distortionLines addChild:[distortionLine representationAsXMLNode]];
		for (VSCalibrationPoint *calibrationPoint in self.pointsFront) [frontCalibrationPoints addChild:[calibrationPoint representationAsXMLNode]];
		for (VSCalibrationPoint *calibrationPoint in self.pointsBack) [backCalibrationPoints addChild:[calibrationPoint representationAsXMLNode]];
		[mainElement addChild:distortionLines];
		[mainElement addChild:frontCalibrationPoints];
		[mainElement addChild:backCalibrationPoints];
	}
	return mainElement;
}

- (NSString *) matrixAsOutputString:(NSArray *)matrix
{
	NSNumberFormatter *nf = self.videoClip.project.document.decimalFormatter;
	NSString *result = [NSString stringWithFormat:@"{{%@,%@,%@},{%@,%@,%@},{%@,%@,%@}}",
					[nf stringFromNumber:[[matrix objectAtIndex:0] objectAtIndex:0]],
					[nf stringFromNumber:[[matrix objectAtIndex:0] objectAtIndex:1]],
					[nf stringFromNumber:[[matrix objectAtIndex:0] objectAtIndex:2]],
					[nf stringFromNumber:[[matrix objectAtIndex:1] objectAtIndex:0]],
					[nf stringFromNumber:[[matrix objectAtIndex:1] objectAtIndex:1]],
					[nf stringFromNumber:[[matrix objectAtIndex:1] objectAtIndex:2]],
					[nf stringFromNumber:[[matrix objectAtIndex:2] objectAtIndex:0]],
					[nf stringFromNumber:[[matrix objectAtIndex:2] objectAtIndex:1]],
					[nf stringFromNumber:[[matrix objectAtIndex:2] objectAtIndex:2]]
					];
	return result;
}

@end


