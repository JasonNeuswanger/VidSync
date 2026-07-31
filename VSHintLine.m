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
	
	// Walk the undistorted line at regular intervals, redistorting each sample as we go.
	//
	// This used to be done with two loops, one stepping in x and one stepping in y, whose outputs were merged by
	// sorting the redistorted points by their x coordinate. That sort is only correct for lines that are more
	// horizontal than vertical. Redistortion moves x non-monotonically along a steep line: the radial correction
	// is weakest far from the distortion centre, so a near-vertical line's redistorted x swings out and back,
	// peaking where the line passes closest to the centre. Sorting by x then interleaves points from opposite
	// ends of the line and the path zigzags across the frame. On the 1080p wide-angle footage that turned this
	// up, the path stayed clean out to a slope of about 3 and then came apart: 33 direction reversals at slope
	// 5, and 99 reversals with 1600-pixel jumps at slope 30, with 40% of that project's hint lines steeper than
	// 3. That is the "janky"/doubled hint line this method carried a note about, and it explains why shrinking
	// the interval appeared to help: it made each fold shorter without removing any.
	//
	// Stepping along the line's own parameter keeps the samples in path order by construction. It also removes
	// the need for a separate vertical-line case, and the duplicate coverage the two loops produced on diagonals.

	float xLimit = self.toVideoClip.windowController.movieSize.width;
	float yLimit = self.toVideoClip.windowController.movieSize.height;
	NSMutableArray *distortedPoints = [NSMutableArray new];
	float padding = 50.0*interval;	// pixel padding to extend the drawn line a bit beyond the bounds of the frame
	// a padding value of '4' worked fine for normal lenses but a much higher value is required to accomodate fisheyes
	// going too high, however, ends up confusing the reverse distortion solver on outlandish solutions and lines get messed up
	// 100 worked fine for most videos but had problems in some places on an 8 mm fisheye video
	// 50 isn't without issues but it's a good compromise between not extending lines far enough and making them buggy/jagged

	double dirX = frontScreenCoordsUndistorted.x - backScreenCoordsUndistorted.x;
	double dirY = frontScreenCoordsUndistorted.y - backScreenCoordsUndistorted.y;
	double dirNorm = sqrt(dirX*dirX + dirY*dirY);
	if (dirNorm < 1e-9) return nil;		// both quadrat intercepts project to the same place, so there is no line of sight to draw
	dirX /= dirNorm;
	dirY /= dirNorm;

	// Clip the infinite line to the padded drawing box to get the range of t worth sampling, where the point at
	// parameter t is backScreenCoordsUndistorted + t*(dirX,dirY). t is in undistorted pixels along the line.
	const double boxMinX = -padding, boxMaxX = xLimit + padding;
	const double boxMinY = -padding, boxMaxY = yLimit + padding;
	double tMin = -INFINITY, tMax = INFINITY;
	if (fabs(dirX) < 1e-12) {			// exactly vertical: the x slab bounds no t, but the line still has to lie inside it
		if (backScreenCoordsUndistorted.x < boxMinX || backScreenCoordsUndistorted.x > boxMaxX) return nil;
	} else {
		double tA = (boxMinX - backScreenCoordsUndistorted.x) / dirX;
		double tB = (boxMaxX - backScreenCoordsUndistorted.x) / dirX;
		tMin = MAX(tMin, MIN(tA,tB));
		tMax = MIN(tMax, MAX(tA,tB));
	}
	if (fabs(dirY) < 1e-12) {			// exactly horizontal, likewise
		if (backScreenCoordsUndistorted.y < boxMinY || backScreenCoordsUndistorted.y > boxMaxY) return nil;
	} else {
		double tA = (boxMinY - backScreenCoordsUndistorted.y) / dirY;
		double tB = (boxMaxY - backScreenCoordsUndistorted.y) / dirY;
		tMin = MAX(tMin, MIN(tA,tB));
		tMax = MIN(tMax, MAX(tA,tB));
	}
	if (tMin > tMax) return nil;		// the line never enters the drawing box

	// A sample the redistortion cannot represent is recorded as NSNull so the drawn path breaks there instead of
	// connecting across the gap. The padded sampling box reaches well past the region a strongly curved lens can
	// actually image, and the alternative to a break is a straight chord to the far side of the gap, which looks
	// exactly like a real hint line and is not one.
	for (double t = tMin; t <= tMax; t += interval) {
		NSPoint undistorted = NSMakePoint(backScreenCoordsUndistorted.x + t*dirX, backScreenCoordsUndistorted.y + t*dirY);
		NSPoint redistorted;
		if ([self.toVideoClip.calibration distortPoint:undistorted toPoint:&redistorted]) {
			[distortedPoints addObject:[NSValue valueWithPoint:redistorted]];
		} else {
			[distortedPoints addObject:[NSNull null]];
		}
	}
	if (fmod(tMax - tMin, interval) > 0.0) {	// the loop stops short of tMax unless the range is an exact multiple of the interval
		NSPoint lastUndistorted = NSMakePoint(backScreenCoordsUndistorted.x + tMax*dirX, backScreenCoordsUndistorted.y + tMax*dirY);
		NSPoint lastRedistorted;
		if ([self.toVideoClip.calibration distortPoint:lastUndistorted toPoint:&lastRedistorted]) [distortedPoints addObject:[NSValue valueWithPoint:lastRedistorted]];
	}

	// create and return the bezierpath
	NSPoint distortedPoint,overlayPoint;
	NSBezierPath *hintLinePath = [NSBezierPath bezierPath];
	[hintLinePath setLineJoinStyle:NSLineJoinStyleRound];
	int numSegments = 0;
	BOOL penIsDown = NO;		// whether the previous sample was drawable, and so whether to line to this one or move to it
	NSRect drawRegionRect = NSInsetRect([self.toVideoClip.windowController.overlayView frame],-padding,-padding);	// "insets" the visible rect by a negative number to draw slightly past screen edges
	for (id entry in distortedPoints) {
		if (entry == [NSNull null]) {			// no valid redistorted position here, so end the current run
			penIsDown = NO;
			continue;
		}
		distortedPoint = [(NSValue *)entry pointValue];
		overlayPoint = [self.toVideoClip.windowController convertVideoToOverlayCoords:distortedPoint];
		if (NSPointInRect(overlayPoint,drawRegionRect)) {
			if (!penIsDown) {
				[hintLinePath moveToPoint:overlayPoint];			// start of a run, so just move to it
				penIsDown = YES;
			} else {
				[hintLinePath lineToPoint:overlayPoint];			// otherwise, draw from the previous point to this one
				numSegments += 1;
			}
		} else {
			penIsDown = NO;						// leaving the draw region ends the run too, rather than drawing a chord across it
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
