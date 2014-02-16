//
//  VSPoint.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/18/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

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
	
	NSMapTable *pointToPointDistanceCache;
	
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
- (BOOL) has3Dcoords;
- (NSNumber *) distanceToVSPoint:(VSPoint *)otherPoint;
- (VSEventScreenPoint *) screenPointForVideoClip:(VSVideoClip *)videoClip;
- (NSSet *) calibratedScreenPoints;
- (void) calculate3DCoords;
- (VSPoint3D) calculate3DCoordsLinear;
- (void) handleScreenPointChange;

- (NSString *) spreadsheetFormatted3DPoint;
- (NSXMLNode *) representationAsXMLNode;

@end
