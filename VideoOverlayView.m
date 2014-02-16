//
//  VideoOverlayView.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/26/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VideoOverlayView.h"


@implementation VideoOverlayView

- (id)initWithFrame:(NSRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
		trackingArea = [[NSTrackingArea alloc] initWithRect:[self bounds]
													options:NSTrackingMouseMoved|NSTrackingCursorUpdate|NSTrackingActiveInActiveApp|NSTrackingInVisibleRect
													  owner:self
												   userInfo:nil];
		[self addTrackingArea:trackingArea];
		// Note:  I'm setting it to refresh overlay when any of these observed values change as long as the object is the shared user defaults controller, regardless of key -- so only need to put the key here.
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratGridOverlayLineSpacing" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratGridOverlayLineThickness" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pointSelectionIndicatorLineLength" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pointSelectionIndicatorLineWidth" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pointSelectionIndicatorSizeFactor" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pointSelectionIndicatorColor" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratShowSurfaceGridOverlayFront" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratShowSurfaceGridOverlayBack" options:0 context:NULL];				
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratOverlayColorFront" options:0 context:NULL];				
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratOverlayColorBack" options:0 context:NULL];				
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratPointOverlayCircleDiameterFront" options:0 context:NULL];				
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.quadratPointOverlayCircleDiameterBack" options:0 context:NULL];				
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.showWorldCoordinatesNextToQuadratPoints" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.showPixelErrorOverlay" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pixelErrorDotSize" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pixelErrorLineWidth" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pixelErrorLineColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.pixelErrorPointColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.hintLineDrawInterval" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.showDistortionOverlay" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionPointsColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionConnectingLinesColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionTipToTipLinesColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionCorrectedPointsColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionCorrectedLinesColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionCenterColor" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionLineThickness" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.distortionPointSize" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.showDistortionConnectingLines" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.showDistortionTipToTipLines" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.showDistortionCorrectedPoints" options:0 context:NULL];		
	}
    return self;
}

- (void) observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context {
	if ([keyPath isEqualToString:@"values.quadratGridOverlayLineSpacing"] || [keyPath isEqualToString:@"values.quadratGridOverlayLineThickness"]) {
		[self calculateQuadratCoordinateGrids];
	}
	if ([object isEqualTo:[NSUserDefaultsController sharedUserDefaultsController]]) [self display];
}

#pragma mark
#pragma mark Drawing Methods

- (void)drawRect:(NSRect)rect 
{
	BOOL showUncorrectedDistortionOverlay = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showDistortionOverlay"] boolValue];
	BOOL showCorrectedDistortionOverlay = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showDistortionCorrectedPoints"] boolValue];
	BOOL showPixelErrorOverlay = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showPixelErrorOverlay"] boolValue];
	
	[[NSColor clearColor] set]; // use clearColor when not testing size
	NSRectFill([self bounds]);  // without the clearColor fill, this layer fills with a non-transparent gray and completely obscures the video
	[self calculateVisibleScreenPoints];
	[self calculateVisibleAnnotations];
	[self drawCalibrationScreenPoints];
	[self drawMeasurementScreenPoints];
	[self drawHintLines];
	[self drawAnnotations];
	[self drawQuadratCoordinateGrids];
	if (showUncorrectedDistortionOverlay || showCorrectedDistortionOverlay) [self drawDistortionCorrections];
	if (showPixelErrorOverlay) [self drawScreenPointToIdealScreenPointComparison];
}

- (void) calculateVisibleScreenPoints;
{
	VideoWindowController *vwc = _delegate;
	NSMutableSet *tempVisibleScreenPoints = [NSMutableSet set];
    CMTime now = [vwc.document currentMasterTime];
	for (VSEventScreenPoint *screenPoint in vwc.videoClip.eventScreenPoints) {
        CMTime startTime = [UtilityFunctions CMTimeFromString:screenPoint.point.timecode];
        CMTime solidDuration = CMTimeMakeWithSeconds([screenPoint.point.trackedEvent.type.duration doubleValue], [[vwc.videoClip.project.masterClip timeScale] longValue]);
        CMTime fadingDuration = CMTimeMakeWithSeconds([screenPoint.point.trackedEvent.type.fadeTime doubleValue], [[vwc.videoClip.project.masterClip timeScale] longValue]);
        CMTime totalDuration = CMTimeAdd(solidDuration,fadingDuration);
        CMTimeRange totalTimeRange = CMTimeRangeMake(startTime,totalDuration);
        if (CMTimeRangeContainsTime(totalTimeRange,now)) [tempVisibleScreenPoints addObject:screenPoint];
	}
	self.visibleScreenPoints = tempVisibleScreenPoints;
}

- (void) calculateVisibleAnnotations;
{
	VideoWindowController *vwc = _delegate;
	NSMutableSet *tempVisibleAnnotations = [NSMutableSet new];
    CMTime now = [vwc.document currentMasterTime];
	for (VSAnnotation *annotation in vwc.videoClip.annotations) {
        CMTime startTime = [UtilityFunctions CMTimeFromString:annotation.startTimecode];
        CMTime solidDuration = CMTimeMakeWithSeconds([annotation.duration doubleValue], [[vwc.videoClip timeScale] longValue]);
        CMTime fadingDuration = CMTimeMakeWithSeconds([annotation.fadeTime doubleValue], [[vwc.videoClip timeScale] longValue]);
        CMTime totalDuration = CMTimeAdd(solidDuration,fadingDuration);
        CMTime fadingStartTime = CMTimeAdd([UtilityFunctions CMTimeFromString:annotation.startTimecode],solidDuration);
        CMTimeRange totalTimeRange = CMTimeRangeMake(startTime,totalDuration);
        CMTimeRange fadingTimeRange = CMTimeRangeMake(fadingStartTime,fadingDuration);
		float currentOpacity = 1.0;
		if (CMTimeRangeContainsTime(totalTimeRange,now)) {
			if (CMTimeRangeContainsTime(fadingTimeRange,now)) {
				CMTime fadingTimeElapsed = CMTimeSubtract(now,fadingStartTime);
                currentOpacity = 1.0 - ((float) fadingTimeElapsed.value / (float) fadingTimeElapsed.timescale) / ((float) fadingDuration.value / (float) fadingDuration.timescale);
			}
			annotation.tempOpacity = currentOpacity;
			[tempVisibleAnnotations addObject:annotation];
		}
	}
	self.visibleAnnotations = tempVisibleAnnotations;
}

- (void) drawAnnotations
{
	for (VSAnnotation *annotation in self.visibleAnnotations) [self drawAnnotation:annotation];
}

- (void) drawAnnotation:(VSAnnotation *)annotation
{
	const float selectionPadding = 5.0;
	VideoWindowController *vwc = _delegate;
	NSFont *font = [NSFont fontWithName:annotation.shape size:[annotation.size floatValue]];
	NSMutableDictionary *attrs = [NSMutableDictionary new];
	[attrs setObject:font forKey:NSFontAttributeName];
	[attrs setObject:[annotation.color colorWithAlphaComponent:annotation.tempOpacity] forKey:NSForegroundColorAttributeName];

	NSMutableAttributedString *annotationString = [[NSMutableAttributedString alloc] initWithString:annotation.notes attributes:attrs];
	
	NSPoint scaledPoint = [vwc convertVideoToOverlayCoords:NSMakePoint([annotation.screenX floatValue],[annotation.screenY floatValue])];
	
	NSRect bounds = [annotationString boundingRectWithSize:NSMakeSize([annotation.width floatValue],vwc.overlayHeight-2*selectionPadding) options:NSStringDrawingTruncatesLastVisibleLine|NSStringDrawingUsesLineFragmentOrigin];
	float newHeight;
	if (bounds.size.height < 2.0*scaledPoint.y) {
		newHeight = bounds.size.height;
	} else {
		newHeight = 2.0*scaledPoint.y;
	}
	
	NSPoint drawOrigin = NSMakePoint(scaledPoint.x - bounds.size.width/2,scaledPoint.y - newHeight/2);
	NSRect drawingRect = NSMakeRect(drawOrigin.x,drawOrigin.y,bounds.size.width,newHeight);
	
	[annotation.notes drawWithRect:drawingRect options:NSStringDrawingTruncatesLastVisibleLine|NSStringDrawingUsesLineFragmentOrigin attributes:attrs];
	
	if ([[vwc.videoClip.project.document.annotationsController selectedObjects] count] > 0 && [[[vwc.videoClip.project.document.annotationsController selectedObjects] objectAtIndex:0] isEqualTo:annotation]) {
		NSColor *selectionColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pointSelectionIndicatorColor"]];
		[selectionColor set];
		NSRect selectionRect = NSMakeRect(drawingRect.origin.x - selectionPadding,drawingRect.origin.y - selectionPadding,drawingRect.size.width + 2*selectionPadding,drawingRect.size.height + 2*selectionPadding);
		NSBezierPath *selectedOutline = [NSBezierPath bezierPathWithRect:selectionRect];
		[selectedOutline setLineWidth:3.0];
		[selectedOutline stroke];
	}
}



- (void) drawScreenPointToIdealScreenPointComparison		// draws dots at all screenPoint clicked locations throughout the entire image, and draws lines from them to their ideal positions
{
	NSColor *pixelErrorPointColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pixelErrorPointColor"]];
	NSColor *pixelErrorLineColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pixelErrorLineColor"]];		
	float shapeSize = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pixelErrorDotSize"] floatValue];
	float lineWidth = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pixelErrorLineWidth"] floatValue];
	VideoWindowController *vwc = _delegate;
	NSRect shapeRect;
	NSPoint point;
	NSPoint idealPoint;
	NSPoint line[2];
	NSBezierPath *path;
	[pixelErrorLineColor setStroke];
	[pixelErrorPointColor setFill];
	for (VSEventScreenPoint *screenPoint in vwc.videoClip.eventScreenPoints) {
		if ([screenPoint.point has3Dcoords]) {
			point = [vwc convertVideoToOverlayCoords:NSMakePoint([screenPoint.screenX floatValue],[screenPoint.screenY floatValue])];
			idealPoint = [vwc convertVideoToOverlayCoords:[screenPoint reprojectedScreenPoint:YES]];
			shapeRect = NSMakeRect(point.x-shapeSize,point.y-shapeSize,2.0*shapeSize,2.0*shapeSize);	
			NSBezierPath *circle = [NSBezierPath bezierPathWithOvalInRect:shapeRect];
			line[0] = point;
			line[1] = idealPoint;
			path = [NSBezierPath bezierPath];	
			[path appendBezierPathWithPoints:line count:2];
			[path setLineWidth:lineWidth];
			[path stroke];
			[circle fill];
		}
	}
}

- (void) drawDistortionCorrections
{		
	NSColor *distortedPointColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionPointsColor"]];
	NSColor *connectingLineColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionConnectingLinesColor"]];
	NSColor *tipToTipLineColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionTipToTipLinesColor"]];
	NSColor *correctedPointColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionCorrectedPointsColor"]];
	NSColor *correctedLineColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionCorrectedLinesColor"]];
	NSColor *crosshairsColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionCenterColor"]];
	float shapeSize = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionPointSize"] floatValue];
	float lineWidth = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"distortionLineThickness"] floatValue];
	BOOL showConnectingLines = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showDistortionConnectingLines"] boolValue];
	BOOL showTipToTipLines = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showDistortionTipToTipLines"] boolValue];
	BOOL showUncorrectedOverlay = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showDistortionOverlay"] boolValue];
	BOOL showCorrectedOverlay = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showDistortionCorrectedPoints"] boolValue];
	
	VideoWindowController *vwc = _delegate;
	NSSet *distortionLines = vwc.videoClip.calibration.distortionLines;
	NSSortDescriptor *indexDescriptor = [[NSSortDescriptor alloc] initWithKey:@"index" ascending:YES];
	NSRect shapeRect;
	NSPoint point,uPoint,undistortedVideoCoords;
	NSArray *distortionPoints;
	VSDistortionPoint *distortionPoint;
	
	NSBezierPath *pointDotsPath = [NSBezierPath bezierPath];
	NSBezierPath *correctedPointDotsPath = [NSBezierPath bezierPath];
	NSBezierPath *connectingLinesPath = [NSBezierPath bezierPath];
	NSBezierPath *tipsToTipsPath = [NSBezierPath bezierPath];
	NSBezierPath *correctedTipsToTipsPath = [NSBezierPath bezierPath];
	[connectingLinesPath setLineWidth:lineWidth];
	[tipsToTipsPath setLineWidth:lineWidth];
	[correctedTipsToTipsPath setLineWidth:lineWidth];
	
	[distortedPointColor setFill];
	for (VSDistortionLine *distortionLine in distortionLines) {
		
		distortionPoints = [[distortionLine.distortionPoints allObjects] sortedArrayUsingDescriptors:[NSArray arrayWithObject:indexDescriptor]]; // all points on current line, sorted by index

		for (int i = 0; i < [distortionPoints count]; i++) {
			distortionPoint = [distortionPoints objectAtIndex:i];
			
			point = [vwc convertVideoToOverlayCoords:NSMakePoint([distortionPoint.screenX floatValue],[distortionPoint.screenY floatValue])];
			
			if (i == 0) [tipsToTipsPath moveToPoint:point];
			if ([vwc.videoClip.calibration hasDistortionCorrection] && i == 0 && [distortionPoints count] >= 2) {
                undistortedVideoCoords = [vwc.videoClip.calibration undistortPoint:NSMakePoint([distortionPoint.screenX floatValue],[distortionPoint.screenY floatValue])];
                uPoint = [vwc convertVideoToOverlayCoords:undistortedVideoCoords];
                [correctedTipsToTipsPath moveToPoint:uPoint];
			}
			shapeRect = NSMakeRect(point.x-shapeSize,point.y-shapeSize,2.0*shapeSize,2.0*shapeSize);	
			[pointDotsPath appendBezierPathWithOvalInRect:shapeRect];
			if ([distortionPoints count] > 1) {															// if it is the first point, move the bezier path to there
				if (showConnectingLines && i == 0) {
					[connectingLinesPath moveToPoint:point];
				} else if (showConnectingLines && i > 0) {												// if it's not the first point, draw a line to the previous point
					[connectingLinesPath lineToPoint:point];
				}
				if (showTipToTipLines && [distortionPoints count] > 2 && i == [distortionPoints count]-1) { // if it's the last of more than 2 points, draw a line back to the start 
					[tipsToTipsPath lineToPoint:point];
				}
                if ([vwc.videoClip.calibration hasDistortionCorrection] && i == [distortionPoints count]-1 && [distortionPoints count] >= 2) {
                    undistortedVideoCoords = [vwc.videoClip.calibration undistortPoint:NSMakePoint([distortionPoint.screenX floatValue],[distortionPoint.screenY floatValue])];
                    uPoint = [vwc convertVideoToOverlayCoords:undistortedVideoCoords];
                    [correctedTipsToTipsPath lineToPoint:uPoint];    
                }
			}
			
			// now the results display to show the corrected points
			if ([vwc.videoClip.calibration hasDistortionCorrection] && showCorrectedOverlay) {	// if the clip has a distortion calculated, draw the corrected points
				undistortedVideoCoords = [vwc.videoClip.calibration undistortPoint:NSMakePoint([distortionPoint.screenX floatValue],[distortionPoint.screenY floatValue])];
				uPoint = [vwc convertVideoToOverlayCoords:undistortedVideoCoords];
				shapeRect = NSMakeRect(uPoint.x-shapeSize*0.7,uPoint.y-shapeSize*0.7,2.0*shapeSize*0.7,2.0*shapeSize*0.7);	
				[correctedPointDotsPath appendBezierPathWithOvalInRect:shapeRect];
				[correctedPointColor setStroke];
				[NSBezierPath strokeLineFromPoint:point toPoint:uPoint];
			}
        }

	}
	
	// if the distortion parameters have been calculated, draw the distortion center
	if ([vwc.videoClip.calibration hasDistortionCorrection]) {		
		NSPoint centerPoint = [vwc convertVideoToOverlayCoords:NSMakePoint([vwc.videoClip.calibration.distortionCenterX floatValue],[vwc.videoClip.calibration.distortionCenterY floatValue])];
		float centerCrossSize = 10.0;
		NSBezierPath *centerCrossPath = [NSBezierPath bezierPath];
		[centerCrossPath moveToPoint:NSMakePoint(centerPoint.x - centerCrossSize, centerPoint.y)];
		[centerCrossPath lineToPoint:NSMakePoint(centerPoint.x + centerCrossSize, centerPoint.y)];
		[centerCrossPath moveToPoint:NSMakePoint(centerPoint.x, centerPoint.y - centerCrossSize)];
		[centerCrossPath lineToPoint:NSMakePoint(centerPoint.x, centerPoint.y + centerCrossSize)];
		[centerCrossPath setLineWidth:4.0];
		[crosshairsColor setStroke];
		[centerCrossPath stroke];
	}
	
    if (showUncorrectedOverlay) {
        [tipToTipLineColor setStroke];
        [tipsToTipsPath stroke];
        [connectingLineColor setStroke];
        [connectingLinesPath stroke];
    }
    [distortedPointColor setFill];
    [pointDotsPath fill];    
    if (showCorrectedOverlay) {
        [correctedPointColor setFill];
        [correctedPointDotsPath fill];			
        [correctedLineColor setStroke];
        [correctedTipsToTipsPath stroke];
    }
    
	// Draw the selection indicator if we're drawing a clip with a current selection
	if ([[vwc.videoClip.project.document.distortionPointsController selectedObjects] count] > 0) {
		VSDistortionPoint *selectedDistortionPoint = [[vwc.videoClip.project.document.distortionPointsController selectedObjects] objectAtIndex:0];	
		if ([selectedDistortionPoint.distortionLine.calibration.videoClip isEqualTo:vwc.videoClip]) {
			NSPoint selectedPoint = [vwc convertVideoToOverlayCoords:NSMakePoint([selectedDistortionPoint.screenX floatValue],[selectedDistortionPoint.screenY floatValue])];
			[self drawSelectionIndicatorAtPoint:selectedPoint forShapeOfSize:shapeSize*2.0];
		}
		
	}

}

- (void) drawMeasurementScreenPoints
{
	VideoWindowController *vwc = _delegate;
	CMTime now = [vwc.document currentMasterTime];
	NSSet *trackedEventsNeedingConnectingLinesDrawn = [NSSet set];
	for (VSEventScreenPoint *screenPoint in vwc.videoClip.eventScreenPoints) {
        CMTime startTime = [UtilityFunctions CMTimeFromString:screenPoint.point.timecode];
        CMTime solidDuration = CMTimeMakeWithSeconds([screenPoint.point.trackedEvent.type.duration doubleValue], [[vwc.videoClip timeScale] longValue]);
        CMTime fadingDuration = CMTimeMakeWithSeconds([screenPoint.point.trackedEvent.type.fadeTime doubleValue], [[vwc.videoClip timeScale] longValue]);
        CMTime totalDuration = CMTimeAdd(solidDuration,fadingDuration);
        CMTime fadingStartTime = CMTimeAdd(startTime,solidDuration);
        CMTimeRange totalTimeRange = CMTimeRangeMake(startTime,totalDuration);
        CMTimeRange fadingTimeRange = CMTimeRangeMake(fadingStartTime,fadingDuration);
		float currentOpacity = 1.0;
		if (CMTimeRangeContainsTime(totalTimeRange,now)) {
			if (CMTimeRangeContainsTime(fadingTimeRange,now)) {
				CMTime fadingTimeElapsed = CMTimeSubtract(now,fadingStartTime);
				currentOpacity = 1.0 - ((float) fadingTimeElapsed.value / (float) fadingTimeElapsed.timescale) / ((float) fadingDuration.value / (float) fadingDuration.timescale);
			}
			if ([screenPoint.point.trackedEvent.trackedObjects count] == 1) {	// If the event is associated with just one object, draw it.
				[self drawMeasurementScreenPoint:screenPoint 
							   fromTrackedObject:[screenPoint.point.trackedEvent.trackedObjects anyObject] 
									 withOpacity:currentOpacity 
								   magnification:1.0];
			} else {	// If the event is associated with more than one object, draw it with nested symbols representing all their colors.
				for(int i=0; i < [screenPoint.point.trackedEvent.trackedObjects count]; i++) {
					float magnification = 1.0 + 0.3 * (float) ([screenPoint.point.trackedEvent.trackedObjects count] - i);
					[self drawMeasurementScreenPoint:screenPoint 
								   fromTrackedObject:[[screenPoint.point.trackedEvent.trackedObjects allObjects] objectAtIndex:i] 
										 withOpacity:currentOpacity 
									   magnification:magnification];
				}
			}
			
			// add the event to a queue of events needing connectinglines drawn, if it is not already there
			if (![screenPoint.point.trackedEvent.type.connectingLineType isEqualToString:@"None"] && ![trackedEventsNeedingConnectingLinesDrawn containsObject:screenPoint.point.trackedEvent] && [screenPoint.point.trackedEvent.points count] > 1) {
				screenPoint.point.trackedEvent.tempOpacity = currentOpacity;
				trackedEventsNeedingConnectingLinesDrawn = [trackedEventsNeedingConnectingLinesDrawn setByAddingObject:screenPoint.point.trackedEvent];
			}
		}
	}
	for (VSTrackedEvent *trackedEvent in trackedEventsNeedingConnectingLinesDrawn) [self drawConnectingLinesForTrackedEvent:trackedEvent];
}

- (void) drawConnectingLinesForTrackedEvent:(VSTrackedEvent *)trackedEvent
{	
	// get all of the VSTrackedEvent's VSPoints that have VSEventScreenPoints for the current VSVideoClip, in ascending order of VSPoint.index
	VideoWindowController *vwc = _delegate;
	NSPoint line[2];
	VSEventScreenPoint *currentScreenPoint,*previousScreenPoint;
	NSArray *sortedPoints = [trackedEvent.points sortedArrayUsingDescriptors:[NSArray arrayWithObject:[NSSortDescriptor sortDescriptorWithKey:@"index" ascending:YES]]];	
	VSPoint *previousPoint = [sortedPoints objectAtIndex:0];
	for (int i = 1; i < [sortedPoints count]; i++) {
		VSPoint *point = [sortedPoints objectAtIndex:i];
		if ([point has3Dcoords] && [previousPoint has3Dcoords]) {
			currentScreenPoint = [point screenPointForVideoClip:vwc.videoClip];
			previousScreenPoint = [previousPoint screenPointForVideoClip:vwc.videoClip];
			if (currentScreenPoint != nil && previousScreenPoint != nil) {
				VSTrackedObject *objectForColor = [trackedEvent.trackedObjects anyObject];	// not wasting time doing multiple colors for multiple objects here
				NSColor *lineColor = [objectForColor.color colorWithAlphaComponent:trackedEvent.tempOpacity];
				line[0] = [vwc convertVideoToOverlayCoords:NSMakePoint([previousScreenPoint.screenX floatValue],[previousScreenPoint.screenY floatValue])];
				line[1] = [vwc convertVideoToOverlayCoords:NSMakePoint([currentScreenPoint.screenX floatValue],[currentScreenPoint.screenY floatValue])];
				[lineColor setStroke];
				NSBezierPath *path = [NSBezierPath bezierPath];	
				[path appendBezierPathWithPoints:line count:2];
				[path setLineWidth:[trackedEvent.type.connectingLineThickness floatValue]];
				if ([trackedEvent.type.connectingLineType isEqualToString:@"Dotted"]) {
					CGFloat lineDash[2] = {3.0,3.0};
					[path setLineDash:lineDash count:2 phase:0.0];
				}
				[path stroke];
				if ([trackedEvent.type.connectingLineLengthLabeled intValue] > 0) { // if "Show connecting line length" is not "No"
					if ([trackedEvent.type.connectingLineLengthLabeled intValue] == 1 || (currentScreenPoint.videoClip.isMasterClipOf != nil)) {	// Show line if it's "On All Clips"
						[self drawConnectingLinesLengthLabelFromVSPoint:point toVSPoint:previousPoint onLine:line inColor:lineColor];	// or if it's "On Master Clip" and this is one.
					}
				}
			}
		}
		previousPoint = point;
	}
	
}

- (void) drawConnectingLinesLengthLabelFromVSPoint:(VSPoint *)point toVSPoint:(VSPoint *)otherPoint onLine:(NSPoint[2])line inColor:(NSColor *)color
{
	// Calculate the connecting line length, CI, and midPoint
	
	NSNumber *distance = [point distanceToVSPoint:otherPoint];
	
    NSPoint midPoint = NSMakePoint(((line[0].x + line[1].x) / 2.0), ((line[0].y + line[1].y) / 2.0));
	
	// Format the text
	
	NSNumberFormatter *nf = [[NSNumberFormatter alloc] init];
	[nf setFormatterBehavior:NSNumberFormatterBehavior10_4];
	[nf setMultiplier:point.trackedEvent.type.connectingLineLengthLabelUnitMultiplier];
	[nf setMaximumFractionDigits:[point.trackedEvent.type.connectingLineLengthLabelFractionDigits intValue]];

	[nf setPositiveSuffix:point.trackedEvent.type.connectingLineLengthLabelUnits];
	
	NSString *lengthText = [nf stringFromNumber:distance];
	NSFont *lengthStrFont = [NSFont fontWithName:@"Helvetica" size:[point.trackedEvent.type.connectingLineLengthLabelFontSize floatValue]];
	NSDictionary *lengthStrAttributes = [NSDictionary dictionaryWithObjectsAndKeys:lengthStrFont,NSFontAttributeName,
										 color,NSForegroundColorAttributeName,nil];
	NSMutableAttributedString *lengthStr = [[NSMutableAttributedString alloc] initWithString:lengthText attributes:lengthStrAttributes];
	
	// Draw everything
	
	float lineAngle;						// the angle the line makes going from the left point to the right point, in radians
	if (line[0].x < line[1].x) {			// line[0] is the leftmost point
		lineAngle = atan((line[1].y-line[0].y) / (line[1].x - line[0].x));
	} else {								// line[1] is the leftmost point
		lineAngle = atan((line[0].y-line[1].y) / (line[0].x - line[1].x));
	}
	float rotationAngle;					// the angle by which to rotate the label, in radians
	if (lineAngle > M_PI/4 || lineAngle < -M_PI/4) {
		rotationAngle = 0.0;
	} else if (lineAngle >= 0.0) {
		rotationAngle = lineAngle - M_PI/4;
	} else {  // -pi/4 < lineAngle < 0
		rotationAngle = lineAngle + M_PI/4;
	}
	NSAffineTransform *transform = [NSAffineTransform transform];
	[transform translateXBy:midPoint.x yBy:midPoint.y];								// put the transformation center at the line's midpoint
	[transform rotateByRadians:rotationAngle];										// rotates about the midpoint of the line
	[transform translateXBy:-midPoint.x yBy:-midPoint.y];							// moves the transformation's center back to the origin
	[NSGraphicsContext saveGraphicsState];	// save state from before affine transform is applied
	[transform concat];						// apply the transform to everything that comes after, until restoreGraphicsState
	[color setStroke];
	NSRect lengthStrBounds = [lengthStr boundingRectWithSize:NSMakeSize(1000.0,1000.0) options:NSStringDrawingTruncatesLastVisibleLine|NSStringDrawingUsesLineFragmentOrigin];
	NSRect lengthStrRect = NSMakeRect(midPoint.x - lengthStrBounds.size.width/2,midPoint.y-lengthStrBounds.size.height/2,lengthStrBounds.size.width,lengthStrBounds.size.height);
	float h = 5.0;	// horizontal padding amount for the backing rect
	float v = 1.5;	// vertical padding amount for the backing rect
	NSBezierPath *lengthLabelBorder = [NSBezierPath bezierPathWithRect:NSMakeRect(lengthStrRect.origin.x-h,lengthStrRect.origin.y-2*v,lengthStrRect.size.width+2*h,lengthStrRect.size.height+3*v)];
	float backgroundAlpha;
	if ([color alphaComponent] < 0.7) {
		backgroundAlpha = [color alphaComponent];
	} else {
		backgroundAlpha = 0.7;
	}
	[[[NSColor blackColor] colorWithAlphaComponent:backgroundAlpha] setFill];
	[lengthLabelBorder fill];
	[lengthLabelBorder setLineWidth:0.7*[point.trackedEvent.type.connectingLineThickness floatValue]];
	[lengthLabelBorder stroke];
	[lengthStr drawWithRect:lengthStrRect options:NSStringDrawingTruncatesLastVisibleLine|NSStringDrawingUsesLineFragmentOrigin];
	[NSGraphicsContext restoreGraphicsState];	// restore to state before affine transform
}

- (void) drawMeasurementScreenPoint:(VSEventScreenPoint *)screenPoint fromTrackedObject:(VSTrackedObject *)pointsObject withOpacity:(float)opacity magnification:(float)magnification
{
	VideoWindowController *vwc = _delegate;
	NSPoint videoPoint = NSMakePoint([screenPoint.screenX floatValue],[screenPoint.screenY floatValue]);
	if (videoPoint.x == 0.0 && videoPoint.y == 0.0) return;
	NSPoint point = [vwc convertVideoToOverlayCoords:videoPoint];
	NSColor *pointColor = [NSColor colorWithDeviceRed:[pointsObject.color redComponent]
												green:[pointsObject.color greenComponent]
												 blue:[pointsObject.color blueComponent]
												alpha:opacity];
	[pointColor setStroke];
	[pointColor setFill];
	float shapeSize = [screenPoint.point.trackedEvent.type.size floatValue]*magnification;
	NSRect shapeRect = NSMakeRect(point.x-shapeSize,point.y-shapeSize,2.0*shapeSize,2.0*shapeSize);	
	if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Circle"]) {
		NSBezierPath *circle = [NSBezierPath bezierPathWithOvalInRect:shapeRect];
		[circle setLineWidth:3.0];
		[circle stroke];
		NSRect centerPoint = NSMakeRect(point.x-1.5, point.y-1.5, 3.0, 3.0);
		NSRectFill(centerPoint);
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Double Circle"]) {
		float outerRadius = shapeSize + 4;
		NSRect outerRect = NSMakeRect(point.x-outerRadius,point.y-outerRadius,2.0*outerRadius,2.0*outerRadius);
		NSBezierPath *circle = [NSBezierPath bezierPathWithOvalInRect:shapeRect];
		NSBezierPath *outerCircle = [NSBezierPath bezierPathWithOvalInRect:outerRect];
		[circle setLineWidth:2.0];
		[outerCircle setLineWidth:2.0];
		[circle stroke];
		[outerCircle stroke];
		NSRect centerPoint = NSMakeRect(point.x-1.5, point.y-1.5, 3.0, 3.0);
		NSRectFill(centerPoint);
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Pacman"]) {
		NSPoint mouthPoints[2];
		mouthPoints[0] = point;
		mouthPoints[1] = NSMakePoint(point.x+shapeSize*0.92388,point.y+shapeSize*0.382683);	// uses cos and sin of half the total mouth angle
		NSBezierPath *pacMan = [NSBezierPath bezierPath];
		[pacMan appendBezierPathWithArcWithCenter:point radius:shapeSize startAngle:22.5 endAngle:342.5];	// total mouth angle 45 degrees
		[pacMan appendBezierPathWithPoints:mouthPoints count:2];
		[pacMan setLineWidth:2.0];
		[pacMan stroke];
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Square"]) {
		NSBezierPath *square = [NSBezierPath bezierPathWithRect:shapeRect];
		[square setLineWidth:3.0];
		[square stroke];
		NSRect centerPoint = NSMakeRect(point.x-1.5, point.y-1.5, 3.0, 3.0);
		NSRectFill(centerPoint);
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Disc"]) {
		NSBezierPath *circle = [NSBezierPath bezierPathWithOvalInRect:shapeRect];
		[circle setLineWidth:3.0];
		[circle stroke];
		[circle fill];
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"x"]) {
		NSPoint cross1[2];
		NSPoint cross2[2];
		float tipCoord = shapeSize*0.70710678;
		cross1[0] = NSMakePoint(point.x+tipCoord,point.y+tipCoord);
		cross1[1] = NSMakePoint(point.x-tipCoord,point.y-tipCoord);
		cross2[0] = NSMakePoint(point.x+tipCoord,point.y-tipCoord);
		cross2[1] = NSMakePoint(point.x-tipCoord,point.y+tipCoord);
		NSBezierPath *cross1path = [NSBezierPath bezierPath];
		[cross1path appendBezierPathWithPoints:cross1 count:2];
		NSBezierPath *cross2path = [NSBezierPath bezierPath];
		[cross2path appendBezierPathWithPoints:cross2 count:2];		
		[cross1path setLineWidth:3.0];
		[cross2path setLineWidth:3.0];
		[cross1path stroke];
		[cross2path stroke];
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"+"]) {
		NSPoint cross1[2];
		NSPoint cross2[2];
		cross1[0] = NSMakePoint(point.x+shapeSize,point.y);
		cross1[1] = NSMakePoint(point.x-shapeSize,point.y);
		cross2[0] = NSMakePoint(point.x,point.y+shapeSize);
		cross2[1] = NSMakePoint(point.x,point.y-shapeSize);
		NSBezierPath *cross1path = [NSBezierPath bezierPath];
		[cross1path appendBezierPathWithPoints:cross1 count:2];
		NSBezierPath *cross2path = [NSBezierPath bezierPath];
		[cross2path appendBezierPathWithPoints:cross2 count:2];
		[cross1path setLineWidth:3.0];
		[cross2path setLineWidth:3.0];
		[cross1path stroke];
		[cross2path stroke];		
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Collision"]) {	// colliding left and right arrows
		NSPoint line1[2];
		NSPoint line2[3];
		NSPoint line3[3];
		line1[0] = NSMakePoint(point.x-shapeSize,point.y);
		line1[1] = NSMakePoint(point.x+shapeSize,point.y);
		line2[0] = NSMakePoint(point.x+0.5*shapeSize,point.y-0.5*shapeSize);
		line2[1] = point;
		line2[2] = NSMakePoint(point.x+0.5*shapeSize,point.y+0.5*shapeSize);
		line3[0] = NSMakePoint(point.x-0.5*shapeSize,point.y+0.5*shapeSize);
		line3[1] = point;
		line3[2] = NSMakePoint(point.x-0.5*shapeSize,point.y-0.5*shapeSize);
		NSBezierPath *line1path = [NSBezierPath bezierPath];
		[line1path appendBezierPathWithPoints:line1 count:2];
		NSBezierPath *line2path = [NSBezierPath bezierPath];
		[line2path appendBezierPathWithPoints:line2 count:3];
		NSBezierPath *line3path = [NSBezierPath bezierPath];
		[line3path appendBezierPathWithPoints:line3 count:3];
		[line1path setLineWidth:3.0];
		[line2path setLineWidth:2.0];
		[line3path setLineWidth:2.0];
		[line1path stroke];
		[line2path stroke];		
		[line3path stroke];				
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Up Arrow"]) {
		NSPoint line1[2];
		NSPoint line2[3];
		line1[0] = point;
		line1[1] = NSMakePoint(point.x,point.y-1.5*shapeSize);
		line2[0] = NSMakePoint(point.x+0.5*shapeSize,point.y-0.5*shapeSize);
		line2[1] = point;
		line2[2] = NSMakePoint(point.x-0.5*shapeSize,point.y-0.5*shapeSize);
		NSBezierPath *line1path = [NSBezierPath bezierPath];
		[line1path appendBezierPathWithPoints:line1 count:2];
		NSBezierPath *line2path = [NSBezierPath bezierPath];
		[line2path setMiterLimit:15.0];
		[line2path appendBezierPathWithPoints:line2 count:3];
		[line1path setLineWidth:3.0];
		[line2path setLineWidth:3.0];
		[line1path stroke];
		[line2path stroke];
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Down Arrow"]) {
		NSPoint line1[2];
		NSPoint line2[3];
		line1[0] = point;
		line1[1] = NSMakePoint(point.x,point.y+1.5*shapeSize);
		line2[0] = NSMakePoint(point.x+0.5*shapeSize,point.y+0.5*shapeSize);
		line2[1] = point;
		line2[2] = NSMakePoint(point.x-0.5*shapeSize,point.y+0.5*shapeSize);
		NSBezierPath *line1path = [NSBezierPath bezierPath];
		[line1path appendBezierPathWithPoints:line1 count:2];
		NSBezierPath *line2path = [NSBezierPath bezierPath];
		[line2path setMiterLimit:15.0];
		[line2path appendBezierPathWithPoints:line2 count:3];
		[line1path setLineWidth:3.0];
		[line2path setLineWidth:3.0];
		[line1path stroke];
		[line2path stroke];
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Left Arrow"]) {
		NSPoint line1[2];
		NSPoint line2[3];
		line1[0] = point;
		line1[1] = NSMakePoint(point.x+1.5*shapeSize,point.y);
		line2[0] = NSMakePoint(point.x+0.5*shapeSize,point.y-0.5*shapeSize);
		line2[1] = point;
		line2[2] = NSMakePoint(point.x+0.5*shapeSize,point.y+0.5*shapeSize);
		NSBezierPath *line1path = [NSBezierPath bezierPath];
		[line1path appendBezierPathWithPoints:line1 count:2];
		NSBezierPath *line2path = [NSBezierPath bezierPath];
		[line2path setMiterLimit:15.0];
		[line2path appendBezierPathWithPoints:line2 count:3];
		[line1path setLineWidth:3.0];
		[line2path setLineWidth:3.0];
		[line1path stroke];
		[line2path stroke];
	} else if ([screenPoint.point.trackedEvent.type.shape isEqualToString:@"Right Arrow"]) {
		NSPoint line1[2];
		NSPoint line2[3];
		line1[0] = point;
		line1[1] = NSMakePoint(point.x-1.5*shapeSize,point.y);
		line2[0] = NSMakePoint(point.x-0.5*shapeSize,point.y-0.5*shapeSize);
		line2[1] = point;
		line2[2] = NSMakePoint(point.x-0.5*shapeSize,point.y+0.5*shapeSize);
		NSBezierPath *line1path = [NSBezierPath bezierPath];
		[line1path appendBezierPathWithPoints:line1 count:2];
		NSBezierPath *line2path = [NSBezierPath bezierPath];
		[line2path setMiterLimit:15.0];
		[line2path appendBezierPathWithPoints:line2 count:3];
		[line1path setLineWidth:3.0];
		[line2path setLineWidth:3.0];
		[line1path stroke];
		[line2path stroke];
	}	
	BOOL pointIsSelected = ([[screenPoint.videoClip.project.document.eventsPointsController selectedObjects] count] > 0 && [[screenPoint.videoClip.project.document.eventsPointsController selectedObjects] containsObject:screenPoint.point]);
	if (pointIsSelected) [self drawSelectionIndicatorAtPoint:point forShapeOfSize:shapeSize];
}

- (void) drawSelectionIndicatorAtPoint:(NSPoint)point forShapeOfSize:(float)shapeSize
{
	float selectionLineLength = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pointSelectionIndicatorLineLength"] floatValue];
	float selectionLineWidth = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pointSelectionIndicatorLineWidth"] floatValue];
	float selectionLineSizeFactor = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pointSelectionIndicatorSizeFactor"] floatValue];
	NSColor *selectionLineColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"pointSelectionIndicatorColor"]];
	
	NSBezierPath *mainPath = [NSBezierPath bezierPath];
	NSBezierPath *outlinePath = [NSBezierPath bezierPath];
	float outlineWidth = 0.3;
	float indicatorDistance = selectionLineSizeFactor*shapeSize;
	[mainPath moveToPoint:NSMakePoint(point.x+indicatorDistance,point.y)];
	[mainPath lineToPoint:NSMakePoint(point.x+indicatorDistance+selectionLineLength,point.y)];
	[mainPath moveToPoint:NSMakePoint(point.x-indicatorDistance,point.y)];
	[mainPath lineToPoint:NSMakePoint(point.x-indicatorDistance-selectionLineLength,point.y)];
	[mainPath moveToPoint:NSMakePoint(point.x,point.y+indicatorDistance)];
	[mainPath lineToPoint:NSMakePoint(point.x,point.y+indicatorDistance+selectionLineLength)];
	[mainPath moveToPoint:NSMakePoint(point.x,point.y-indicatorDistance)];
	[mainPath lineToPoint:NSMakePoint(point.x,point.y-indicatorDistance-selectionLineLength)];

	[outlinePath moveToPoint:NSMakePoint(point.x+indicatorDistance-outlineWidth,point.y)];
	[outlinePath lineToPoint:NSMakePoint(point.x+indicatorDistance+selectionLineLength+outlineWidth,point.y)];
	[outlinePath moveToPoint:NSMakePoint(point.x-indicatorDistance+outlineWidth,point.y)];
	[outlinePath lineToPoint:NSMakePoint(point.x-indicatorDistance-selectionLineLength-outlineWidth,point.y)];
	[outlinePath moveToPoint:NSMakePoint(point.x,point.y+indicatorDistance-outlineWidth)];
	[outlinePath lineToPoint:NSMakePoint(point.x,point.y+indicatorDistance+selectionLineLength+outlineWidth)];
	[outlinePath moveToPoint:NSMakePoint(point.x,point.y-indicatorDistance+outlineWidth)];
	[outlinePath lineToPoint:NSMakePoint(point.x,point.y-indicatorDistance-selectionLineLength-outlineWidth)];

	[mainPath setLineWidth:selectionLineWidth];
	[outlinePath setLineWidth:selectionLineWidth+2*outlineWidth];
	[[NSColor blackColor] set];
	[outlinePath stroke];
	[selectionLineColor set];
	[mainPath stroke];
}

- (void) drawHintLines
{
	VideoWindowController *vwc = _delegate;
	CMTime now = [vwc.videoClip.project.document currentMasterTime];
	NSString *hintLinesSetting = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"hintLinesSetting"];
	if (![hintLinesSetting isEqualToString:@"None"]) {	
		NSSet *visibleHintLines = [NSSet set];	// initialize as an empty set
		NSPredicate *currentTimePredicate = [NSPredicate predicateWithFormat:@"fromScreenPoint.point.timecode = %@",[UtilityFunctions CMStringFromTime:now]];
		NSSet *currentHintLines = [vwc.videoClip.hintLines filteredSetUsingPredicate:currentTimePredicate];	// all hintLines for the current timecode
		if ([hintLinesSetting isEqualToString:@"All"]) {
			visibleHintLines = currentHintLines;
		} else {	// setting is "Unpaired"; show only unpaired hintLines
			if ([currentHintLines count] > 0) {
				for (VSHintLine *hintLine in currentHintLines) {
					// if another VSEventScreenPoint for this VSHintLine's VSPoint has the same VSVideoClip as the VSHintLine does, it's paired.
					bool isPaired = false;
					for (VSEventScreenPoint *screenPoint in hintLine.fromScreenPoint.point.screenPoints) {						
						if ([screenPoint.videoClip isEqualTo:hintLine.toVideoClip]) isPaired = true;
					}
					if (!isPaired) visibleHintLines = [visibleHintLines setByAddingObject:hintLine];	// only add unpaired ones to the visibleHintLines
				}
			}
		}
		for (VSHintLine *hintLine in visibleHintLines) {	// only draw hintlines for the current timecode
			if ([hintLine.fromScreenPoint.point.trackedEvent.trackedObjects count] == 1) {	// If the line is associated with just one object, draw it.
				[self drawHintLine:hintLine 
						   ofWidth:1.0 
				 fromTrackedObject:[hintLine.fromScreenPoint.point.trackedEvent.trackedObjects anyObject]];
			} else {	// If the line is associated with more than one object, draw it as nested lines of increasing thickness, representing all their colors.
				for(int i=0; i < [hintLine.fromScreenPoint.point.trackedEvent.trackedObjects count]; i++) {
					float lineWidth = 2*([hintLine.fromScreenPoint.point.trackedEvent.trackedObjects count] - i);
					[self drawHintLine:hintLine 
							   ofWidth:lineWidth
					 fromTrackedObject:[[hintLine.fromScreenPoint.point.trackedEvent.trackedObjects allObjects] objectAtIndex:i]];
				}
			}
		}
	}	
}

- (void) drawHintLine:(VSHintLine *)hintLine ofWidth:(float)width fromTrackedObject:(VSTrackedObject *)obj
{
	float hintLineDrawInterval = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"hintLineDrawInterval"] floatValue];
	NSBezierPath *path = [hintLine bezierPathForLineWithInterval:hintLineDrawInterval];
	if (path) {
		[obj.color setStroke];
		[path setLineWidth:width];
		[path stroke];
	}
}


- (void) drawCalibrationScreenPoints
{
	VideoWindowController *vwc = _delegate;
	if ([vwc.videoClip isAtCalibrationTime]) {
		for (VSCalibrationPoint *backPoint in vwc.videoClip.calibration.pointsBack) {
			[self drawCalibrationScreenPoint:backPoint forSurface:@"Back"];
		}
		for (VSCalibrationPoint *frontPoint in vwc.videoClip.calibration.pointsFront) {
			[self drawCalibrationScreenPoint:frontPoint forSurface:@"Front"];
		}
	}
}

- (void) drawCalibrationScreenPoint:(VSCalibrationPoint *)calibrationPoint forSurface:(NSString *)whichSurface
{
	NSPoint videoPoint = NSMakePoint([calibrationPoint.screenX floatValue],[calibrationPoint.screenY floatValue]);
	if (videoPoint.x == 0.0 && videoPoint.y == 0.0) return;
	VideoWindowController *vwc = _delegate;
	NSPoint point = [vwc convertVideoToOverlayCoords:videoPoint];
	NSPoint textOffset;
	float radius;
	NSColor *pointColor;
	CalibScreenPtArrayController *pointsArrayController;
	if ([whichSurface isEqual: @"Front"]) {
		pointColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratOverlayColorFront"]];
		radius = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratPointOverlayCircleDiameterFront"] floatValue];
		textOffset = NSMakePoint(1.2*radius,-1.1*radius);
		pointsArrayController = calibrationPoint.calibration.videoClip.project.document.calibScreenPtFrontArrayController;
	} else {
		pointColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratOverlayColorBack"]];
		radius = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratPointOverlayCircleDiameterBack"] floatValue];
		textOffset = NSMakePoint(1.2*radius,-1.63*radius);
		pointsArrayController = calibrationPoint.calibration.videoClip.project.document.calibScreenPtBackArrayController;
	}
	// draw the circle around the point
	[pointColor setStroke];
	NSRect circleRect = NSMakeRect(point.x-radius,point.y-radius,2.0*radius,2.0*radius);
	NSBezierPath *circle = [NSBezierPath bezierPathWithOvalInRect:circleRect];
	[circle setLineWidth:3.0];
	[circle stroke];
	// draw the dot at the point
	[pointColor setFill];
	NSRect centerPoint = NSMakeRect(point.x-1.5, point.y-1.5, 3.0, 3.0);
    NSRectFill(centerPoint);
	// draw the selection indicator, if the point is selected
	
	BOOL pointIsSelected = ([[pointsArrayController selectedObjects] count] > 0 && [[pointsArrayController selectedObjects] containsObject:calibrationPoint]);
	if (pointIsSelected) [self drawSelectionIndicatorAtPoint:point forShapeOfSize:radius];
	
	// draw the text label
	
	if ([[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showWorldCoordinatesNextToQuadratPoints"] boolValue]) {
		float worldX = 0.0;
        float worldY = 0.0;
        float worldZ = 0.0;
		if ([vwc.videoClip.calibration.axisHorizontal isEqualToString:@"x"]) {
			worldX = [calibrationPoint.worldHcoord floatValue];
			if ([vwc.videoClip.calibration.axisVertical isEqualToString:@"y"]) {
				worldY = [calibrationPoint.worldVcoord floatValue];	
				if ([whichSurface isEqual: @"Front"]) {
					worldZ = [vwc.videoClip.calibration.planeCoordFront floatValue];
				} else if ([whichSurface isEqual: @"Back"]) {
					worldZ = [vwc.videoClip.calibration.planeCoordBack floatValue];
				}
			} else if ([vwc.videoClip.calibration.axisVertical isEqualToString:@"z"]) {
				worldZ = [calibrationPoint.worldVcoord floatValue];		
				if ([whichSurface isEqual: @"Front"]) {
					worldY = [vwc.videoClip.calibration.planeCoordFront floatValue];
				} else if ([whichSurface isEqual: @"Back"]) {
					worldY = [vwc.videoClip.calibration.planeCoordBack floatValue];
				}			
			}
		} else if ([vwc.videoClip.calibration.axisHorizontal isEqualToString:@"y"]) {
			worldY = [calibrationPoint.worldHcoord floatValue];
			if ([vwc.videoClip.calibration.axisVertical isEqualToString:@"x"]) {
				worldX = [calibrationPoint.worldVcoord floatValue];	
				if ([whichSurface isEqual: @"Front"]) {
					worldZ = [vwc.videoClip.calibration.planeCoordFront floatValue];
				} else if ([whichSurface isEqual: @"Back"]) {
					worldZ = [vwc.videoClip.calibration.planeCoordBack floatValue];
				}			
			} else if ([vwc.videoClip.calibration.axisVertical isEqualToString:@"z"]) {
				worldZ = [calibrationPoint.worldVcoord floatValue];		
				if ([whichSurface isEqual: @"Front"]) {
					worldX = [vwc.videoClip.calibration.planeCoordFront floatValue];
				} else if ([whichSurface isEqual: @"Back"]) {
					worldX = [vwc.videoClip.calibration.planeCoordBack floatValue];
				}			
			}		
		} else if ([vwc.videoClip.calibration.axisHorizontal isEqualToString:@"z"]) {
			worldZ = [calibrationPoint.worldHcoord floatValue];
			if ([vwc.videoClip.calibration.axisVertical isEqualToString:@"x"]) {
				worldX = [calibrationPoint.worldVcoord floatValue];	
				if ([whichSurface isEqual: @"Front"]) {
					worldY = [vwc.videoClip.calibration.planeCoordFront floatValue];
				} else if ([whichSurface isEqual: @"Back"]) {
					worldY = [vwc.videoClip.calibration.planeCoordBack floatValue];
				}			
			} else if ([vwc.videoClip.calibration.axisVertical isEqualToString:@"y"]) {
				worldY = [calibrationPoint.worldVcoord floatValue];		
				if ([whichSurface isEqual: @"Front"]) {
					worldX = [vwc.videoClip.calibration.planeCoordFront floatValue];
				} else if ([whichSurface isEqual: @"Back"]) {
					worldX = [vwc.videoClip.calibration.planeCoordBack floatValue];
				}			
			}	
		}
		NSDictionary *textAttributes = [NSDictionary dictionaryWithObjectsAndKeys:
										[NSFont fontWithName:@"Helvetica" size:11.0],NSFontAttributeName,
										pointColor,NSForegroundColorAttributeName,nil];
		NSString *label = [NSString stringWithFormat:@"%1.2f\n%1.2f\n%1.2f",worldX,worldY,worldZ];
		[label drawAtPoint:NSMakePoint(point.x+textOffset.x,point.y+textOffset.y) withAttributes:textAttributes];
	}
}



- (void) drawQuadratCoordinateGrids
{
	BOOL shouldDrawFront = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratShowSurfaceGridOverlayFront"] boolValue];
	BOOL shouldDrawBack = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratShowSurfaceGridOverlayBack"] boolValue];
	NSColor *frontColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratOverlayColorFront"]];
	NSColor *backColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratOverlayColorBack"]];
	
	if ((shouldDrawFront || shouldDrawBack) && quadratCoordinateGrids == nil) {	// quadratCoordinateGrids holds a multidimensional array of NSBezierPaths representing all the grid lines
		[self calculateQuadratCoordinateGrids];
	}
	if (shouldDrawBack) {
		[backColor setStroke];
		for (NSArray *directionArray in [quadratCoordinateGrids objectAtIndex:1]) {
			for (NSBezierPath *path in directionArray) [path stroke];
		}
	}		
	if (shouldDrawFront) {
		[frontColor setStroke];
		for (NSArray *directionArray in [quadratCoordinateGrids objectAtIndex:0]) {
			for (NSBezierPath *path in directionArray) [path stroke];
		}
	}
}

- (void) calculateQuadratCoordinateGrids
{
	quadratCoordinateGrids = [NSArray arrayWithObjects:
							  [NSArray arrayWithObjects:
                               [self quadratCoordinateGridForSurface:@"Front"],
							   nil],
							  [NSArray arrayWithObjects:
                               [self quadratCoordinateGridForSurface:@"Back"],
							   nil],
							  nil];
}


#pragma mark
#pragma mark Quadrat Coordinate Grid Overlay

- (NSArray *) quadratCoordinateGridForSurface:(NSString *)surface
{
	// Returns an NSArray of NSBezierPaths, one representing all the grid lines, and one (thicker) representing the two x=0, y=0 axes.    
    VideoWindowController *vwc = _delegate;
	NSMutableArray *outPathsArray = [NSMutableArray new];
	
    // Here we configure the spacing for the overlay grid automatically based on the distance between the first two points in world coordinates.
    // Having user-configured spacings creates major problems when a default value like 0.1 (for using meters) is applied to someone using millimeters for their units (millions of grid nodes slow everything down)
    NSSet *calibPoints = ([surface isEqualToString:@"Front"]) ? vwc.videoClip.calibration.pointsFront : vwc.videoClip.calibration.pointsBack;
    if ([calibPoints count] < 2) return outPathsArray;
    NSArray *calibPointsOrdered = [[calibPoints allObjects] sortedArrayUsingDescriptors:[NSArray arrayWithObjects:[NSSortDescriptor sortDescriptorWithKey:@"worldHcoord" ascending:YES],[NSSortDescriptor sortDescriptorWithKey:@"worldVcoord" ascending:YES],nil]];
    float hGridSpacing = abs([[[calibPointsOrdered objectAtIndex:1] worldHcoord] floatValue] - [[[calibPointsOrdered objectAtIndex:2] worldHcoord] floatValue]);
    float vGridSpacing= abs([[[calibPointsOrdered objectAtIndex:1] worldVcoord] floatValue] - [[[calibPointsOrdered objectAtIndex:2] worldVcoord] floatValue]);
    float gridSpacing = (hGridSpacing > vGridSpacing) ? hGridSpacing : vGridSpacing;
        
	float lineWidth = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratGridOverlayLineThickness"] floatValue];
    
    NSPoint bottomLeft = [vwc.videoClip.calibration projectScreenPoint:NSMakePoint(0.0,0.0) toQuadratSurface:surface];
    NSPoint bottomRight = [vwc.videoClip.calibration projectScreenPoint:NSMakePoint([vwc.videoClip clipWidth],0.0) toQuadratSurface:surface];
    NSPoint topLeft = [vwc.videoClip.calibration projectScreenPoint:NSMakePoint(0.0,[vwc.videoClip clipHeight]) toQuadratSurface:surface];
    NSPoint topRight = [vwc.videoClip.calibration projectScreenPoint:NSMakePoint([vwc.videoClip clipWidth],[vwc.videoClip clipHeight]) toQuadratSurface:surface];
    float maxX = bottomLeft.x;
    float minX = bottomLeft.x;
    float maxY = bottomLeft.y;
    float minY = bottomLeft.y;
    if (bottomRight.x > maxX) maxX = bottomRight.x;
    if (bottomRight.x < minX) minX = bottomRight.x;
    if (topLeft.x > maxX) maxX = topLeft.x;
    if (topLeft.x < minX) minX = topLeft.x;
    if (topRight.x > maxX) maxX = topRight.x;
    if (topRight.x < minX) minX = topRight.x;
    if (bottomRight.y > maxY) maxY = bottomRight.y;
    if (bottomRight.y < minY) minY = bottomRight.y;
    if (topLeft.y > maxY) maxY = topLeft.y;
    if (topLeft.y < minY) minY = topLeft.y;
    if (topRight.y > maxY) maxY = topRight.y;
    if (topRight.y < minY) minY = topRight.y;    
    maxX = ceilf(maxX/gridSpacing) * gridSpacing;
    minX = floorf(minX/gridSpacing) * gridSpacing;
    maxY = ceilf(maxY/gridSpacing) * gridSpacing;
    minY = floorf(minY/gridSpacing) * gridSpacing;
    
    NSBezierPath *path = [NSBezierPath bezierPath];
    NSBezierPath *axisPath = [NSBezierPath bezierPath];
	[path setLineWidth:lineWidth];    
    [axisPath setLineWidth:lineWidth*2.5];
    NSPoint pt, overlayPt;
    for (float x = minX; x <= maxX; x += gridSpacing) {
        for (float y = minY; y <= maxY; y += (maxY - minY)/100) {
            pt = [vwc.videoClip.calibration projectToScreenFromPoint:NSMakePoint(x,y) onQuadratSurface:surface redistort:TRUE];
            overlayPt = [vwc convertVideoToOverlayCoords:pt];
            if (y == minY) {
                [path moveToPoint:overlayPt];
                if (fabs(x) < 0.1*gridSpacing) [axisPath moveToPoint:overlayPt];    // equivalent to if(x == 0), accounting for floating point errors
            } else {
                [path lineToPoint:overlayPt];
                if (fabs(x) < 0.1*gridSpacing) [axisPath lineToPoint:overlayPt];
            }
        }
    }
    for (float y = minY; y <= maxY; y += gridSpacing) {
        for (float x = minX; x <= maxX; x += (maxX - minX)/100) {
            pt = [vwc.videoClip.calibration projectToScreenFromPoint:NSMakePoint(x,y) onQuadratSurface:surface redistort:TRUE];
            overlayPt = [vwc convertVideoToOverlayCoords:pt];
            if (x == minX) {
                [path moveToPoint:overlayPt];
                if (fabs(y) < 0.1*gridSpacing) [axisPath moveToPoint:overlayPt];    // equivalent to if(x == 0), accounting for floating point errors
            } else {
                [path lineToPoint:overlayPt];
                if (fabs(y) < 0.1*gridSpacing) [axisPath lineToPoint:overlayPt];
            }
        }
    }                                                                                        
    [outPathsArray addObject:path];
    [outPathsArray addObject:axisPath];
    return outPathsArray;
}

#pragma mark
#pragma mark Event Handling

- (void)mouseMoved:(NSEvent *)theEvent {
	VideoWindowController *vwc = _delegate;
	NSPoint mousePosition = [self convertPoint:[theEvent locationInWindow] fromView:nil];
    mousePosition.x = floor(mousePosition.x);   // Here, I'm accounting for a weird bug in Lion in which mouseMoved events deliver apparently "subpixel" coordinates but
    mousePosition.y = ceil(mousePosition.y);    // mouseDown doesn't, so the position of a click doesn't match where the mouse had moved to.  The subpixel coordinates weren't real anyway.
	[vwc updateMagnifiedPreviewWithCenter:[vwc convertOverlayToVideoCoords:mousePosition]];
	[[vwc window] makeKeyAndOrderFront:nil]; // the delegate is the VideoWindowController
	[vwc makeOverlayKeyWindow];	// make the overlay the key window, so it receives keyDown events
	[vwc.document setFrontVideoClip:vwc.videoClip];
}

- (void)mouseDown:(NSEvent *)theEvent {	
	NSPoint mousePosition = [self convertPoint:[theEvent locationInWindow] fromView:nil];
	[_delegate handleOverlayClick:mousePosition fromEvent:theEvent];	// tell the VideoWindowController to figure out what to do
}

- (void)rightMouseDown:(NSEvent *)theEvent {	
	NSPoint mousePosition = [self convertPoint:[theEvent locationInWindow] fromView:nil];
	[_delegate handleOverlayRightClick:mousePosition];	// tell the VideoWindowController to figure out what to do
}

- (void)otherMouseDown:(NSEvent *)theEvent {	// Clicking the 4th mouse button (left side button on mine) snaps a new point to the nearest corner unless the OS grabs that button first
    if ([theEvent buttonNumber] == 3) {
        NSPoint mousePosition = [self convertPoint:[theEvent locationInWindow] fromView:nil];
        [_delegate handleOverlayClick:mousePosition fromEvent:theEvent];	// tell the VideoWindowController to figure out what to do
    }
}

- (BOOL)acceptsFirstResponder {
	return YES;
}

- (void)keyUp:(NSEvent *)theEvent {
	VideoWindowController *vwc = _delegate;
	[vwc handleOverlayKeyUp:theEvent];
}

- (void)keyDown:(NSEvent *)theEvent {
	VideoWindowController *vwc = _delegate;
	[vwc handleOverlayKeyDown:theEvent];	
}

- (void)scrollWheel:(NSEvent *)theEvent {
	VideoWindowController *vwc = _delegate;
    if ([theEvent deltaY] > 0.0) {
        [vwc.document stepBackwardAll:self];
    } else if ([theEvent deltaY] < 0.0) {
        [vwc.document stepForwardAll:self];
    }
    
}

@end
