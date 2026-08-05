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

	BOOL isRenderingForExport;		// while set, drawing uses exportRenderTime instead of the live playback time and skips interactive chrome
	CMTime exportRenderTime;

}

@property (weak) VideoWindowController *vwc;

@property (strong) NSSet * visibleScreenPoints;
@property (strong) NSSet * visibleAnnotations;

@property (assign) BOOL isRenderingForExport;
@property (assign) CMTime exportRenderTime;

- (void)drawRect:(NSRect)rect;
- (void)drawOverlayContent;
- (id)initWithFrame:(NSRect)frame andWindowController:(VideoWindowController *)windowController;

// Time accessors all drawing goes through: the live master time normally, the export time while
// rendering offscreen for the export queue. clipIsAtCalibrationTimeForRender is the export-aware
// stand-in for VSVideoClip's isAtCalibrationTime, which reads the live player position.
- (CMTime) renderMasterTime;
- (NSString *) renderMasterTimeString;
- (BOOL) clipIsAtCalibrationTimeForRender;

// Renders the overlay for an arbitrary master time into a fresh bitmap of the given pixel size
// (normally the video's native size), without moving the video or touching the screen. Drawing
// happens in the view's own coordinate system under a scaling transform, so everything lands
// exactly where it does on screen but at full video resolution. Returns a +1 retained CGImage
// (or NULL); the caller must CGImageRelease it. Main thread only.
- (CGImageRef) newOverlayImageForExportAtMasterTime:(CMTime)masterTime pixelSize:(CGSize)pixelSize;

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
