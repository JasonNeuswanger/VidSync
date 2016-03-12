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
    
    NSSet *__strong visibleScreenPoints;
    NSSet *__strong visibleAnnotations;

    VideoWindowController *__weak vwc;
    
}

@property (weak) VideoWindowController *vwc;

@property (strong) NSSet * visibleScreenPoints;
@property (strong) NSSet * visibleAnnotations;

- (void)drawRect:(NSRect)rect;
- (id)initWithFrame:(NSRect)frame andWindowController:(VideoWindowController *)windowController;

- (void) calculateVisibleScreenPoints;
- (void) drawHintLines;
- (void) drawHintLine:(VSHintLine *)hintLine ofWidth:(float)width fromTrackedObject:(VSTrackedObject *)obj;
- (void) drawScreenPointToIdealScreenPointComparison;
- (void) drawMeasurementScreenPoints;
- (void) drawMeasurementScreenPoint:(VSEventScreenPoint *)screenPoint fromTrackedObject:(VSTrackedObject *)pointsObject withOpacity:(float)opacity magnification:(float)magnification;
- (void) drawSelectionIndicatorAtPoint:(NSPoint)point forShapeOfSize:(float)shapeSize opacity:(float)opacity;
- (void) drawConnectingLinesForTrackedEvent:(VSTrackedEvent *)trackedEvent;
- (void) drawConnectingLinesLabelFromVSPoint:(VSPoint *)point toVSPoint:(VSPoint *)otherPoint onLine:(NSPoint[2])line inColor:(NSColor *)color do_distance:(BOOL)do_distance do_speed:(BOOL)do_speed;
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
