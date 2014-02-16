//
//  VSHintLine.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/25/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VSHintLine.h"


@implementation VSHintLine

@dynamic frontSurfaceX;
@dynamic frontSurfaceY;
@dynamic backSurfaceX;
@dynamic backSurfaceY;
@dynamic fromScreenPoint;
@dynamic toVideoClip;

+ (void) createHintLineFromScreenPoint:(VSEventScreenPoint *)screenPoint toVideoClip:(VSVideoClip *)videoClip
{
	// Convert the clicked screen coordinates into front and back face quadrat coordinates, using screenPoint's videoClip's calibration.	
	NSPoint screenPoint2D = NSMakePoint([screenPoint.screenX doubleValue],[screenPoint.screenY doubleValue]);
	NSPoint frontQuadratCoords = [screenPoint.videoClip.calibration projectScreenPoint:screenPoint2D toQuadratSurface:@"Front"];
	NSPoint backQuadratCoords = [screenPoint.videoClip.calibration projectScreenPoint:screenPoint2D toQuadratSurface:@"Back"];
		
	VSHintLine *hintLine = [NSEntityDescription insertNewObjectForEntityForName:@"VSHintLine" inManagedObjectContext:[screenPoint managedObjectContext]]; 
	
	// should rename these attributes to quadratFrontX, quadratFrontY, quadratBackX, quadratBackY in the data model, and store those... but figure out how I unpack that line first
	hintLine.frontSurfaceX = [NSNumber numberWithFloat:frontQuadratCoords.x];
	hintLine.frontSurfaceY = [NSNumber numberWithFloat:frontQuadratCoords.y];
	hintLine.backSurfaceX = [NSNumber numberWithFloat:backQuadratCoords.x];
	hintLine.backSurfaceY = [NSNumber numberWithFloat:backQuadratCoords.y];
	hintLine.fromScreenPoint = screenPoint;
	hintLine.toVideoClip = videoClip;
}

- (NSBezierPath *) bezierPathForLineWithInterval:(float)interval	// returns a bezierpath for the hintline in the current overlay coordinates of this hintLine's toVideoClip
{
    
    // A note about the algorithm for calculating hint lines:  It would seem to make more intuitive sense to calculate hint lines by taking 3-D points at intervals up and down the first line-of-sight, 
    // then converting each of those 3-D points into a screen coordinate from the other screen, and undistorting.  Instead, we convert only two points, the quadrat intercepts, and then extend a 2-D line
    // between them in the other camera's screen coordinates, and undistort points at intervals along that line.  This results in hint lines with fewer coordinates, because equal intervals on a 3-D line
    // would translate to very small intervals on the screen as the line extends far away from the camera, and would make bezier paths with very long coordinate lists.  However, it's less intuitive why
    // this would be correct at all.  
    
	NSPoint frontQuadratCoords = NSMakePoint([self.frontSurfaceX floatValue],[self.frontSurfaceY floatValue]);
	NSPoint backQuadratCoords = NSMakePoint([self.backSurfaceX floatValue],[self.backSurfaceY floatValue]);
	
	// Project the front & back quadrat coords into undistorted "screen" coordinates, in which the hint line coordinates can be calculated as a straight line
	NSPoint frontScreenCoordsUndistorted = [self.toVideoClip.calibration projectToScreenFromPoint:frontQuadratCoords onQuadratSurface:@"Front" redistort:NO];
	NSPoint backScreenCoordsUndistorted = [self.toVideoClip.calibration projectToScreenFromPoint:backQuadratCoords onQuadratSurface:@"Back" redistort:NO];
	
	// get m and b for the line y = mx + b describing the undistorted hintline
	float m = (frontScreenCoordsUndistorted.y - backScreenCoordsUndistorted.y) / (frontScreenCoordsUndistorted.x - backScreenCoordsUndistorted.x);
	float b = frontScreenCoordsUndistorted.y - m*frontScreenCoordsUndistorted.x;
	
	// generate points on that line at regular intervals in both the x and y directions
	float xLimit = self.toVideoClip.windowController.movieSize.width;
	float yLimit = self.toVideoClip.windowController.movieSize.height;
    float tempx, tempy;
	NSMutableArray *distortedPoints = [NSMutableArray new];
	float padding = 4.0*interval;	// pixel padding to extend the drawn line a bit beyond the bounds of the frame
	for (float x = -padding; x <= xLimit+padding; x += interval) {
        tempy = m*x+b;
        if (tempy >= -padding && tempy <= yLimit + padding) {
            [distortedPoints addObject:[NSValue valueWithPoint:[self.toVideoClip.calibration distortPoint:NSMakePoint(x,tempy)]]];  // regular intervals in the x direction
        }
	}
	for (float y = -padding; y <= yLimit+padding; y += interval) {
        tempx = (y-b)/m;
        if (tempx >= -padding && tempx <= xLimit + padding) {
            [distortedPoints addObject:[NSValue valueWithPoint:[self.toVideoClip.calibration distortPoint:NSMakePoint(tempx,y)]]];	// regular intervals in the y direction	
        }
	}
	
    // sort them by x coordinate
	[distortedPoints sortUsingComparator:(NSComparator)^(id obj1, id obj2){
		NSComparisonResult result;
			if ([obj1 pointValue].x > [obj2 pointValue].x) {
				result = NSOrderedAscending;
			} else if ([obj1 pointValue].x == [obj2 pointValue].x) {
				result = NSOrderedSame;
			} else {
				result = NSOrderedDescending;
			}
		return result;
		}];
	
	// create and return the bezierpath
	NSPoint distortedPoint,overlayPoint;
	NSBezierPath *hintLinePath = [NSBezierPath bezierPath];
	[hintLinePath setLineJoinStyle:NSRoundLineJoinStyle];
	int numSegments = 0;
	NSRect drawRegionRect = NSInsetRect([self.toVideoClip.windowController.overlayView frame],-padding,-padding);	// "insets" the visible rect by a negative number to draw slightly past screen edges
	for (NSValue *distortedPointValue in distortedPoints) {
		distortedPoint = [distortedPointValue pointValue];
		overlayPoint = [self.toVideoClip.windowController convertVideoToOverlayCoords:distortedPoint];
		if (NSPointInRect(overlayPoint,drawRegionRect)) {
			if (numSegments == 0) {
				[hintLinePath moveToPoint:overlayPoint];			// if it's the first point in the line, just move to it
			} else {
				[hintLinePath lineToPoint:overlayPoint];			// otherwise, draw from the previous point to this one
			}
			numSegments += 1;
		}
	}
	if (numSegments > 0) {
		return hintLinePath;
	} else {
		return nil;
	}
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


@end
