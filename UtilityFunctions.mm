//
//  UtilityFunctions.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/23/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "opencv2/opencv.hpp"

#import "UtilityFunctions.h"

@implementation UtilityFunctions

+ (NSColor *) userDefaultColorForKey:(NSString *)key
{
    // I sometimes get strange exceptions unpacking colors ([NSUnarchiver initForReadingWithData:] complains about a nil argument with NSInvalidArgumentException) so I'm handling them here
    NSColor *color;
    @try {
        color = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:key]];
    } @catch (NSException *e) {
        NSLog(@"Error unarchiving user defaults color value for key %@. Using red instead. Exception was: %@",key,e);
        color = [NSColor redColor];
    } @finally {
        return color;
    }
}


+ (NSString *) CMStringFromTime:(CMTime)time onScale:(int32_t)timeScale
{
    CMTime scaledTime = CMTimeConvertScale(time,timeScale,kCMTimeRoundingMethod_RoundHalfAwayFromZero);
    int64_t scaledTimeValue = scaledTime.value;
    QTTime qtTime = QTMakeTime(scaledTimeValue,timeScale);
    return QTStringFromTime(qtTime);
}

+ (NSString *) CMStringFromTime:(CMTime)time // I have to use QTTime functions for now to encode/decode times as strings for backward compatibility with files that stored times as strings in Core Data.
                                            // The modern way to do it would be to store the times as dictonaries using CMTimeMakeFromDictiory and CMTimeCopyAsDictionary, but backward compatability would be annoying.
                                            // This time thing should be the only reason I still have QTKit included in this project, eventually. I'll have to code the string conversions from scratch to eliminate QTKit.
{
    long long timeValue = (long long) time.value;
    long timeScale = (long) time.timescale;
    QTTime qtTime = QTMakeTime(timeValue,timeScale);
    return QTStringFromTime(qtTime);
}

+ (CMTime) CMTimeFromString:(NSString *)timeString; // This one also uses QTKit
{
    QTTime rawTime = QTTimeFromString(timeString);
	if ([timeString characterAtIndex:0] == '-') {
		QTTime zero = QTMakeTime(0,rawTime.timeScale);
		NSComparisonResult rawTimeComparedWithZero = QTTimeCompare(rawTime,zero);
		if (rawTimeComparedWithZero == NSOrderedDescending) {	// if QTTimeFromString returned a positive time from a negative string, fix it and return it.  
			QTTime decrementedTime = QTTimeDecrement(zero,rawTime);
            return CMTimeMake((int64_t) decrementedTime.timeValue, (int32_t) decrementedTime.timeScale);
		}
	}
    return CMTimeMake((int64_t) rawTime.timeValue, (int32_t) rawTime.timeScale);
}

+ (QTTime) FixedQTMakeTimeScaled:(QTTime)inTime scale:(long)timeScale	// Fixes another bug in Quicktime, in which QTMakeTimeScaled comes up 1 short of the timeValue it should
{	
	long double newTimeDouble = ((long double) inTime.timeValue / (long double) inTime.timeScale) * (long double) timeScale;
	long long newTimeLongLong = llroundl(newTimeDouble);	// original QTTime just casts it to double, which is in effect floor() instead of round()
	return QTMakeTime(newTimeLongLong,timeScale);
}


+ (NSPoint) project2DPoint:(NSPoint)pt usingMatrix:(double[9])A
{
	CBLAS_ORDER Order = CblasColMajor;			// passing the matrix A in the column-major form native to the Fortran function
	CBLAS_TRANSPOSE TransA = CblasNoTrans;		// don't do any transposing or anything with A
	int M = 3;						// rows in the matrix A
	int N = 3;						// columns in the matrix A
	double alpha = 1.0;				// scaler multiplier for A, set to 1.0 for no effect
	int lda = 3;					// the leading dimension of A
	double X[3] = {pt.x,pt.y,1.0};	// the screen coordinates x, expressed as homogeneous coordinates by adding the 3rd element 1.0
	int incX = 1;					// increment for X, should always be 0 in my case
	double beta = 0.0;				// scalar multiplier for y's initial value; set to 0 for this simple multiplication
	double Y[3];					// vector to hold the results of the computation
	int incY = 1;					// increment for Y, should always be 1 in my case
	cblas_dgemv(Order, TransA, M, N, alpha, A, lda, X, incX, beta, Y, incY);	// Compute the homogeneous 2D quadrat coordinates
	return NSMakePoint(Y[0]/Y[2],Y[1]/Y[2]);
}

+ (VSPoint3D) intersectionOfLine:(VSLine3D)line withPlaneDefinedByPoints:(VSPoint3D[3])pointsInPlane
{
	// Finds the point at which the given line in 3D space intersects the plane defined by the 3 3D points given in pointsInPlane
	// Set up the system of equations Ax=b described for the Parametric form on the Wikipedia page for "Line-plane intersection"
	// Source for the math:  http://en.wikipedia.org/wiki/Line-plane_intersection
	
	__CLPK_doublereal b[3] = {line.front.x - pointsInPlane[0].x,line.front.y - pointsInPlane[0].y,line.front.z - pointsInPlane[0].z};
	__CLPK_doublereal A[9];	// Elements of the matrix A, being filled in in Fortran column-major form
	A[0] = line.front.x - line.back.x;
	A[1] = line.front.y - line.back.y;
	A[2] = line.front.z - line.back.z;
	A[3] = pointsInPlane[1].x - pointsInPlane[0].x;
	A[4] = pointsInPlane[1].y - pointsInPlane[0].y;
	A[5] = pointsInPlane[1].z - pointsInPlane[0].z;
	A[6] = pointsInPlane[2].x - pointsInPlane[0].x;
	A[7] = pointsInPlane[2].y - pointsInPlane[0].y;
	A[8] = pointsInPlane[2].z - pointsInPlane[0].z;
	
	// Use Lapack's dgesv routine to solve the system Ax=b for x.

	__CLPK_integer n = 3;								// Number of linearly independent rows in the matrix A
	__CLPK_integer nrhs = 1;							// Number of columns of the matrix b (1, of course)
	__CLPK_integer lda = 3;								// Leading dimension of the matrix A
	__CLPK_integer ipiv[3];								// Output parameter, the pivot indices of the permutation matrix used for the solution
	__CLPK_integer ldb = 3;								// Leading dimension of the matrix b
	__CLPK_integer info;								// Output parameter: if 0, success; if -i, ith argument had illegal value; if >0, solution not computable
	dgesv_(&n, &nrhs, A, &lda, ipiv, b, &ldb, &info);	// On output, the variable b contains the solution x.
	
	double t = b[0];	// The first element of b should be the scaling parameter t for t he parametric equation
	
	VSPoint3D intersection;
	intersection.x = line.front.x + (line.back.x - line.front.x) * t;
	intersection.y = line.front.y + (line.back.y - line.front.y) * t;
	intersection.z = line.front.z + (line.back.z - line.front.z) * t;
	return intersection;
}


+ (VSPoint3D) intersectionOfNumber:(int)numLines of3DLines:(VSLine3D[])lines meanPLD:(double *)meanPLD
{
	// This calculates the closest point of approach of an arbitrary number of 3D lines.  The formula comes from Wikipedia.
    // It's the last formula on this page: http://en.wikipedia.org/wiki/Line-line_intersection
    
    // I need to first loop through and calculate the CPA.
    // Then, I can loop through the lines one by one and calculate their distances from the CPA, and average those to get the error index.
    
    double I_vvt[9] = {0,0,0,0,0,0,0,0,0};      // 3x3 matrix (as a row-by-row 9 vector) holding the running total of I_3x3 - v_i * Transpose(v_i)
    double I_vvtp[3] = {0,0,0};                 // 3-vector holding the running total of (I_3x3 - v_i * Transpose(v_i)).p
    double p[3];
    double v[3],d[3],dnorm;
    double A[9];
    double CPAvect[3];                          // Holds the answer to the closest point of approach (CPA), our estimate of the lines' intersection.
    VSPoint3D CPA;                              // Holds the answer as above but in a VSPoint3D struct    
    
    // This loops over all lines keeping a running total of I - vvT, and (I - vvT)p and adds to them for every line.
    
    for (int i=0; i<numLines; i++) {
        d[0] = lines[i].back.x - lines[i].front.x;  // d is a vector along the ith line
        d[1] = lines[i].back.y - lines[i].front.y;
        d[2] = lines[i].back.z - lines[i].front.z;
        dnorm = cblas_dnrm2(3,d,1);
        v[0] = d[0]/dnorm;                          // v is a unit vector along the ith line
        v[1] = d[1]/dnorm;
        v[2] = d[2]/dnorm;
        A[0] = 1;                                   // reset A to the identity matrix each time; it will be overwritten with the result of the calculation
        A[1] = 0;
        A[2] = 0;
        A[3] = 0;
        A[4] = 1;
        A[5] = 0;
        A[6] = 0;
        A[7] = 0;
        A[8] = 1;
                
        cblas_dger(CblasColMajor,3,3,-1.0,v,1,v,1,A,3);
        
        for (int j=0; j<9; j++) {
            I_vvt[j] += A[j];                     // add the result of the calculation for I - v*Transpose(v) into the overall storage array before repeating the loop for other lines
        }
        p[0] = lines[i].front.x;
        p[1] = lines[i].front.y;
        p[2] = lines[i].front.z;

        cblas_dgemv(CblasColMajor, CblasNoTrans, 3, 3, 1.0, A, 3, p, 1, 1.0, I_vvtp, 1);	// This one line this line's values to the total of (I_3x3 - v_i * Transpose(v_i)).p     

    }

    [VSCalibration invert3x3Matrix:I_vvt];  // Overwrites I_vvt with its inverse, using Lapack's dgetrf and dgetri functions.
    
    cblas_dgemv(CblasColMajor, CblasNoTrans, 3, 3, 1.0, I_vvt, 3, I_vvtp, 1, 0, CPAvect, 1);	// Multiplies the 3-vector I_vvtp by the 3x3 inverse of I_vvt to store the final result in CPAvect   
    
    CPA.x = CPAvect[0];
    CPA.y = CPAvect[1];
    CPA.z = CPAvect[2];
    
    // Now the CPA calculation is completed; time to calculate the error estimate.

    double totalPLD = 0.0;  // Holds total point-line distance (PLD) from all the lines to their CPA
    for (int i=0; i<numLines; i++) {
        totalPLD += [UtilityFunctions distanceOfPoint:CPA fromLine:lines[i]];
    }
    *meanPLD = totalPLD / numLines;

	return CPA;
}

+ (double) distanceOfPoint:(VSPoint3D)point fromLine:(VSLine3D)line;
{
    // This function calculates the distance between a 3-D line and a 3-D point, using equation (6) from Mathworld's Point-Line Distance 3D page, 
    // which is located here:  http://mathworld.wolfram.com/Point-LineDistance3-Dimensional.html
    // I use that equation rather than the shorter-form last one (equation 11) because there's no BLAS or Lapack function for the vector cross product.
    
    double x1_x0[3] = {line.front.x - point.x, line.front.y - point.y, line.front.z - point.z};
    double x2_x1[3] = {line.back.x - line.front.x, line.back.y - line.front.y, line.back.z - line.front.z};
    double x1_x0_nrm = cblas_dnrm2(3,x1_x0,1);
    double x2_x1_nrm = cblas_dnrm2(3,x2_x1,1);
    double dotprod = cblas_ddot(3, x1_x0, 1, x2_x1, 1);
    double dsquared = (x1_x0_nrm * x1_x0_nrm * x2_x1_nrm * x2_x1_nrm - dotprod*dotprod) / (x2_x1_nrm*x2_x1_nrm);
    return sqrt(dsquared);
}


+ (VSPointPair2D) extendLine:(VSPointPair2D)lineSegment toFillFrameOfClip:(VSVideoClip *)videoClip didFitInFrame:(bool *)didFit;
{ 
	// Extends the line by putting it in slope-intercept form y = mx + b and solving for intersections with the video edges
	// It won't work if any of the lines being extended are 100% parallel to the video edges, but that shouldn't come up in practice in this program.
	NSSize movieSize = videoClip.windowController.movieSize;
	NSPoint p1 = lineSegment.p1;
	NSPoint p2 = lineSegment.p2;
	double m = (p2.y - p1.y) / (p2.x - p1.x);
	double b = p1.y - m * p1.x;
	// Find the four crossing points at which the line being extended should cross the lines including and extending from the movie edges.
	NSPoint c1 = NSMakePoint(movieSize.width,m*movieSize.width+b);
	NSPoint c2 = NSMakePoint(0.0,b);
	NSPoint c3 = NSMakePoint((movieSize.height-b)/m,movieSize.height);
	NSPoint c4 = NSMakePoint(-b/m,0.0);
	// Only two of those crossings should be within the boundary of the movie rectangle.  Find those two and add them to an array.
	NSPoint c[2];
	int i = 0;
	if (c1.y >= 0 && c1.y <= movieSize.height) {c[i] = c1; i += 1;};
	if (c2.y >= 0 && c2.y <= movieSize.height) {c[i] = c2; i += 1;};
	if (c3.x >= 0 && c3.x <= movieSize.width) {c[i] = c3; i += 1;};
	if (c4.x >= 0 && c4.x <= movieSize.width) {c[i] = c4; i += 1;};
	if (i == 2) {														// If we found exactly 2 crossings, all is good; format and return result.
		*didFit = YES;
		VSPointPair2D newLineSegment;
		newLineSegment.p1 = c[0];
		newLineSegment.p2 = c[1];
		return newLineSegment;
	} else {	// If the line segment doesn't cross into the clip's frame at all, just return the segment
		*didFit = NO;
		return lineSegment;
	}
}

+ (float) randomFloatBetween:(float)float1 and:(float)float2
{
	double arc4random_max = 0x100000000;
	return ((float) arc4random() / (float) arc4random_max) * (float2 - float1) + float1;
}

+ (NSString *)stringFromMatrix:(double[])M withRows:(int)numRows andCols:(int)numCols
{
	// Prints a matrix in normal readable 2D row-major form, based on the input matrix represented in the 1D column-major form used for blas and lapack
	NSMutableString *str = [NSMutableString stringWithString:@"\n"];
	for (int i=0; i<numRows; i++) {
		for (int j=0; j<numCols; j++) {
			[str appendFormat:@"%1.4f   ",M[j*numRows+i]];
		}
		[str appendString:@"\n"];
	}
	return str;
}

#pragma mark Helpers for OpenCV

// These IplImage<-->CGImage conversion functions are adapted from http://niw.at/articles/2009/03/14/using-opencv-on-iphone/en

// NOTE you SHOULD cvReleaseImage() for the return value when end of the code.
+ (void *)CreateIplImageFromCGImage:(CGImageRef)imageRef {
    
    CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
    // Creating temporal IplImage for drawing
    IplImage *iplimage = cvCreateImage(
                                       cvSize(CGImageGetWidth(imageRef), CGImageGetHeight(imageRef)), IPL_DEPTH_8U, 4
                                       );
    // Creating CGContext for temporal IplImage
    CGContextRef contextRef = CGBitmapContextCreate(
                                                    iplimage->imageData, iplimage->width, iplimage->height,
                                                    iplimage->depth, iplimage->widthStep,
                                                    colorSpace, kCGImageAlphaPremultipliedLast|kCGBitmapByteOrderDefault
                                                    );
    // Drawing CGImage to CGContext
    CGContextDrawImage(
                       contextRef,
                       CGRectMake(0, 0, CGImageGetWidth(imageRef), CGImageGetHeight(imageRef)),
                       imageRef
                       );
    CGContextRelease(contextRef);
    CGColorSpaceRelease(colorSpace);
    
    // Creating result IplImage
    IplImage *ret = cvCreateImage(cvGetSize(iplimage), IPL_DEPTH_8U, 3);    // changing this from 3 channels to 1, just for now
    cvCvtColor(iplimage, ret, CV_RGBA2BGR);
    cvReleaseImage(&iplimage);
    return ret;
}

// NOTE You should convert color mode as RGB before passing to this function

+ (CGImageRef)CGImageFromIplImage:(void *)imageAsVoid {
    IplImage *image = (IplImage *) imageAsVoid;
    CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
    // Allocating the buffer for CGImage
    NSData *data =
    [NSData dataWithBytes:image->imageData length:image->imageSize];
    CGDataProviderRef provider =
    CGDataProviderCreateWithCFData((__bridge CFDataRef)data);
    // Creating CGImage from chunk of IplImage
    CGImageRef imageRef = CGImageCreate(
                                        image->width, image->height,
                                        image->depth, image->depth * image->nChannels, image->widthStep,
                                        colorSpace, kCGImageAlphaNone|kCGBitmapByteOrderDefault,
                                        provider, NULL, false, kCGRenderingIntentDefault
                                        );
    CGDataProviderRelease(provider);
    CGColorSpaceRelease(colorSpace);
    return imageRef;
}

@end
