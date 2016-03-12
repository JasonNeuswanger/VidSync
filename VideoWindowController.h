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
#import "VSVideoClip.h"
#import "VideoOverlayView.h"
#import "VideoClipArrayController.h"

@class VideoClipArrayController;

@interface VideoWindowController : NSWindowController {

	NSManagedObjectContext *__weak managedObjectContext;
	
    IBOutlet AVPlayerView *__weak playerView;
	
	IBOutlet NSPanel *__weak newAnnotationPanel;
	IBOutlet NSTextView *__strong newAnnotationContents;    // class NSTextView does not support weak references
	NSPoint newAnnotationCoords;
	NSString *newAnnotationStartTimecode;
	
	VSVideoClip *__weak videoClip;
	AVPlayerItem *__strong playerItem;
    AVAssetTrack *__strong videoTrack;
    AVAsset *__strong videoAsset;
    AVPlayerLayer *__strong playerLayer;
    AVAssetImageGenerator *__strong assetImageGenerator;
	CGSize movieSize;
	
	NSWindow *__strong overlayWindow;
	VideoOverlayView *__strong overlayView;
	float overlayWidth,overlayHeight;
    
    NSPoint portraitDragStartCoords, portraitDragCurrentCoords;
    NSString *__strong shouldShowPortraitFrame;
		
}

@property (weak) VSVideoClip *videoClip;
@property (strong) AVAssetTrack *videoTrack;
@property (strong) AVPlayerItem *playerItem;
@property (strong) AVAsset *videoAsset;
@property (strong) AVPlayerLayer *playerLayer;
@property (strong) AVAssetImageGenerator *assetImageGenerator;
@property (weak) IBOutlet AVPlayerView *playerView;
@property (assign) CGSize movieSize;
@property (weak) NSManagedObjectContext *managedObjectContext;
@property (strong) VideoOverlayView *overlayView;
@property (assign) float overlayWidth;
@property (assign) float overlayHeight;
@property (assign) NSPoint portraitDragStartCoords;
@property (assign) NSPoint portraitDragCurrentCoords;
@property (strong) NSString *shouldShowPortraitFrame;

- (VideoWindowController *)initWithVideoClip:(VSVideoClip *)inVideoClip inManagedObjectContext:(NSManagedObjectContext *)moc;
- (void)setUpPlaybackOfAsset:(AVAsset *)asset withKeys:(NSArray *)keys;
- (AVAsset *) playableAssetForClipName:(NSString *)clipName atPath:(NSString *)filePath;

- (NSString *)windowTitleForDocumentDisplayName:(NSString *)displayName;

- (void) windowDidLoad;

- (void) makeOverlayKeyWindow;
- (void) fitVideoOverlay;

- (void) updateMagnifiedPreviewWithCenter:(NSPoint)point;

- (void) handleOverlayKeyUp:(NSEvent *)theEvent;
- (void) handleOverlayKeyDown:(NSEvent *)theEvent;
- (void) handleOverlayKeyDownInDistortionMode:(NSEvent *)theEvent;
- (void) handleOverlayKeyDownInCalibrateMode:(NSEvent *)theEvent;
- (void) handleOverlayKeyDownInMeasureMode:(NSEvent *)theEvent;
- (void) handleOverlayKeyDownInAnnotateMode:(NSEvent *)theEvent;

- (void) handleOverlayClick:(NSPoint)coords fromEvent:(NSEvent *)theEvent;
- (void) handleOverlayMouseUp:(NSPoint)coords fromEvent:(NSEvent *)theEvent;
- (void) handleOverlayMouseDrag:(NSPoint)coords fromEvent:(NSEvent *)theEvent;
- (void) handleOverlayRightClick:(NSPoint)coords;
- (IBAction) createNewAnnotation:(id)sender;
- (void) handleOverlayRightClickInDistortionMode:(NSPoint)coords;
- (void) handleOverlayRightClickInCalibrateMode:(NSPoint)coords;
- (void) handleOverlayRightClickInMeasureMode:(NSPoint)coords;
- (void) handleOverlayRightClickInAnnotateMode:(NSPoint)coords;

- (NSPoint) convertVideoToOverlayCoords:(NSPoint)videoCoords;
- (NSRect) convertVideoToOverlayRect:(NSRect)videoRect;
- (NSPoint) convertOverlayToVideoCoords:(NSPoint)annotationCoords;

- (IBAction) setAsMaster:(id)sender;
- (IBAction) lockSyncOffset:(id)sender;
- (IBAction) resizeToVideoPercent:(id)sender;
- (void) resizeVideoToFactor:(float)sizeFactor;
- (void) setMovieViewControllerVisible:(BOOL)setting;
- (void) processSynchronizationStatus;
- (void) updateMasterTimeScrubberTicks;
- (void) refreshOverlay;

@end


@interface NSObject (NSWindow) // NSWindowDelegate delegate methods for the window being controlled

- (void)windowDidResize:(NSNotification *)notification;
- (void)windowDidMove:(NSNotification *)notification;

@end
