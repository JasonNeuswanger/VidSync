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


#import "VSEventScreenPoint.h"

NSPoint quadratCoords2Dfrom3D(const VSPoint3D *quadratCoords3D, const char axisHorizontal, const char axisVertical) {
    NSPoint quadratCoords2D;																						
	if (axisHorizontal == 'x') {			// hvd = (horizontal coord, vertical coord, depth front-to-back coord)
		if (axisVertical == 'y') {		// hvd = xyz
			quadratCoords2D.x = quadratCoords3D->x;
			quadratCoords2D.y = quadratCoords3D->y;			
		} else {																	// hvd = xzy
			quadratCoords2D.x = quadratCoords3D->x;
			quadratCoords2D.y = quadratCoords3D->z;			
		}
	} else if (axisHorizontal == 'y') {
		if (axisVertical == 'x') {		// hvd = yxz
			quadratCoords2D.x = quadratCoords3D->y;
			quadratCoords2D.y = quadratCoords3D->x;			
		} else {																	// hvd = yzx
			quadratCoords2D.x = quadratCoords3D->y;
			quadratCoords2D.y = quadratCoords3D->z;			
		}
	} else if (axisHorizontal == 'z'){
		if (axisVertical == 'x') {		// hvd = zxy
			quadratCoords2D.x = quadratCoords3D->z;
			quadratCoords2D.y = quadratCoords3D->x;			
		} else {																	// hvd = zyx
			quadratCoords2D.x = quadratCoords3D->z;
			quadratCoords2D.y = quadratCoords3D->y;			
		}
	}
    return quadratCoords2D;
}

@implementation VSEventScreenPoint

@dynamic screenX;
@dynamic screenY;
@dynamic frontFrameWorldH;
@dynamic frontFrameWorldV;
@dynamic backFrameWorldH;
@dynamic backFrameWorldV;
@dynamic videoClip;
@dynamic point;
@dynamic screenPoints;
@dynamic hintLinesOut;
@synthesize tempOpacity;
@synthesize totalTimeRange;
@synthesize fadingTimeRange;
@synthesize fadingStartTime;
@synthesize fadingDuration;

- (void) awakeFromFetch
{
    [self addObserver:self forKeyPath:@"point.timecode" options:0 context:NULL];
    [self updateVisibleTimeRange];
    [super awakeFromFetch];
}

- (void) awakeFromInsert
{
    [self addObserver:self forKeyPath:@"point.timecode" options:0 context:NULL];
    [self updateVisibleTimeRange];
    [super awakeFromFetch];
}

- (void) observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context {
	if ([keyPath isEqual: @"point.timecode"]) [self updateVisibleTimeRange];
}

- (void) updateVisibleTimeRange
{
    if ([[self.videoClip.project.masterClip timeScale] intValue] > 0) {
        CMTime startTime = [UtilityFunctions CMTimeFromString:self.point.timecode];
        CMTime solidDuration = CMTimeMakeWithSeconds([self.point.trackedEvent.type.duration doubleValue], [[self.videoClip.project.masterClip timeScale] longValue]);
        fadingDuration = CMTimeMakeWithSeconds([self.point.trackedEvent.type.fadeTime doubleValue], [[self.videoClip.project.masterClip timeScale] longValue]);
        CMTime totalDuration = CMTimeAdd(solidDuration,fadingDuration);
        fadingStartTime = CMTimeAdd(startTime,solidDuration);
        totalTimeRange = CMTimeRangeMake(startTime,totalDuration);
        fadingTimeRange = CMTimeRangeMake(fadingStartTime,fadingDuration);
    } else {    // if the master clip hasn't loaded yet, wait and try again
        fadingDuration = CMTimeMakeWithSeconds(0,1);
        fadingStartTime=CMTimeMakeWithSeconds(0,1);
        totalTimeRange=CMTimeRangeMake(fadingStartTime,fadingDuration);
        fadingDuration=CMTimeMakeWithSeconds(0,1);
        [self performSelector:@selector(updateVisibleTimeRange) withObject:nil afterDelay:0.3f];
    }
}

- (void) updateCalibrationFrameCoords
{
    NSPoint videoCoords = NSMakePoint([self.screenX doubleValue],[self.screenY doubleValue]);
    if (self.videoClip.calibration.frontIsCalibrated) {
        NSPoint frontCalibrationFrameCoords = [self.videoClip.calibration projectScreenPoint:videoCoords toQuadratSurface:@"Front"];
        self.frontFrameWorldH = [NSNumber numberWithDouble:frontCalibrationFrameCoords.x];
        self.frontFrameWorldV = [NSNumber numberWithDouble:frontCalibrationFrameCoords.y];
    }
    if (self.videoClip.calibration.backIsCalibrated) {
        NSPoint backCalibrationFrameCoords = [self.videoClip.calibration projectScreenPoint:videoCoords toQuadratSurface:@"Back"];
        self.backFrameWorldH = [NSNumber numberWithDouble:backCalibrationFrameCoords.x];
        self.backFrameWorldV = [NSNumber numberWithDouble:backCalibrationFrameCoords.y];
    }
}

- (void) calculateHintLines
{
	for (VSHintLine *oldHintLine in self.hintLinesOut) [self.managedObjectContext deleteObject:oldHintLine];
	for (VSVideoClip *toVideoClip in self.videoClip.project.videoClips) {	// loop over all video clips in the project
		if (![toVideoClip isEqualTo:self.videoClip]) {						// but skip the current screenPoint's videoClip
			[VSHintLine createHintLineFromScreenPoint:self toVideoClip:toVideoClip];
		}
	}
}

- (VSLine3D) computeLine3D:(BOOL)useReprojectedPoints
{
	// Calculate the 2D quadrat coordinates from the clicked screen point
    NSPoint screenPoint;
    if (useReprojectedPoints) {
        screenPoint = [self reprojectedScreenPoint:NO];
    } else {
        screenPoint = NSMakePoint([self.screenX doubleValue],[self.screenY doubleValue]);
    }
	NSPoint front = [self.videoClip.calibration projectScreenPoint:screenPoint toQuadratSurface:@"Front"];
	NSPoint back = [self.videoClip.calibration projectScreenPoint:screenPoint toQuadratSurface:@"Back"];

	// Put the 2D quadrat coordinates into 3D coordinates based on the configuration of the quadrat, and return as a VSLine3D structure (defined in UtilityFunctions.h)
	VSLine3D line;
	double front3Dcoord = [self.videoClip.calibration.planeCoordFront doubleValue];
	double back3Dcoord = [self.videoClip.calibration.planeCoordBack doubleValue];
	if ([self.videoClip.calibration.axisHorizontal isEqualToString:@"x"]) {
		if ([self.videoClip.calibration.axisVertical isEqualToString:@"y"]) {
			line.front.x = front.x; line.front.y = front.y; line.front.z = front3Dcoord;
			line.back.x = back.x; line.back.y = back.y; line.back.z = back3Dcoord;
		} else {
			line.front.x = front.x; line.front.y = front3Dcoord; line.front.z = front.y;
			line.back.x = back.x; line.back.y = back3Dcoord; line.back.z = back.y;
		}
	} else if ([self.videoClip.calibration.axisHorizontal isEqualToString:@"y"]) {
		if ([self.videoClip.calibration.axisVertical isEqualToString:@"x"]) {
			line.front.x = front.y; line.front.y = front.x; line.front.z = front3Dcoord;
			line.back.x = back.y; line.back.y = back.x; line.back.z = back3Dcoord;
		} else {
			line.front.x = front3Dcoord; line.front.y = front.x; line.front.z = front.y;
			line.back.x = back3Dcoord; line.back.y = back.x; line.back.z = back.y;
		}
	} else {	// calibration's axisHorizontal is z
		if ([self.videoClip.calibration.axisVertical isEqualToString:@"x"]) {
			line.front.x = front.y; line.front.y = front3Dcoord; line.front.z = front.x;
			line.back.x = back.y; line.back.y = back3Dcoord; line.back.z = back.x;
		} else {
			line.front.x = front3Dcoord; line.front.y = front.y; line.front.z = front.x;
			line.back.x = back3Dcoord; line.back.y = back.y; line.back.z = back.x;
		}
	}
	return line;
}

- (void) putPointsInFrontQuadratPlaneIntoArray:(VSPoint3D[3])quadratPlanePoints
{
    double front3Dcoord = [self.videoClip.calibration.planeCoordFront doubleValue];
	if ([self.videoClip.calibration.axisFrontToBack isEqual: @"x"]) {
		quadratPlanePoints[0].x = front3Dcoord;
		quadratPlanePoints[0].y = 0.0;
		quadratPlanePoints[0].z = 0.0;
		quadratPlanePoints[1].x = front3Dcoord;
		quadratPlanePoints[1].y = 0.0;
		quadratPlanePoints[1].z = 1.0;
		quadratPlanePoints[2].x = front3Dcoord;
		quadratPlanePoints[2].y = 1.0;
		quadratPlanePoints[2].z = 0.0;
	} else if ([self.videoClip.calibration.axisFrontToBack isEqual: @"y"]) {
		quadratPlanePoints[0].x = 0.0;
		quadratPlanePoints[0].y = front3Dcoord;
		quadratPlanePoints[0].z = 0.0;
		quadratPlanePoints[1].x = 0.0;
		quadratPlanePoints[1].y = front3Dcoord;
		quadratPlanePoints[1].z = 1.0;
		quadratPlanePoints[2].x = 1.0;
		quadratPlanePoints[2].y = front3Dcoord;
		quadratPlanePoints[2].z = 0.0;		
	} else if ([self.videoClip.calibration.axisFrontToBack isEqual: @"z"]) {
		quadratPlanePoints[0].x = 0.0;
		quadratPlanePoints[0].y = 0.0;
		quadratPlanePoints[0].z = front3Dcoord;
		quadratPlanePoints[1].x = 1.0;
		quadratPlanePoints[1].y = 0.0;
		quadratPlanePoints[1].z = front3Dcoord;
		quadratPlanePoints[2].x = 0.0;
		quadratPlanePoints[2].y = 1.0;
		quadratPlanePoints[2].z = front3Dcoord;		
	}
}

- (NSPoint) reprojectedScreenPoint:(bool)shouldRedistort	// can only be used AFTER the associated point has 3D coordinates defined
{
	// Set up a 3D line from the camera through the screenPoint's VSPoint's 3D location.
	VSLine3D cameraToQuadratLine;
	VSPoint3D cameraPoint;
	VSPoint3D targetPoint;
	cameraPoint.x = [self.videoClip.calibration.cameraX floatValue];
	cameraPoint.y = [self.videoClip.calibration.cameraY floatValue];
	cameraPoint.z = [self.videoClip.calibration.cameraZ floatValue];
	targetPoint.x = [self.point.worldX floatValue];
	targetPoint.y = [self.point.worldY floatValue];
	targetPoint.z = [self.point.worldZ floatValue];	
	cameraToQuadratLine.front = cameraPoint;
	cameraToQuadratLine.back = targetPoint;
	
	// Construct 3 points in the front quadrat surface plane.
	VSPoint3D quadratPlanePoints[3];	
    [self putPointsInFrontQuadratPlaneIntoArray:quadratPlanePoints];
	
	// Calculate the intersection of the line from the camera through the target with the front quadrat face.

	VSPoint3D quadratFrontFaceIntersection = [UtilityFunctions intersectionOfLine:cameraToQuadratLine withPlaneDefinedByPoints:quadratPlanePoints];
	
	// Convert the 3D quadrat face coordinates into 2D front quadrat face coordinates of the intersection point, with .x and .y oriented actually representing the 
	// horizontal and vertical directions on the screen, for easy conversion into screen coordinates.

    char axisHorizontal = [self.videoClip.calibration.axisHorizontal characterAtIndex:0];
    char axisVertical = [self.videoClip.calibration.axisVertical characterAtIndex:0];
	NSPoint idealQuadratFrontCoords2D = quadratCoords2Dfrom3D(&quadratFrontFaceIntersection, axisHorizontal, axisVertical);																						
	
	// Convert the 2D quadrat face coordinates into 2D screen coordinates, representing the ideal screen coordinates of the target point's calculated 3D position for this videoClip.
	
	return [self.videoClip.calibration projectToScreenFromPoint:idealQuadratFrontCoords2D onQuadratSurface:@"Front" redistort:shouldRedistort];	
}

- (NSPoint) undistortedCoords
{
    NSPoint screenPoint = NSMakePoint([self.screenX floatValue],[self.screenY floatValue]);
    NSPoint undistortedScreenPoint = [self.videoClip.calibration undistortPoint:screenPoint];
    return undistortedScreenPoint;
}


- (NSString *) spreadsheetFormattedScreenPoint
{
	NSNumberFormatter *nf = self.point.trackedEvent.type.project.document.decimalFormatter;
    NSPoint undistortedScreenPoint = [self undistortedCoords];
    return [NSString stringWithFormat:@"\"%@: screen={%@,%@} undistorted={%@,%@} calibrationFrameFront={%@,%@} calibrationFrameBack={%@,%@}\"",
            self.videoClip.clipName,
            [nf stringFromNumber:self.screenX],
            [nf stringFromNumber:self.screenY],
            [nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.x]],
            [nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.y]],
            [nf stringFromNumber:self.frontFrameWorldH],
            [nf stringFromNumber:self.frontFrameWorldV],
            [nf stringFromNumber:self.backFrameWorldH],
            [nf stringFromNumber:self.backFrameWorldV]
            ];
}

- (NSXMLNode *) representationAsXMLNode
{
	NSNumberFormatter *nf = self.point.trackedEvent.type.project.document.decimalFormatter;
    NSPoint undistortedScreenPoint = [self undistortedCoords];
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"screenpoint"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"videoClip" stringValue:self.videoClip.clipName]];	
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"x" stringValue:[nf stringFromNumber:self.screenX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"y" stringValue:[nf stringFromNumber:self.screenY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"xu" stringValue:[nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.x]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"yu" stringValue:[nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.y]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"frameFrontH" stringValue:[nf stringFromNumber:self.frontFrameWorldH]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"frameFrontV" stringValue:[nf stringFromNumber:self.frontFrameWorldV]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"frameBackH" stringValue:[nf stringFromNumber:self.backFrameWorldH]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"frameBackV" stringValue:[nf stringFromNumber:self.backFrameWorldV]]];
	return mainElement;
}

- (void) dealloc
{
    [self carefullyRemoveObserver:self forKeyPath:@"point.timecode"];
}

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath
{
    if (observer != nil && self.point != nil) { // the point existence check is a quick hack to prevent EXC_BAD_ACCESS when it deallocs the point before the screenpoint
        @try {
            [self removeObserver:observer forKeyPath:keyPath];
        } @catch (id exception) {
        }
    }
}

@end
