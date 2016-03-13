/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
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
#import "gsl/gsl_multimin.h"

#import "VSCalibration.h"

#pragma mark
#pragma mark C Functions for Distortion Correction

double orthogonalRegressionLineCostFunction(NSPoint line[], const size_t numLinePoints, double* linePixelLength)
// This is a cost function measuring the "straightness" of a line based on orthogonal distance regression.
// It returns the sums of squared residuals from the line, and places the length of the line (the distance
// between its endpoints) in linePixelLength.  The formula comes from a 2005 post on the Ask Dr. Math forum,
// at http://mathforum.org/library/drmath/view/68362.html
{
    // Find the centroid of the line
    NSPoint centroid = NSMakePoint(0.0,0.0);
    for (int i = 0; i < numLinePoints; i++) {
        centroid.x += line[i].x;
        centroid.y += line[i].y;
    }
    centroid.x = centroid.x / (double) numLinePoints;
    centroid.y = centroid.y / (double) numLinePoints;
    // Calculate big ArcTan term
    double mainsum = 0.0;
    double mainsqsum = 0.0;
    for (int i = 0; i < numLinePoints; i++) {
        mainsum += (line[i].x - centroid.x) * (line[i].y - centroid.y); 
        mainsqsum += (pow((line[i].x - centroid.x),2.0) - pow((line[i].y - centroid.y),2.0));
    }
    const double bigatan = atan(2.0 * mainsum / mainsqsum);
    // Calculate the sums of squares
    const double theta1 = 0.5 * bigatan;
    const double theta2 = 0.5 * (bigatan + M_PI);
    const double xInt1 = centroid.x - centroid.y / tan(theta1);
    const double xInt2 = centroid.x - centroid.y / tan(theta2);
    double ssq1 = 0.0;
    double ssq2 = 0.0;
    for (int i = 0; i < numLinePoints; i++) {
        ssq1 += pow(-(line[i].x - xInt1) * sin(theta1) + line[i].y * cos(theta1),2.0);
        ssq2 += pow(-(line[i].x - xInt2) * sin(theta2) + line[i].y * cos(theta2),2.0);
    }
    // Find the length of the line (distance from first point to last point -- line is sorted)
    double endpointsvec[2];
    endpointsvec[0] = line[numLinePoints-1].x - line[0].x;
    endpointsvec[1] = line[numLinePoints-1].y - line[0].y;
    *linePixelLength += cblas_dnrm2(2,endpointsvec,1);
    // Return the smallest ssq
    const double minssq = (ssq1 > ssq2) ? ssq2 : ssq1;
    return minssq;
}

double orthogonalRegressionTotalCostFunction(const gsl_vector *v, void *params){
    // This function measures the total "straightness" of all the lines.  Its arguments are formatted
    // in such a way that it can be set as the function to minimize using the multimin features of the GNU
    // scientific library.  It returns the sum of the squared residuals from an orthogonal regression on all
    // the lines, divided by the total length of all the lines (without this division, te total residual can be minimized by 
    // shrinking all the lines to 0 size instead of just straightening them).
    // First, interpret the "parameters," which in this case means the pointer to the struct holding the plumbline data
    Plumblines* p = (Plumblines*) params;
    // Prepare the variables being adjusted to minimize the cost function -- the distortion parameters
    double x0,y0,k1,k2,k3,p1,p2,p3;
    x0 = gsl_vector_get(v,0) * SCALE_FACTOR_X0;
    y0 = gsl_vector_get(v,1) * SCALE_FACTOR_Y0;
    k1 = gsl_vector_get(v,2) * SCALE_FACTOR_K1;
    k2 = gsl_vector_get(v,3) * SCALE_FACTOR_K2;
    k3 = gsl_vector_get(v,4) * SCALE_FACTOR_K3;
    p1 = gsl_vector_get(v,5) * SCALE_FACTOR_P1;
    p2 = gsl_vector_get(v,6) * SCALE_FACTOR_P2;
    p3 = gsl_vector_get(v,7) * SCALE_FACTOR_P3;
    // Build an undistorted line data structure based on the values above and the pointer to the original data
    Plumblines up;
    up.numLines = p->numLines;
    up.lines = (NSPoint **) malloc(up.numLines*sizeof(NSPoint *));
    up.lineLengths = (size_t *) malloc(up.numLines*sizeof(size_t *));
    for (int i = 0; i < up.numLines; i++) {		
        up.lineLengths[i] = p->lineLengths[i];
        up.lines[i] = (NSPoint *) malloc(up.lineLengths[i]*sizeof(NSPoint));
        for (int j = 0; j < up.lineLengths[i]; j++) {
            up.lines[i][j] = undistortPoint(&(p->lines[i][j]),x0,y0,k1,k2,k3,p1,p2,p3);
        }
    }
    // Sum the orthogonal regression cost functions over all the lines
    double totalSSQRCost = 0.0;
    double totalLinePixelLength = 0.0;
    for (int i = 0; i < up.numLines; i++) totalSSQRCost += orthogonalRegressionLineCostFunction(up.lines[i], up.lineLengths[i], &totalLinePixelLength);
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

NSPoint undistortPoint(const NSPoint* pt, const double x0, const double y0, const double k1, const double k2, const double k3, const double p1, const double p2, const double p3){
    double xd = pt->x - x0;
    double yd = pt->y - y0;
    double rs = xd*xd + yd*yd; 
    const double xu = x0 + xd*(1 + k1*rs + k2*rs*rs + k3*rs*rs*rs) + (p1*(rs + 2*xd*xd) + 2*p2*xd*yd)*(1 + p3*rs);
    const double yu = y0 + yd*(1 + k1*rs + k2*rs*rs + k3*rs*rs*rs) + (2*p1*xd*yd + p2*(rs + 2*yd*yd))*(1 + p3*rs);
    return NSMakePoint(xu, yu);
}

NSPoint redistortPoint(const NSPoint* pt, const double x0, const double y0, const double k1, const double k2, const double k3, const double p1, const double p2, const double p3){
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
    double params[8] = {xuc, yuc, k1, k2, k3, p1, p2, p3};
    gsl_multiroot_function_fdf f = {&redistortionRootFunc_f, &redistortionRootFunc_df, &redistortionRootFunc_fdf, n, params};
    gsl_vector *x = gsl_vector_alloc(n);    // Initialize the solution starting at the input/undistorted point
    gsl_vector_set(x, 0, xuc);
    gsl_vector_set(x, 1, yuc);
    T = gsl_multiroot_fdfsolver_gnewton;
    s = gsl_multiroot_fdfsolver_alloc(T, n);
    gsl_multiroot_fdfsolver_set(s, &f, x);
    do {
        iter++;
        status = gsl_multiroot_fdfsolver_iterate(s);
        if (status) break;
        status = gsl_multiroot_test_residual (s->f, 1e-7);
    } while (status == GSL_CONTINUE && iter < 1000);
    
    NSPoint result = NSMakePoint(x0 + gsl_vector_get(s->x, 0), y0 + gsl_vector_get(s->x, 1));
    /*
     This code shows a bit of what's going on when this solver finds the wrong solution for one of the y-coordinates in seemingly random (but repeatable)
     locations... it's probably convering on some other solution. Not sure how to fix this. Only happens in 9/4/2015 video for now with the widest fisheye.
     
    if (fabs(pt->y - result.y) > 2000) {
        NSLog(@"VERY ODDLY REDISTORTED POINT (%1.1f, %1.1f) TO POINT (%1.1f, %1.1f)",pt->x,pt->y,result.x,result.y);
    } else {
        NSLog(@"redistorted (%1.1f, %1.1f) to point (%1.1f, %1.1f)",pt->x,pt->y,result.x,result.y);
    }
    */
    gsl_multiroot_fdfsolver_free (s);
    gsl_vector_free (x);
    return result;
}

int redistortionRootFunc_f(const gsl_vector* x, void* params, gsl_vector* f) {
    const double* p = (double*) params;
    const double xd = gsl_vector_get(x, 0);
    const double yd = gsl_vector_get(x, 1);
    const double targetxu = p[0];
    const double targetyu = p[1];
    const double k1 = p[2];
    const double k2 = p[3];
    const double k3 = p[4];
    const double p1 = p[5];
    const double p2 = p[6];
    const double p3 = p[7];
    const double rs = xd*xd + yd*yd; // I read online that multiplying like this is slightly faster than pow() for simple squaring/cubing
    const double xu = xd + xd*(k1*rs + k2*rs*rs + k3*rs*rs*rs) + (p1*(rs + 2*xd*xd) + 2*p2*xd*yd)*(1 + p3*rs);
    const double yu = yd + yd*(k1*rs + k2*rs*rs + k3*rs*rs*rs) + (2*p1*xd*yd + p2*(rs + 2*yd*yd))*(1 + p3*rs);    
    gsl_vector_set(f, 0, xu - targetxu);
    gsl_vector_set(f, 1, yu - targetyu);
    return GSL_SUCCESS;
}

int redistortionRootFunc_df(const gsl_vector* x, void* params, gsl_matrix* J) {
    double* p = (double*) params;
    const double xd = gsl_vector_get(x, 0);  // distorted xd input
    const double yd = gsl_vector_get(x, 1);  // distorted yd input
    const double k1 = p[2];
    const double k2 = p[3];
    const double k3 = p[4];
    const double p1 = p[5];
    const double p2 = p[6];
    const double p3 = p[7];
    const double rs = xd*xd + yd*yd;
    
    // This Jacobian consists of the derivative of each of the xd and yd elements of the distortion function, with respect to each of xd and yd.  Calculated using Mathematica.
    const double df00 = 1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + (6*p1*xd + 2*p2*yd)*(1 + p3*rs) + xd*(2*k1*xd + 4*k2*xd*rs + 6*k3*xd*pow(rs,2)) + 2*p3*xd*(2*p2*xd*yd + p1*(3*rs));
    const double df01 =  (2*p2*xd + 2*p1*yd)*(1 + p3*rs) + xd*(2*k1*yd + 4*k2*yd*rs + 6*k3*yd*pow(rs,2)) + 2*p3*yd*(2*p2*xd*yd + p1*(3*rs));
    const double df10 =  (2*p2*xd + 2*p1*yd)*(1 + p3*rs) + yd*(2*k1*xd + 4*k2*xd*rs + 6*k3*xd*pow(rs,2)) + 2*p3*xd*(2*p1*xd*yd + p2*(pow(xd,2) + 3*pow(yd,2)));
    const double df11 =  1 + k1*rs + k2*pow(rs,2) + k3*pow(rs,3) + (2*p1*xd + 6*p2*yd)*(1 + p3*rs) + yd*(2*k1*yd + 4*k2*yd*rs + 6*k3*yd*pow(rs,2)) + 2*p3*yd*(2*p1*xd*yd + p2*(pow(xd,2) + 3*pow(yd,2)));
    
    gsl_matrix_set(J, 0, 0, df00);
    gsl_matrix_set(J, 0, 1, df01);
    gsl_matrix_set(J, 1, 0, df10);
    gsl_matrix_set(J, 1, 1, df11);
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
            frontIntersection = VSMakePoint3D(p->frontSurfaceCoord, frontSolveCoord2, frontSolveCoord2);            
            refractionPlaneBackPoint = VSMakePoint3D(p->realPosition.x, backSolveCoord2, backSolveCoord1);
            refractionPlaneFrontPoint = VSMakePoint3D(p->camPosition.y, frontSolveCoord2, frontSolveCoord2);
        }
    }
    
    negativeInterfaceNormal = VSMakePoint3D(interfaceNormal.x * -1.0, interfaceNormal.y * -1.0, interfaceNormal.z * -1.0);
    
    const double thetaBackIn   = acos(VSPoint3DDot(interfaceNormal, VSSubtractPoint3D(p->realPosition, backIntersection)) / VSPoint3DNorm(VSSubtractPoint3D(p->realPosition, backIntersection)));
    const double thetaBackOut  = acos(VSPoint3DDot(negativeInterfaceNormal, VSSubtractPoint3D(frontIntersection, backIntersection)) / VSPoint3DNorm(VSSubtractPoint3D(frontIntersection, backIntersection)));
    const double thetaFrontIn  = acos(VSPoint3DDot(interfaceNormal, VSSubtractPoint3D(backIntersection, frontIntersection)) / VSPoint3DNorm(VSSubtractPoint3D(backIntersection, frontIntersection)));
    const double thetaFrontOut = acos(VSPoint3DDot(negativeInterfaceNormal, VSSubtractPoint3D(p->camPosition, frontIntersection)) / VSPoint3DNorm(VSSubtractPoint3D(p->camPosition, frontIntersection)));
    
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
@dynamic distortionP1;
@dynamic distortionP2;
@dynamic distortionP3;
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
        [UtilityFunctions InformUser:[NSString stringWithFormat:@"Your click was ignored because you haven't set the world coordinates for any calibration points on the %@ yet. Please set them and try again.",whichSurface]];
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
		NSArray *quadratDescription = [NSArray arrayWithObjects:[self.quadratNodesFront string],[self.quadratNodesBack string],self.planeCoordFront,self.planeCoordBack,self.shouldCorrectRefraction, self.frontQuadratSurfaceThickness, self.frontQuadratSurfaceRefractiveIndex, self.mediumRefractiveIndex, nil];
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
		self.quadratNodesFront = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:0]];
		self.quadratNodesBack = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:1]];
		self.planeCoordFront = [quadratDescription objectAtIndex:2];
		self.planeCoordBack = [quadratDescription objectAtIndex:3];
        if ([quadratDescription count] > 4) {
            self.shouldCorrectRefraction = [quadratDescription objectAtIndex:4];
            self.frontQuadratSurfaceThickness = [quadratDescription objectAtIndex:5];
            self.frontQuadratSurfaceRefractiveIndex = [quadratDescription objectAtIndex:6];
            self.mediumRefractiveIndex = [quadratDescription objectAtIndex:7];
        }
	}	
}

- (void) loadQuadratDescriptionExample
{
	NSString *filePath = [[NSBundle mainBundle] pathForResource:@"Example Quadrat" ofType:@"VidSyncQuadrat"];
	NSArray *quadratDescription = [[NSArray alloc] initWithContentsOfFile:filePath];
	self.quadratNodesFront = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:0]];
	self.quadratNodesBack = [[NSAttributedString alloc] initWithString:[quadratDescription objectAtIndex:1]];
	self.planeCoordFront = [quadratDescription objectAtIndex:2];
	self.planeCoordBack = [quadratDescription objectAtIndex:3];	
    if ([quadratDescription count] > 4) {
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
        
        NSArray *fullCalibration = [NSArray arrayWithObjects:
                                     ([self.quadratNodesFront string] != nil) ? [self.quadratNodesFront string] : @"",
									([self.quadratNodesBack string] != nil) ? [self.quadratNodesBack string] : @"",
                                    (self.planeCoordFront != nil) ? self.planeCoordFront : [NSNumber numberWithInt:0],
                                    (self.planeCoordBack != nil) ? self.planeCoordBack : [NSNumber numberWithInt:0],
                                    self.axisHorizontal,
                                    self.axisVertical,
									pointsFrontArray,
									pointsBackArray,
									isMasterClip,
                                    self.videoClip.project.calibrationTimecode,
                                    self.shouldCorrectRefraction,
                                    self.frontQuadratSurfaceThickness,
                                    self.frontQuadratSurfaceRefractiveIndex,
                                    self.mediumRefractiveIndex,
                                    nil
                                    ];
		if (![fullCalibration writeToFile:[[savePanel URL] path] atomically:YES]) NSLog(@"Error writing calibration file. Some object in the list was null.");
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
		self.quadratNodesFront = [[NSAttributedString alloc] initWithString:[fullCalibration objectAtIndex:0]];
		self.quadratNodesBack = [[NSAttributedString alloc] initWithString:[fullCalibration objectAtIndex:1]];
		self.planeCoordFront = [fullCalibration objectAtIndex:2];
		self.planeCoordBack = [fullCalibration objectAtIndex:3];
		self.axisHorizontal = [fullCalibration objectAtIndex:4];
		self.axisVertical = [fullCalibration objectAtIndex:5];
        if ([fullCalibration count] > 10) {
            self.shouldCorrectRefraction = [fullCalibration objectAtIndex:10];
            self.frontQuadratSurfaceThickness = [fullCalibration objectAtIndex:11];
            self.frontQuadratSurfaceRefractiveIndex = [fullCalibration objectAtIndex:12];
            self.mediumRefractiveIndex = [fullCalibration objectAtIndex:13];
        }
		VSCalibrationPoint *newPoint;
		for (VSCalibrationPoint *pointToDelete in self.pointsFront) [self.managedObjectContext deleteObject:pointToDelete];		// remove the old points if there are any
		for (NSArray *pointArray in [fullCalibration objectAtIndex:6]) {	// Loop through the array for the front calibration points, and create them
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
			NSInteger alertResult = NSRunAlertPanel(@"Set calibration time?",
													@"The calibration you've loaded comes from a master clip, and includes a calibration time.  Do you want to set this project's calibration time to equal that one?",
													@"Yes",
													@"No",
													nil);
			if (alertResult == NSAlertDefaultReturn) self.videoClip.project.calibrationTimecode = [fullCalibration objectAtIndex:9];		// user clicked yes
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
                                    self.distortionP1,
                                    self.distortionP2,
                                    self.distortionP3,
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
        NSInteger alertResult;
        if ([self.distortionLines count] > 0) {
            alertResult = NSRunAlertPanel(@"Overwrite current plumblines and parameters?",
                                                    @"You can choose to overwrite any existing plumblines and parameters with new values from the file, or simply add the plumblines from the file to the list above.",
                                                    @"Overwrite Plumblines and Parameters",
                                                    @"Just Add to Existing Plumblines",
                                                    nil);
        } else {
            alertResult = NSAlertDefaultReturn; // If there was nothing to overwrite, simulate the user clicking "Overwrite" without prompting for it.
        }
        if (alertResult == NSAlertDefaultReturn) { // user clicked overwrite -- delete old distortion lines AND overwrite parameters
            self.distortionCenterX = [fullDistortion objectAtIndex:0];
            self.distortionCenterY = [fullDistortion objectAtIndex:1];
            self.distortionK1 = [fullDistortion objectAtIndex:2];
            self.distortionK2 = [fullDistortion objectAtIndex:3];
            self.distortionK3 = [fullDistortion objectAtIndex:4];
            self.distortionP1 = [fullDistortion objectAtIndex:5];
            self.distortionP2 = [fullDistortion objectAtIndex:6];
            self.distortionP3 = [fullDistortion objectAtIndex:7];
            for (VSDistortionLine *lineToDelete in self.distortionLines) [self.managedObjectContext deleteObject:lineToDelete];		// remove the old points if there are any
        }
        VSDistortionLine *newLine;
        VSDistortionPoint *newPoint;
        for (NSArray *lineArray in [fullDistortion objectAtIndex:8]) {	// Regardless of overwrite setting, we now add points
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
        [tooFewPointsAlert setAlertStyle:NSCriticalAlertStyle];
        NSInteger alertResult = [tooFewPointsAlert runModal];
        if (alertResult == NSAlertSecondButtonReturn) {
            ([self.pointsFront count] >= 4) ? calibrateFront = YES : calibrateBack = YES;
        }
    } else {
        NSAlert *tooFewPointsAlert = [NSAlert new];
        [tooFewPointsAlert setMessageText:@"Too few points for calibration"];
        [tooFewPointsAlert setInformativeText:@"You need at least 4 points on both calibration frame surfaces for 3-D calibration (or on one surface for 2-D calibration)."];
        [tooFewPointsAlert addButtonWithTitle:@"Ok"];
        [tooFewPointsAlert setAlertStyle:NSCriticalAlertStyle];
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
        [tooFewPointsAlert setAlertStyle:NSCriticalAlertStyle];
        [tooFewPointsAlert runModal];
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
    return (self.matrixScreenToQuadratBack != nil && self.matrixQuadratFrontToScreen != nil);
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
    int numPoints = ([whichSurface isEqualToString:@"Front"]) ? [self.pointsFront count] : [self.pointsBack count];
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
    int numPoints = [points count];
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
    int numLines = [self.pointsBack count];
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
	int numRows = [points count]*2;
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
    [VSCalibration rightMultiply3x3Matrix:p trans:CblasNoTrans by3x3Matrix:normalizingMatrix trans:CblasNoTrans intoResultingMatrix:halfway];
    [VSCalibration rightMultiply3x3Matrix:denormalizingMatrix trans:CblasNoTrans by3x3Matrix:halfway trans:CblasNoTrans intoResultingMatrix:p];

    // Now we can calculate the inverse of the new p as normal in the non-normalized coordinates.
    
	memcpy(pinv, p, 9 * sizeof (double));			// copy p into pinv for inversion
	memcpy(x_r, p, 9 * sizeof (double));			// copy p into x_r for use calculating residuals
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
    p.axisHorizontal = [self.axisHorizontal characterAtIndex:0];
    p.axisVertical   = [self.axisVertical characterAtIndex:0];
    p.frontSurfaceCoord = [self.planeCoordFront doubleValue];
    p.backSurfaceCoord = p.frontSurfaceCoord + frontSurfaceThickness;
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
                          [self.distortionP1 doubleValue],
                          [self.distortionP2 doubleValue],
                          [self.distortionP3 doubleValue]
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
                          [self.distortionP1 doubleValue],
                          [self.distortionP2 doubleValue],
                          [self.distortionP3 doubleValue]
                          );
}

- (CvPoint2D32f) centroidOfNumber:(int)numPoints ofCvPoints:(CvPoint2D32f *)points
{
    double xtot = 0.0;
    double ytot = 0.0;
    for (int i=0; i<numPoints; i++) {
        xtot += points[i].x;
        ytot += points[i].y;
    }
    double xmean = xtot / (double) numPoints;
    double ymean = ytot / (double) numPoints;
    return cvPoint2D32f(xmean,ymean);
}

- (int) indexOfNearestPointTo:(CvPoint2D32f)position inNumber:(int)numPoints ofCvPoints:(CvPoint2D32f *)points bestDistance:(double *)bestDistance
{
    int bestIndex = 0;
    double tempBestDistance = 100000.0;  // Start out with the "best" distance longer than any real points can have, so it's replaced ASAP.
    double distance,a,b;
    for (int i=0; i<numPoints; i++) {
        a = position.x - points[i].x;
        b = position.y - points[i].y;
        distance = sqrt(a*a + b*b);
        if (distance < tempBestDistance && distance > 0.0001) {    // Exclude distance ~0 so I don't select the same point as the closest.
            tempBestDistance = distance;
            bestIndex = i;
        }
    }
    *bestDistance = tempBestDistance;
    return bestIndex;
}

- (int) indexOfPointEqualTo:(CvPoint2D32f)position inNumber:(int)numPoints ofCvPoints:(CvPoint2D32f *)points
{
    int theIndex = 0;
    int i = 0;
    bool found = false;
    while (!found) {
        if (position.x == points[i].x && position.y == points[i].y) {
            theIndex = i;
            found = true;
        }
        i++;
    }
    return theIndex;
}

- (int) buildLine:(CvPoint2D32f *)linePoints fromNumber:(int)numPoints ofPoints:(CvPoint2D32f *)allPoints byExtending:(int)startPointInd inDirectionOf:(int)dirPointInd
{
    // Maximum distance from the next point to its candidate position, as a fraction of the distance between previous points.
    const double distanceTolerance =  [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"chessboardDetectionCandidateDistanceTolerance"] doubleValue];   
    
    // set the minimum pixels from the edge of the image for a detected corner to count; prevents non-corner detections right on the edge of the image
    const float minDistanceFromEdge = 4.0;
    const float maxX = (float) [self.videoClip clipWidth] - minDistanceFromEdge;
    const float maxY = (float) [self.videoClip clipHeight] - minDistanceFromEdge;
    const float minX = minDistanceFromEdge;
    const float minY = minDistanceFromEdge;
    
    linePoints[0] = allPoints[startPointInd];
    linePoints[1] = allPoints[dirPointInd];
    
//    NSLog(@"Beginning building a line based on %1.1f,%1.1f and %1.1f,%1.1f",linePoints[0].x,linePoints[0].y,linePoints[1].x,linePoints[1].y);
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
        nextIndex = [self indexOfNearestPointTo:cvPoint2D32f(xcandidate,ycandidate) inNumber:numPoints ofCvPoints:allPoints bestDistance:&bestDistance];
        if (minX < allPoints[nextIndex].x && allPoints[nextIndex].x < maxX && minY < allPoints[nextIndex].y && allPoints[nextIndex].y < maxY) { // check that point isn't too close to edge of screen
            // We add a new point if the closest point to the candidate next point position is within an appropriate distance of it, and is not the previous point itself.
            if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
                foundNext = true;
                linePoints[i] = allPoints[nextIndex];
                
//                NSLog(@"Extending the line to the next point %1.1f,%1.1f.",linePoints[i].x,linePoints[i].y);
                
                prevIndex = nextIndex;
                i++;    // After this loop breaks, 'i' will be 1 greater than the highest index of the highest actual point, equal to the total # of points
            } else {    // No point was found in the expected position of a next point... see if we can find one by jumping a bad point.  Otherwise, end of the line.
                xcandidate = linePoints[i-1].x + (2.0 * xdiff);
                ycandidate = linePoints[i-1].y + (2.0 * ydiff);
                nextIndex = [self indexOfNearestPointTo:cvPoint2D32f(xcandidate,ycandidate) inNumber:numPoints ofCvPoints:allPoints bestDistance:&bestDistance];
                if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
                    foundNext = true;
                    linePoints[i] = allPoints[nextIndex];

//                    NSLog(@"Skipped one point and then extending the line to the next point %1.1f,%1.1f.",linePoints[i].x,linePoints[i].y);
                    
                    prevIndex = nextIndex;
                    i++;    // After this loop breaks, i will be 1 greater than the highest index of the highest actual point, equal to the total # of points
                } else {
//                    NSLog(@"End of line -- tried to skip a point but didn't find anything after skipping.");
                    foundNext = false;
                }
            }
        } else { // stop if point was too close to edge of screen
//            NSLog(@"End of line -- point found was too close to edge of screen.");
            foundNext = false;
        }
    }
    // Reverse the elements of linePoints.  Before this, indices of the line points go from 0 to i-1
    CvPoint2D32f *reversedFirstHalf = (CvPoint2D32f*)malloc(i * sizeof(CvPoint2D32f)); 
    for (int j=0; j<i; j++) {
        reversedFirstHalf[j] = linePoints[(i-1) - j];
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
        nextIndex = [self indexOfNearestPointTo:cvPoint2D32f(xcandidate,ycandidate) inNumber:numPoints ofCvPoints:allPoints bestDistance:&bestDistance];
        if (minX < allPoints[nextIndex].x && allPoints[nextIndex].x < maxX && minY < allPoints[nextIndex].y && allPoints[nextIndex].y < maxY) { // check that point isn't too close to edge of screen
            if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
                foundNext = true;
                linePoints[i] = allPoints[nextIndex];
                prevIndex = nextIndex;
                i++;
            } else {
                xcandidate = linePoints[i-1].x + (2.0 * xdiff);
                ycandidate = linePoints[i-1].y + (2.0 * ydiff);
                nextIndex = [self indexOfNearestPointTo:cvPoint2D32f(xcandidate,ycandidate) inNumber:numPoints ofCvPoints:allPoints bestDistance:&bestDistance];
                if (bestDistance < maxBestDistance && prevIndex != nextIndex) {
                    foundNext = true;
                    linePoints[i] = allPoints[nextIndex];
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
    return i; // return value i is the length of the line
}

- (void) removeAllPlumblines
{
    for (VSDistortionLine *line in self.distortionLines) [[self managedObjectContext] deleteObject:line];
    [[self managedObjectContext] processPendingChanges];
    [self.videoClip.windowController refreshOverlay];
}


- (void) autodetectChessboardPlumblines
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
    const int useHarris = 0;
    const double harrisK = 0.04;
    
    const int maxLineCorners = floor(maxNumCorners/4);
    
    CGImageRef videoFrameCG = [self.videoClip.project.document highQualityStillFromVSVideoClip:self.videoClip atMasterTime:[self.videoClip.project.document currentMasterTime]];
    IplImage *videoFrameIpl = (IplImage *) [UtilityFunctions CreateIplImageFromCGImage:videoFrameCG];
    CFRelease(videoFrameCG);
    IplImage* videoFrameSingleChannelIpl = cvCreateImage(cvGetSize(videoFrameIpl), videoFrameIpl->depth, 1);
    cvSetImageCOI(videoFrameIpl, 1);
    cvCopy(videoFrameIpl, videoFrameSingleChannelIpl);

    int numCorners = maxNumCorners;  // Max # of corners to find.  On return, it is replaced by the # actually found.
    CvPoint2D32f *foundCorners = (CvPoint2D32f*)malloc((maxNumCorners + 1) * sizeof(CvPoint2D32f)); 
    IplImage *eigImage = cvCreateImage(cvGetSize(videoFrameIpl),IPL_DEPTH_32F, 1);
    IplImage *tempImage = cvCreateImage(cvGetSize(videoFrameIpl),IPL_DEPTH_32F, 1);
    
    // Find the corner positions -- they'll be pretty much the only good "features to track" when the chessboard takes up the entire screen.
    cvGoodFeaturesToTrack(videoFrameSingleChannelIpl, eigImage, tempImage, foundCorners, &numCorners, qualityLevel, minDistance, NULL, blockSize, useHarris, harrisK);
    
    // Running cvFindCornerSubPix with a high window size like (15,15) corrected some severe mislocations around one of my squares that (5,5) did not.
    cvFindCornerSubPix(videoFrameSingleChannelIpl, foundCorners, numCorners, cvSize(cornerSubPixWindowSize,cornerSubPixWindowSize), cvSize(-1,-1), cvTermCriteria( CV_TERMCRIT_ITER | CV_TERMCRIT_EPS, 20, 0.01 ));
    
    // Since OpenCV flips the y-coordinate (from top left instead of bottom left), flip it back here right away so it doesn't confuse later calculations.
    for (int i = 0; i < numCorners; i++) foundCorners[i].y = [self.videoClip clipHeight] - foundCorners[i].y;
    
    // Store the autodetected corners for temporarly display overlaying the main window.
    
    self.autodetectedPoints = [NSMutableSet setWithCapacity:numCorners];
    for (int i = 0; i < numCorners; i++) {
        [self.autodetectedPoints addObject:[NSValue valueWithPoint:NSMakePoint(foundCorners[i].x,foundCorners[i].y)]];
    }
    
    // Build the first distortion line
    int lineLength, centerIndex, nextIndex;
    double dummyBestDistance;
    CvPoint2D32f *firstLine = (CvPoint2D32f*)malloc((maxLineCorners + 1) * sizeof(CvPoint2D32f));
    // Manually seed the start of the line creation algorithm if the user has entered exactly one line with exactly two points as the seed.
    if ([self.distortionLines count] == 1 && [[[self.distortionLines anyObject] distortionPoints] count] == 2) {
//        NSLog(@"Running the autodetect section for when there's a seed line.");
        VSDistortionLine *seedLine = [self.distortionLines anyObject];
        NSArray *seedPoints = [[seedLine distortionPoints] allObjects];
        VSDistortionPoint *seedPoint1 = [seedPoints objectAtIndex:0];
        VSDistortionPoint *seedPoint2 = [seedPoints objectAtIndex:1];
        CvPoint2D32f seedPointCv1 = cvPoint2D32f([seedPoint1.screenX doubleValue],[seedPoint1.screenY doubleValue]);
        CvPoint2D32f seedPointCv2 = cvPoint2D32f([seedPoint2.screenX doubleValue],[seedPoint2.screenY doubleValue]);
//        NSLog(@"The seed line is %1.1f,%1.1f and %1.1f,%1.1f",seedPointCv1.x,seedPointCv1.y,seedPointCv2.x,seedPointCv2.y);
        centerIndex = [self indexOfNearestPointTo:seedPointCv1 inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
        nextIndex = [self indexOfNearestPointTo:seedPointCv2 inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
        [[self managedObjectContext] deleteObject:seedLine];    // Delete the seed after using it
    } else {    // Otherwise, start the line creation algorithm from the center point to the nearest other point
//        NSLog(@"Running the autodetect section for when there's NO seed line.");
        CvPoint2D32f centroid = [self centroidOfNumber:numCorners ofCvPoints:foundCorners]; // geometrical center of all the detected point (NOT the centermost point)
        centerIndex = [self indexOfNearestPointTo:centroid inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
        nextIndex = [self indexOfNearestPointTo:foundCorners[centerIndex] inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
    }
    lineLength = [self buildLine:firstLine fromNumber:numCorners ofPoints:foundCorners byExtending:centerIndex inDirectionOf:nextIndex];
    
    // I'm not adding the first line to the object model here, because it would be duplicated later when crossing the crossing lines, and it's easier to just not add it here
    // than to skip over adding it there.

    // After calculating the first line, now go all up and down it calculating other lines.
 
    CvPoint2D32f vec, newDir, rotatedTargetGuess;
    int crossingLineLength = 0;
    int baseIndex = 0;
    int midCrossingLineLength = 0;
    CvPoint2D32f *midCrossingLine = (CvPoint2D32f*)malloc((maxLineCorners + 1) * sizeof(CvPoint2D32f)); // temp spot to save the middle crossing line
    // This whole block below is a copy of the loop below it, but with the line order switched, just to avoid skipping the first crossing line on the end.
    vec = cvPoint2D32f(firstLine[0].x - firstLine[1].x,firstLine[0].y - firstLine[1].y);
    newDir = cvPoint2D32f(-vec.y,vec.x);
    rotatedTargetGuess = cvPoint2D32f(firstLine[0].x + newDir.x, firstLine[0].y + newDir.y);
    nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
    CvPoint2D32f *crossingLine = (CvPoint2D32f*)malloc((maxLineCorners + 1) * sizeof(CvPoint2D32f)); 
    baseIndex = [self indexOfPointEqualTo:firstLine[0] inNumber:numCorners ofCvPoints:foundCorners];
    crossingLineLength = [self buildLine:crossingLine fromNumber:numCorners ofPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
    if (crossingLineLength > minLineLength) {
        [self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithNumber:crossingLineLength ofPoints:crossingLine];    
    }    
    // Now, this loop does the remainder of the line.
    for (int i=1; i<lineLength; i++) {
        vec = cvPoint2D32f(firstLine[i].x - firstLine[i-1].x,firstLine[i].y - firstLine[i-1].y);
        newDir = cvPoint2D32f(-vec.y,vec.x);
        rotatedTargetGuess = cvPoint2D32f(firstLine[i].x + newDir.x, firstLine[i].y + newDir.y);
        nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
        CvPoint2D32f *crossingLine = (CvPoint2D32f*)malloc((maxLineCorners + 1) * sizeof(CvPoint2D32f)); 
        baseIndex = [self indexOfPointEqualTo:firstLine[i] inNumber:numCorners ofCvPoints:foundCorners];
        crossingLineLength = [self buildLine:crossingLine fromNumber:numCorners ofPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
        if (crossingLineLength > minLineLength) {
            [self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithNumber:crossingLineLength ofPoints:crossingLine];    
        }
        if (i == floor(lineLength/2.0)) {   // When we get to the middle, store a copy of the middle crossing line to use for generating the ones crossing the crossing lines
            midCrossingLineLength = [self buildLine:midCrossingLine fromNumber:numCorners ofPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
        }
        free(crossingLine);
    }
    
    // Now build the set of crossing lines for the middle crossing line, completing the grid.  We start with the whole block and the indices switched, to catch the first line.
    free(crossingLine);
    vec = cvPoint2D32f(midCrossingLine[0].x - midCrossingLine[1].x,midCrossingLine[0].y - midCrossingLine[1].y);
    newDir = cvPoint2D32f(-vec.y,vec.x);
    rotatedTargetGuess = cvPoint2D32f(midCrossingLine[0].x + newDir.x, midCrossingLine[0].y + newDir.y);
    nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
    crossingLine = (CvPoint2D32f*)malloc((maxLineCorners + 1) * sizeof(CvPoint2D32f)); 
    baseIndex = [self indexOfPointEqualTo:midCrossingLine[0] inNumber:numCorners ofCvPoints:foundCorners];
    crossingLineLength = [self buildLine:crossingLine fromNumber:numCorners ofPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
    if (crossingLineLength > minLineLength) {
        [self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithNumber:crossingLineLength ofPoints:crossingLine];    
    }
    free(crossingLine);    
    
    for (int i=1; i<midCrossingLineLength; i++) {
        vec = cvPoint2D32f(midCrossingLine[i].x - midCrossingLine[i-1].x,midCrossingLine[i].y - midCrossingLine[i-1].y);
        newDir = cvPoint2D32f(-vec.y,vec.x);
        rotatedTargetGuess = cvPoint2D32f(midCrossingLine[i].x + newDir.x, midCrossingLine[i].y + newDir.y);
        nextIndex = [self indexOfNearestPointTo:rotatedTargetGuess inNumber:numCorners ofCvPoints:foundCorners bestDistance:&dummyBestDistance];
        CvPoint2D32f *crossingLine = (CvPoint2D32f*)malloc((maxLineCorners + 1) * sizeof(CvPoint2D32f)); 
        baseIndex = [self indexOfPointEqualTo:midCrossingLine[i] inNumber:numCorners ofCvPoints:foundCorners];
        crossingLineLength = [self buildLine:crossingLine fromNumber:numCorners ofPoints:foundCorners byExtending:baseIndex inDirectionOf:nextIndex];
        if (crossingLineLength > minLineLength) {
            [self.videoClip.project.document.distortionLinesController addNewAutodetectedLineWithNumber:crossingLineLength ofPoints:crossingLine];    
        }
        free(crossingLine);
    }
    
    free(midCrossingLine);
    free(foundCorners);
    free(firstLine);
    cvReleaseImage(&videoFrameIpl);
    cvReleaseImage(&videoFrameSingleChannelIpl);
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
    
    CGImageRef videoFrameCG = [self.videoClip.project.document highQualityStillFromVSVideoClip:self.videoClip atMasterTime:[self.videoClip.project.document currentMasterTime]];
    
    NSPoint snapSearchOrigin = NSMakePoint(clickedPoint.x - snapSearchHalfWidth,([self.videoClip clipHeight] - clickedPoint.y) - snapSearchHalfWidth);
    // NSLog(@"Current origin y is %1.3f, but I would like to try %1.3f",snapSearchOrigin.y,(1920.0-clickedPoint.y)-snapSearchHalfWidth);
    CGRect snapSearchRect = CGRectMake(snapSearchOrigin.x, snapSearchOrigin.y, snapSearchHalfWidth*2, snapSearchHalfWidth*2);
    
    CGImageRef localVideoFrameCG = CGImageCreateWithImageInRect(videoFrameCG,snapSearchRect);
    CFRelease(videoFrameCG);    
    
    IplImage *videoFrameIpl = (IplImage *) [UtilityFunctions CreateIplImageFromCGImage:localVideoFrameCG];
    CFRelease(localVideoFrameCG);
    IplImage* videoFrameSingleChannelIpl = cvCreateImage(cvGetSize(videoFrameIpl), videoFrameIpl->depth, 1);
    cvSetImageCOI(videoFrameIpl, 1);
    cvCopy(videoFrameIpl, videoFrameSingleChannelIpl);
    
    int numCorners = maxNumCorners;  // Max # of corners to find.  On return, it is replaced by the # actually found.
    CvPoint2D32f *foundCorners = (CvPoint2D32f*)malloc((maxNumCorners + 1) * sizeof(CvPoint2D32f)); 
    IplImage *eigImage = cvCreateImage(cvGetSize(videoFrameIpl),IPL_DEPTH_32F, 1);
    IplImage *tempImage = cvCreateImage(cvGetSize(videoFrameIpl),IPL_DEPTH_32F, 1);
    
    // Find the corner positions -- they'll be pretty much the only good "features to track" when the chessboard takes up the entire screen.
    cvGoodFeaturesToTrack(videoFrameSingleChannelIpl, eigImage, tempImage, foundCorners, &numCorners, qualityLevel, minDistance, NULL, 3, 0, 0.04);
    
    // Running cvFindCornerSubPix with a high window size like (15,15) corrected some severe mislocations around one of my squares that (5,5) did not.
    // But (15,15) has some trouble getting drawn off to other things. So trying (10, 10).
    // Only run the subpixel refinement if we're not right on the edge of the image; otherwise it crashes the program from an array size mismatch.

    if (clickedPoint.x > snapSearchHalfWidth && clickedPoint.y > snapSearchHalfWidth && clickedPoint.x < ([self.videoClip clipWidth] - snapSearchHalfWidth) && clickedPoint.y < ([self.videoClip clipWidth] - snapSearchHalfWidth)) {
        cvFindCornerSubPix(videoFrameSingleChannelIpl, foundCorners, numCorners, cvSize(cornerSubPixWindowSize,cornerSubPixWindowSize), cvSize(-1,-1), cvTermCriteria( CV_TERMCRIT_ITER | CV_TERMCRIT_EPS, 20, 0.01 ));
    }

    
    NSPoint snappedPoint = NSMakePoint(snapSearchOrigin.x + foundCorners[0].x,([self.videoClip clipHeight] - (snapSearchOrigin.y + foundCorners[0].y)));

    return snappedPoint;
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
    int totalPointCount = 0; // Total # of points on all plumblines, for use calculating the average remaining distortion per point.
                             // This will double-count screen points used in both horizontal and vertical lines. That is by design.
    for (int i = 0; i < p.numLines; i++) {		
		NSArray *pointsInLine = [[[[plumbLines objectAtIndex:i] distortionPoints] allObjects] sortedArrayUsingDescriptors:[NSArray arrayWithObject:pointIndexSortDescriptor]];
        p.lineLengths[i] = [pointsInLine count];
        totalPointCount += p.lineLengths[i];
        p.lines[i] = (NSPoint *) malloc(p.lineLengths[i]*sizeof(NSPoint));
        for (int j = 0; j < p.lineLengths[i]; j++) p.lines[i][j] = NSMakePoint([[[pointsInLine objectAtIndex:j] screenX] floatValue],[[[pointsInLine objectAtIndex:j] screenY] floatValue]);
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
    x = gsl_vector_alloc(8);             
    gsl_vector_set(x, 0, ([self.videoClip clipWidth]/2.0) / SCALE_FACTOR_X0);       // Initialize the distortion center to be
    gsl_vector_set(x, 1, ([self.videoClip clipHeight]/2.0) / SCALE_FACTOR_Y0);      // at the center of the screen as a first guess
    gsl_vector_set(x, 2, 1.0);
    gsl_vector_set(x, 3, 1.0);
    gsl_vector_set(x, 4, 1.0);
    gsl_vector_set(x, 5, 1.0);
    gsl_vector_set(x, 6, 1.0);    
    gsl_vector_set(x, 7, 1.0);    
    
    /* Set initial step sizes to 1 */
    ss = gsl_vector_alloc(8);            // ss is short for "step sizes"
    gsl_vector_set_all(ss, 0.25);        // I've been getting good results starting with 0.25, so I haven't changed that
    
    /* Initialize method and iterate */
    minex_func.n = 8;                                           // Number of variables being adjusted for the minimization (distortion parameters)
    minex_func.f = orthogonalRegressionTotalCostFunction;       // The cost function to minimize (defined at the top of VSCalibration.mm)
    minex_func.params = &p;                                     // The *params argument of the cost function -- this holds the line data, not the distortion parameters.
    
    s = gsl_multimin_fminimizer_alloc(T, 8);
    gsl_multimin_fminimizer_set(s, &minex_func, x, ss);
    
    double initial_cost_function_value, final_cost_function_value = 0.0;
    
    do {
        iter++;
        status = gsl_multimin_fminimizer_iterate(s);
        if (status) break;
        size = gsl_multimin_fminimizer_size(s);
        status = gsl_multimin_test_size(size, 1e-10);                        // Here we set the minimum characteristic size of the simplex as a possible stopping criterion
        
        // Diagnostic code within the loop -- leave here, commented, in case the function ever gives me problems
         if (status == GSL_SUCCESS || status == GSL_CONTINUE)
         {
             if (iter == 1) initial_cost_function_value = s->fval;
             /*
             NSLog(@"Iteration step: %5d %.3f %.3f %10.5e %10.5e %10.5e %10.5e %10.5e %10.5e Cost Function f() = %7.10f size = %.20f\n",
             (int) iter, gsl_vector_get(s->x, 0) * SCALE_FACTOR_X0, gsl_vector_get(s->x, 1) * SCALE_FACTOR_Y0,gsl_vector_get(s->x, 2) * SCALE_FACTOR_K1,
             gsl_vector_get(s->x, 3) * SCALE_FACTOR_K2,gsl_vector_get(s->x, 4) * SCALE_FACTOR_K3,gsl_vector_get(s->x, 5) * SCALE_FACTOR_P1,gsl_vector_get(s->x, 6) * SCALE_FACTOR_P2,gsl_vector_get(s->x, 7) * SCALE_FACTOR_P3,s->fval,size);
              */
         }
        
    } while (status == GSL_CONTINUE && iter < 2000);                         // Here we set the max # of iterations
    
    final_cost_function_value = s->fval;
    
	self.distortionCenterX = [NSNumber numberWithDouble:gsl_vector_get(s->x, 0) * SCALE_FACTOR_X0];
	self.distortionCenterY = [NSNumber numberWithDouble:gsl_vector_get(s->x, 1) * SCALE_FACTOR_Y0];
    self.distortionK1 = [NSNumber numberWithDouble:gsl_vector_get(s->x, 2) * SCALE_FACTOR_K1];
    self.distortionK2 = [NSNumber numberWithDouble:gsl_vector_get(s->x, 3) * SCALE_FACTOR_K2];
    self.distortionK3 = [NSNumber numberWithDouble:gsl_vector_get(s->x, 4) * SCALE_FACTOR_K3];
    self.distortionP1 = [NSNumber numberWithDouble:gsl_vector_get(s->x, 5) * SCALE_FACTOR_P1];
    self.distortionP2 = [NSNumber numberWithDouble:gsl_vector_get(s->x, 6) * SCALE_FACTOR_P2];
    self.distortionP3 = [NSNumber numberWithDouble:gsl_vector_get(s->x, 7) * SCALE_FACTOR_P3];
    
    self.distortionReductionAchieved = [NSNumber numberWithDouble:(initial_cost_function_value - final_cost_function_value) / initial_cost_function_value];
    self.distortionRemainingPerPoint = [NSNumber numberWithDouble:final_cost_function_value / (double) totalPointCount];
    
    /*
    NSLog(@"Initial cost function value was %1.3f, final is %1.3f, reduction of %1.5f percent. Remaining mean per-point residual is %1.6f pixels.",initial_cost_function_value,final_cost_function_value,100.0*(initial_cost_function_value - final_cost_function_value) / initial_cost_function_value, final_cost_function_value / (double) totalPointCount);
    */
    gsl_vector_free(x);
    gsl_vector_free(ss);
    gsl_multimin_fminimizer_free (s);
    
    for (int i = 0; i < p.numLines; i++) free(p.lines[i]);
    free(p.lines);
    free(p.lineLengths);
 
    self.videoClip.project.distortionDisplayMode = @"Corrected";
    [self.videoClip.windowController refreshOverlay];
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
	NSNumberFormatter *nf = self.videoClip.project.document.decimalFormatter;
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"calibration"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"cameraX" stringValue:[nf stringFromNumber:self.cameraX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"cameraY" stringValue:[nf stringFromNumber:self.cameraY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"cameraZ" stringValue:[nf stringFromNumber:self.cameraZ]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionCenterX" stringValue:[nf stringFromNumber:self.distortionCenterX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionCenterY" stringValue:[nf stringFromNumber:self.distortionCenterY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK1" stringValue:[nf stringFromNumber:self.distortionK1]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK2" stringValue:[nf stringFromNumber:self.distortionK2]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionK3" stringValue:[nf stringFromNumber:self.distortionK3]]];
    [mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionP1" stringValue:[nf stringFromNumber:self.distortionP1]]];
    [mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionP2" stringValue:[nf stringFromNumber:self.distortionP2]]];
    [mainElement addAttribute:[NSXMLNode attributeWithName:@"distortionP3" stringValue:[nf stringFromNumber:self.distortionP3]]];
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


