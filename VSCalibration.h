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


#import <Cocoa/Cocoa.h>
#import "gsl/gsl_multimin.h"
#import "gsl/gsl_multiroots.h"

@class VSVideoClip;
@class VSCalibrationPoint;

/* -----------Code related to C functions for distortion calculations using the GNU Scientific Library ---------------*/

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

typedef struct
{
    NSPoint** lines;
    size_t* lineLengths;
    size_t numLines;
} Plumblines;

double orthogonalRegressionLineCostFunction(NSPoint line[], const size_t numLinePoints);
double orthogonalRegressionTotalCostFunction(const gsl_vector *v, void *params);
NSPoint undistortPoint(const NSPoint* pt, const double x0, const double y0, const double k1, const double k2, const double k3, const double k4, const double k5, const double k6, const double k7, const double p1, const double p2, const double p3, const double p4);
NSPoint redistortPoint(const NSPoint* pt, const double x0, const double y0, const double k1, const double k2, const double k3, const double k4, const double k5, const double k6, const double k7, const double p1, const double p2, const double p3, const double p4);
int redistortionRootFunc_f(const gsl_vector* x, void* params, gsl_vector* f);
int redistortionRootFunc_df(const gsl_vector* x, void* params, gsl_matrix* J);
int redistortionRootFunc_fdf(const gsl_vector* x, void* params, gsl_vector* f, gsl_matrix* J);

/* ------------------------------------The actual VSCalibration class ----------------------------------------------------*/

@interface VSCalibration : NSManagedObject {
    
	// The matrices below can't be made Objective-C 2.0 properties, because C functions (the synthesized accessors) can't return a matrix.  
	// Therefore I have to access them through a pointer passed to the custom accessor as a parameter.
	double matrixQuadratFrontToScreenFCM[9];	// Each of these contains its respective matrix represented as a flattened, 1-dimensional vector in Fortran column-major form
	double matrixQuadratBackToScreenFCM[9];		// for use by Lapack.  These vectors are not stored in Core Data, but are calculated from the Core Data values the first time
	double matrixScreenToQuadratFrontFCM[9];	// they're called for after the project is opened, or when the calibration is recalculated.  The purpose of storing them here
	double matrixScreenToQuadratBackFCM[9];		// is to not waste CPU time reorganizing arrays when doing calculations based on the projection matrices.
		
}

@property (strong) VSVideoClip *videoClip;

@property (strong) NSString *axisHorizontal;
@property (strong) NSString *axisVertical;
@property (strong,readonly) NSString *axisFrontToBack;
@property (strong) NSNumber *planeCoordFront;
@property (strong) NSNumber *planeCoordBack;

@property (strong) NSAttributedString *quadratNodesFront;
@property (strong) NSAttributedString *quadratNodesBack;
@property (strong) NSSet *pointsFront;
@property (strong) NSSet *pointsBack;
@property (strong) NSSet *distortionLines;

@property (strong) NSMutableSet *autodetectedPoints;

@property (strong) NSArray *matrixQuadratFrontToScreen;
@property (strong) NSArray *matrixQuadratBackToScreen;
@property (strong) NSArray *matrixScreenToQuadratFront;
@property (strong) NSArray *matrixScreenToQuadratBack;

@property (strong) NSNumber *cameraX;
@property (strong) NSNumber *cameraY;
@property (strong) NSNumber *cameraZ;
@property (strong) NSNumber *cameraMeanPLD;

@property (strong) NSNumber *residualFrontLeastSquares;
@property (strong) NSNumber *residualBackLeastSquares;
@property (strong) NSNumber *residualFrontPixel;
@property (strong) NSNumber *residualBackPixel;
@property (strong) NSNumber *residualFrontWorld;
@property (strong) NSNumber *residualBackWorld;

@property (strong) NSNumber *distortionCenterX;
@property (strong) NSNumber *distortionCenterY;
@property (strong) NSNumber *distortionK1;
@property (strong) NSNumber *distortionK2;
@property (strong) NSNumber *distortionK3;
@property (strong) NSNumber *distortionK4;
@property (strong) NSNumber *distortionK5;
@property (strong) NSNumber *distortionK6;
@property (strong) NSNumber *distortionK7;
@property (strong) NSNumber *distortionP1;
@property (strong) NSNumber *distortionP2;
@property (strong) NSNumber *distortionP3;
@property (strong) NSNumber *distortionP4;
@property (strong) NSNumber *distortionReductionAchieved;
@property (strong) NSNumber *distortionRemainingPerPoint;

@property (strong) NSNumber *shouldCorrectRefraction;
@property (strong) NSNumber *frontQuadratSurfaceThickness;
@property (strong) NSNumber *frontQuadratSurfaceRefractiveIndex;
@property (strong) NSNumber *mediumRefractiveIndex;

+ (NSSet *) keyPathsForValuesAffectingAxisFrontToBack;
- (NSString *) axisFrontToBack;

- (BOOL) frontIsCalibrated;
- (BOOL) backIsCalibrated;

- (void) resetFrameAndBeginCalibration;
- (void) resetFrontFrameOnly;
- (void) resetBackFrameOnly;
- (void) createPointsFromQuadratDescription:(NSString *)whichSurface;

- (void) saveQuadratDescriptionToFile;
- (void) loadQuadratDescriptionFromFile;
- (void) loadQuadratDescriptionExample;
- (IBAction) export3DCalibrationToFile:(id)sender;
- (IBAction) import3DCalibrationFromFile:(id)sender;
- (IBAction) exportDistortionToFile:(id)sender;
- (IBAction) importDistortionFromFile:(id)sender;

- (void) processClickOnSurface:(NSString *)whichSurface withCoords:(NSPoint)videoCoords;
- (void) calculateCalibration;
- (void) calculatePixelResiduals:(NSString *)whichSurface;
- (void) calculateWorldResiduals:(NSString *)whichSurface;
- (double) leastSquaresResidualWithA:(double*)a_r x:(double[9])x_r rowsA:(int)rowsA;
- (void) calculateCameraPosition;
- (NSArray *) candidateCameraPositionsForRefinement;
- (void) calculateMatrix:(NSString *)whichMatrix correctRefraction:(BOOL)correctRefraction;

+ (void) invert3x3Matrix:(double[9])A;
+ (void) arrange2DArray:(double[][9])A withRows:(int)numRows intoColumnMajorVector:(double[])a;
+ (void) putLeastSquaresSolutionForOverdeterminedSystem:(double[][9])A withRows:(int)numRows intoOutputMatrix:(double[9])x;
+ (void) rightMultiply3x3Matrix:(double[9])A trans:(enum CBLAS_TRANSPOSE)transA by3x3Matrix:(double[9])B trans:(enum CBLAS_TRANSPOSE)transB intoResultingMatrix:(double[9])C;
+ (NSArray *) createMatrixOfNSArraysFromCMatrix:(double[9])p;

- (NSPoint) projectScreenPoint:(NSPoint)screenPoint toQuadratSurface:(NSString *)surface;
- (NSPoint) projectToScreenFromPoint:(NSPoint)quadratPoint onQuadratSurface:(NSString *)surface redistort:(BOOL)redistort;

- (void) autodetectChessboardPlumblines;
- (BOOL) hasDistortionCorrection;
- (NSPoint) distortPoint:(NSPoint)undistortedPoint;
- (NSPoint) undistortPoint:(NSPoint)distortedPoint;
- (void) calculateDistortionCorrection;

- (void) refractionCorrectApparentPositionOfBackQuadratPoint:(VSCalibrationPoint*)point;

- (NSPoint) snapToFeatureNearestToClick:(NSPoint)clickedPoint;

- (void) calculateFCMMatrix:(NSString *)whichSurface;
- (void) putQuadratFrontToScreenFCMMatrixInArray:(double[9])arr;

- (NSXMLNode *) representationAsXMLNode;
- (NSString *) matrixAsOutputString:(NSArray *)matrix;  // Formats matrices for output with the XML nodes

@end
