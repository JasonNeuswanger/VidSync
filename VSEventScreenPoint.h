//
//  VSEventScreenPoint.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/18/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class VSVideoClip;
@class VSPoint;

NSPoint quadratCoords2Dfrom3D(const VSPoint3D *quadratCoords3D, const char axisHorizontal, const char axisVertical);

@interface VSEventScreenPoint : NSManagedObject {
	
}

@property (strong) NSNumber *screenX;
@property (strong) NSNumber *screenY;
@property (strong) VSVideoClip *videoClip;
@property (strong) VSPoint *point;
@property (strong) NSSet *screenPoints;
@property (strong) NSSet *hintLinesOut;
@property (assign) float tempOpacity;

- (VSLine3D) computeLine3D:(BOOL)useReprojectedPoints;
- (void) calculateHintLines;
- (void) putPointsInFrontQuadratPlaneIntoArray:(VSPoint3D[3])quadratPlanePoints;
- (NSPoint) reprojectedScreenPoint:(bool)shouldRedistort;
- (NSString *) spreadsheetFormattedScreenPoint;
- (NSXMLNode *) representationAsXMLNode;
- (NSPoint) undistortedCoords;

@end
