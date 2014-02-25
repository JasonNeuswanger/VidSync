//
//  VideoOverlayView.h
//  VidSync
//
//  Created by Jason Neuswanger on 10/26/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class VideoWindowController;
@class VSCalibrationPoint;
@class VSEventScreenPoint;
@class VSTrackedObject;
@class VSHintLine;
@class VSTrackedEvent;
@class VSAnnotation;
@class VSPoint;

@interface VideoOverlayView : NSView {

	NSTrackingArea *__strong trackingArea;
	NSArray *__strong quadratCoordinateGrids;
    
}

@property (weak) id delegate; // I make the VideoWindowController a delegate, so I can call its methods when click things happen in the view.

@property (strong) NSSet * visibleScreenPoints;
@property (strong) NSSet * visibleAnnotations;

- (void)drawRect:(NSRect)rect;
- (id)initWithFrame:(NSRect)frameRect;

- (void) calculateVisibleScreenPoints;
- (void) drawHintLines;
- (void) drawHintLine:(VSHintLine *)hintLine ofWidth:(float)width fromTrackedObject:(VSTrackedObject *)obj;
- (void) drawScreenPointToIdealScreenPointComparison;
- (void) drawMeasurementScreenPoints;
- (void) drawMeasurementScreenPoint:(VSEventScreenPoint *)screenPoint fromTrackedObject:(VSTrackedObject *)pointsObject withOpacity:(float)opacity magnification:(float)magnification;
- (void) drawSelectionIndicatorAtPoint:(NSPoint)point forShapeOfSize:(float)shapeSize opacity:(float)opacity;
- (void) drawConnectingLinesForTrackedEvent:(VSTrackedEvent *)trackedEvent;
- (void) drawConnectingLinesLengthLabelFromVSPoint:(VSPoint *)point toVSPoint:(VSPoint *)otherPoint onLine:(NSPoint[2])line inColor:(NSColor *)color;
- (void) drawDistortionCorrections;
- (void) drawPortraitSelectionBox;

- (void) calculateVisibleAnnotations;
- (void) drawAnnotations;
- (void) drawAnnotation:(VSAnnotation *)annotation;

- (void) drawCalibrationScreenPoints;
- (void) drawCalibrationScreenPoint:(VSCalibrationPoint *)screenPoint forSurface:(NSString *)whichSurface;
- (void) drawQuadratCoordinateGrids;
- (void) calculateQuadratCoordinateGrids;
- (NSArray *) quadratCoordinateGridForSurface:(NSString *)surface;

- (void)mouseMoved:(NSEvent *)theEvent;
- (void)mouseDown:(NSEvent *)theEvent;
- (void)mouseDragged:(NSEvent *)theEvent;
- (void)mouseUp:(NSEvent *)theEvent;
- (void)rightMouseDown:(NSEvent *)theEvent;
- (void)keyDown:(NSEvent *)theEvent;
- (BOOL)acceptsFirstResponder;
- (void)scrollWheel:(NSEvent *)theEvent;

@end

@interface NSObject (VideoWindowController) // spot to write out the delegate methods so I don't get lots of "not found" warnings

- (void) handleOverlayClick:(NSPoint)coords;
- (void) handleOverlayRightClick:(NSPoint)coords;
- (void) updateMagnifiedPreviewWithCenter:(NSPoint)point;
- (NSPoint) convertVideoToOverlayCoords:(NSPoint)videoCoords;
- (NSPoint) convertOverlayToVideoCoords:(NSPoint)annotationCoords;

@end
