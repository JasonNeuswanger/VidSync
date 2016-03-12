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
@class VSTrackedEvent;
@class VSEventScreenPoint;
@class VSVideoClip;

typedef struct
{
    VSPoint3D* camPositions;
    double **quadratFrontToScreenFCMMatrices;
    VSPoint3D **frontFacePlanes;
    NSPoint *undistortedScreenPoints;
    char* axesHorizontal;
    char* axesVertical;
    size_t numCameras;
} VSPointSolverParams;

double pointSolverCostFunction_f(const gsl_vector* x, void* params);
VSPoint3D linePlaneIntersect(VSLine3D line, VSPoint3D pointsInPlane[3]);
NSPoint project2DPoint(NSPoint pt, double projectionMatrix[9]);

@interface VSPoint : NSManagedObject {
	
	NSMapTable *__strong pointToPointDistanceCache;
	
}

@property (strong) NSNumber *index;
@property (strong) NSString *timecode;
@property (strong) NSNumber *worldX;
@property (strong) NSNumber *worldY;
@property (strong) NSNumber *worldZ;
@property (strong) NSNumber *meanPLD;
@property (strong) NSSet *screenPoints;
@property (strong) NSNumber *reprojectionErrorNorm;
@property (strong) VSTrackedEvent *trackedEvent;

- (void) clearPointToPointDistanceCache;
- (NSString *) screenPointsString;
- (NSString *) calibrationFramePointsString;
- (BOOL) has3Dcoords;
- (NSNumber *) distanceToVSPoint:(VSPoint *)otherPoint;
- (NSNumber *) speedToVSPoint:(VSPoint *)otherPoint; // magnitude of the velocity vector from this point to the otherPoint
- (VSEventScreenPoint *) screenPointForVideoClip:(VSVideoClip *)videoClip;
- (NSSet *) calibratedScreenPoints;
- (void) calculate3DCoords;
- (VSPoint3D) calculate3DCoordsLinear;
- (void) handleScreenPointChange;

- (NSString *) spreadsheetFormatted3DPoint:(NSString *)separator;
- (NSXMLNode *) representationAsXMLNode;

@end
