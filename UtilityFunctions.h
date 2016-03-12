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


//#import "opencv2/opencv.hpp"

#import <Cocoa/Cocoa.h>

@class VSVideoClip;

typedef struct {
	double x;
	double y;
	double z;
} VSPoint3D;

typedef struct {
	VSPoint3D front;	// Lines in this program are typically actually line segments with a 'front' end on the front calibration frame face
	VSPoint3D back;		// and a 'back' end on the back calibration frame face.
} VSLine3D;

typedef struct {		// Creates a pair of 2D points, which can be used to represent a 2D line or not.
	NSPoint p1;		
	NSPoint p2;		
} VSPointPair2D;


@interface UtilityFunctions : NSObject {
	
}

+ (NSColor *) userDefaultColorForKey:(NSString *)key;

+ (BOOL) ConfirmAction:(NSString *)userMessage;
+ (void) InformUser:(NSString *)userMessage;

+ (BOOL) timeString:(NSString *)timeString1 isEqualToTimeString:(NSString *)timeString2;
+ (BOOL) time:(CMTime)time1 isEqualToTime:(CMTime)time2;
+ (NSString *) CMStringFromTime:(CMTime)time;
+ (NSString *) CMStringFromTime:(CMTime)time onScale:(int32_t)timeScale;
+ (CMTime) CMTimeFromString:(NSString *)timeString;
+ (QTTime) FixedQTMakeTimeScaled:(QTTime)inTime scale:(long)timeScale;
+ (NSPoint) project2DPoint:(NSPoint)pt usingMatrix:(double[9])A;
+ (VSPoint3D) intersectionOfLine:(VSLine3D)line withPlaneDefinedByPoints:(VSPoint3D[3])pointsInPlane;

+ (VSPoint3D) intersectionOfNumber:(int)numLines of3DLines:(VSLine3D[])lines meanPLD:(double *)meanPLD;
+ (double) distanceOfPoint:(VSPoint3D)point fromLine:(VSLine3D)line;

+ (VSPointPair2D) extendLine:(VSPointPair2D)lineSegment toFillFrameOfClip:(VSVideoClip *)videoClip didFitInFrame:(bool *)didFit;
+ (float) randomFloatBetween:(float)float1 and:(float)float2;
+ (NSString *)stringFromMatrix:(double[])M withRows:(int)numRows andCols:(int)numCols;

+ (NSString *)sanitizeFileNameString:(NSString *)fileName;

+ (void *)CreateIplImageFromCGImage:(CGImageRef)imageRef;   // returns an IplImage ; can't use that c++ type in a .c header though
+ (CGImageRef)CGImageFromIplImage:(void *)imageAsVoid;

+(NSManagedObject *) Clone:(NSManagedObject *)source inContext:(NSManagedObjectContext *)context deep:(BOOL)deep;


@end
