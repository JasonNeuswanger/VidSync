//
//  VideoWindowController.h
//  VidSync
//
//  Created by Jason Neuswanger on 10/26/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
#import "VSVideoClip.h"
#import "VideoOverlayView.h"
#import "VideoClipArrayController.h"

@class VideoClipArrayController;

@interface VideoWindowController : NSWindowController {

	NSManagedObjectContext *__weak managedObjectContext;
	
    IBOutlet AVPlayerView *__weak playerView;
	
	IBOutlet NSPanel *newAnnotationPanel;
	IBOutlet NSTextField *newAnnotationContents;
	NSPoint newAnnotationCoords;
	NSString *newAnnotationStartTimecode;
	
	VSVideoClip *__weak videoClip;
	AVPlayerItem *__weak playerItem;
    AVAssetTrack *__weak videoTrack;
    AVAsset *__weak videoAsset;
    AVPlayerLayer *__strong playerLayer;
    AVAssetImageGenerator *__strong assetImageGenerator;
	CGSize movieSize;
	
	NSWindow *overlayWindow;
	VideoOverlayView *overlayView;
	float overlayWidth,overlayHeight;
    
    NSPoint portraitDragStartCoords, portraitDragCurrentCoords;
    NSString *__strong shouldShowPortraitFrame;
		
}

@property (weak) QTMovie *movie;
@property (weak) VSVideoClip *videoClip;
@property (weak) AVAssetTrack *videoTrack;
@property (weak) AVPlayerItem *playerItem;
@property (weak) AVAsset *videoAsset;
@property (strong) AVPlayerLayer *playerLayer;
@property (strong) AVAssetImageGenerator *assetImageGenerator;
@property (weak) IBOutlet AVPlayerView *playerView;
@property (assign) CGSize movieSize;
@property (weak) NSManagedObjectContext *managedObjectContext;
@property  VideoOverlayView *overlayView;
@property float overlayWidth;
@property float overlayHeight;
@property NSPoint portraitDragStartCoords;
@property NSPoint portraitDragCurrentCoords;
@property (strong) NSString *shouldShowPortraitFrame;

- (VideoWindowController *)initWithVideoClip:(VSVideoClip *)inVideoClip inManagedObjectContext:(NSManagedObjectContext *)moc;
- (void)setUpPlaybackOfAsset:(AVAsset *)asset withKeys:(NSArray *)keys;
- (NSString *) locateMovieFileForClipName:(NSString *)clipName;

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
- (void) refreshOverlay;

@end


@interface NSObject (NSWindow) // NSWindowDelegate delegate methods for the window being controlled

- (void)windowDidResize:(NSNotification *)notification;
- (void)windowDidMove:(NSNotification *)notification;

@end
