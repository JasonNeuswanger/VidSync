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
@class MagnifiedPreviewView;
@class VideoClipArrayController;
@class TrackedObjectArrayController;
@class TrackedEventArrayController;
@class EventsPointsController;
@class CalibScreenPtArrayController;
@class VSVideoClip;
@class VSTrackedObject;
@class TypeIndexNameSortedArrayController;
@class EventsOtherObjectsArrayController;
@class VSVisibleItemArrayController;
@class ObjectSynonymizeArrayController;
@class TypesArrayController;
@class CalibDistortionLineArrayController;
@class VideoControlButton;
@class PlayWhilePressedButton;
@class SyncedPlaybackView;
@class SyncedPlaybackPanel;
@class ObjectsPortraitsArrayController;
@class AllPortraitsArrayController;
@class MainProjectWindow;

@interface VidSyncDocument: NSPersistentDocument {
	
	NSManagedObjectModel *__strong managedObjectModel;
	
	VSProject *__weak project;
    
	NSTimer *__strong playbackTimer;
    
    IBOutlet NSTextField *__weak projectNameDisplayInSyncedPlaybackWindow;
    IBOutlet NSObjectController *__weak projectController;
    IBOutlet TypeIndexNameSortedArrayController *__weak eventsObjectsController;
    IBOutlet TypeIndexNameSortedArrayController *__weak objectsEventsController;
    IBOutlet EventsOtherObjectsArrayController *__weak eventsOtherObjectsController;
    IBOutlet AllPortraitsArrayController *__weak allPortraitsArrayController;
    IBOutlet ObjectsPortraitsArrayController *__weak objectsPortraitsArrayController;

    
	IBOutlet MagnifiedPreviewView *__weak magnifiedCalibrationPreview,*__weak magnifiedMeasurementPreview,*__weak magnifiedDistortionPreview;
	IBOutlet VideoClipArrayController *__weak videoClipArrayController;
	IBOutlet CalibScreenPtArrayController *__weak calibScreenPtFrontArrayController;
	IBOutlet CalibScreenPtArrayController *__weak calibScreenPtBackArrayController;
	IBOutlet TrackedObjectArrayController *__weak trackedObjectsController;
	IBOutlet TrackedEventArrayController *__weak trackedEventsController;
	IBOutlet TypesArrayController *__weak trackedObjectTypesController;
	IBOutlet TypesArrayController *__weak trackedEventTypesController;	
	IBOutlet EventsPointsController *__weak eventsPointsController;
	IBOutlet VSVisibleItemArrayController *__weak annotationsController;
	IBOutlet VSVisibleItemArrayController *__weak distortionPointsController;
	IBOutlet CalibDistortionLineArrayController *__weak distortionLinesController;	
	IBOutlet ObjectSynonymizeArrayController *__weak objectSynonymizeController;
	IBOutlet NSTableView *__weak eventsPointsTable;
	
    IBOutlet NSWindowController *__strong syncedPlaybackWindowController;
    IBOutlet SyncedPlaybackPanel *__weak syncedPlaybackPanel;
    IBOutlet SyncedPlaybackView *__weak syncedPlaybackView;
    IBOutlet NSSlider *__weak syncedPlaybackScrubber;
    int scrubberMaxTime;
    
	IBOutlet PlayWhilePressedButton *__weak playForwardAtRate1WhilePressedButton,*__weak playBackwardAtRate1WhilePressedButton,*__weak playForwardAtRate2WhilePressedButton,*__weak playBackwardAtRate2WhilePressedButton,*__weak playForwardWhilePressedButton, *__weak playBackwardWhilePressedButton;
    
    IBOutlet VideoControlButton *__weak playOrPauseButton, *__weak playBackwardButton, *__weak playForwardAtRate1Button, *__weak playBackwardAtRate1Button, *__weak playForwardAtRate2Button, *__weak playBackwardAtRate2Button, *__weak instantReplayButton;
    
	CMTime bookmarkTime1, bookmarkTime2;
    BOOL bookmarkIsSet1, bookmarkIsSet2;
	
	IBOutlet NSTextField *__weak masterTimeDisplay;

	IBOutlet MainProjectWindow *__weak mainWindow;
	IBOutlet NSTabView *__weak mainTabView;
	IBOutlet NSTabView *__weak calibrationSurfaceTabView;
	IBOutlet NSTabView *__weak calibrationInputTabView;
	
	IBOutlet NSPopUpButton *__weak exportClipSelectionPopUpButton;
	IBOutlet NSProgressIndicator *__weak videoCaptureProgressIndicator;
    IBOutlet NSTextField *__weak videoCaptureProgressDescription;
	
	IBOutlet NSProgressIndicator *__weak pointRecalculateProgressIndicator;
	IBOutlet NSPanel *__weak pointRecalculatePanel;
	
	VSVideoClip *__weak frontVideoClip;	// whichever clip is the key window or in front of the other at the moment
	
	CMTime stopTime;							// These two are temporarily non-nil when playing to or from a stoptime.
	NSComparisonResult stopTimeComparison;
	
	NSSound *__strong shutterClick;
    
	NSNumberFormatter *__strong decimalFormatter;
    
    VSTrackedObject *__weak portraitSubject;
    
    IBOutlet NSButton *__weak allPortraitBrowserOpenButton;
    
    BOOL objectsTableSelectionChangeNotificationCascadeEnabled, eventsTableSelectionChangeNotificationCascadeEnabled;
    
    NSMutableSet *activeExportSessions;
	
}

@property (weak, nonatomic) VSProject *project; // was (weak, nonatomic)
@property (readonly, weak) IBOutlet NSTabView *mainTabView;
@property (readonly, weak) IBOutlet NSTabView *calibrationSurfaceTabView;
@property (readonly, weak) IBOutlet NSTabView *calibrationInputTabView;
@property (readonly, weak) IBOutlet VideoClipArrayController *videoClipArrayController;
@property (readonly, weak) IBOutlet CalibScreenPtArrayController *calibScreenPtFrontArrayController;
@property (readonly, weak) IBOutlet CalibScreenPtArrayController *calibScreenPtBackArrayController;
@property (readonly, weak) IBOutlet TrackedObjectArrayController *trackedObjectsController;
@property (readonly, weak) IBOutlet TrackedEventArrayController *trackedEventsController;
@property (readonly, weak) IBOutlet TypesArrayController *trackedObjectTypesController;
@property (readonly, weak) IBOutlet TypesArrayController *trackedEventTypesController;
@property (readonly, weak) IBOutlet EventsPointsController *eventsPointsController;
@property (readonly, weak) IBOutlet VSVisibleItemArrayController *annotationsController;
@property (readonly, weak) IBOutlet VSVisibleItemArrayController *distortionPointsController;
@property (readonly, weak) IBOutlet CalibDistortionLineArrayController *distortionLinesController;	
@property (readonly, weak) IBOutlet MainProjectWindow *mainWindow;

@property (strong) NSWindowController *syncedPlaybackWindowController;
@property (weak) IBOutlet SyncedPlaybackPanel *syncedPlaybackPanel;
@property (weak) IBOutlet NSSlider *syncedPlaybackScrubber;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playForwardWhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playBackwardWhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playForwardAtRate1WhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playBackwardAtRate1WhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playForwardAtRate2WhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playBackwardAtRate2WhilePressedButton;
@property (readonly, weak) IBOutlet VideoControlButton *playForwardAtRate1Button;
@property (readonly, weak) IBOutlet VideoControlButton *playBackwardAtRate1Button;
@property (readonly, weak) IBOutlet VideoControlButton *playForwardAtRate2Button;
@property (readonly, weak) IBOutlet VideoControlButton *playBackwardAtRate2Button;

@property (strong) NSNumberFormatter *decimalFormatter;
@property (weak) VSVideoClip *frontVideoClip;

@property (weak) IBOutlet MagnifiedPreviewView *magnifiedCalibrationPreview;
@property (weak) IBOutlet MagnifiedPreviewView *magnifiedMeasurementPreview;
@property (weak) IBOutlet MagnifiedPreviewView *magnifiedDistortionPreview;

@property (weak) IBOutlet ObjectsPortraitsArrayController *objectsPortraitsArrayController;

@property (weak) VSTrackedObject *portraitSubject;

@property (assign) BOOL bookmarkIsSet1;
@property (assign) BOOL bookmarkIsSet2;

@property (assign) BOOL objectsTableSelectionChangeNotificationCascadeEnabled;
@property (assign) BOOL eventsTableSelectionChangeNotificationCascadeEnabled;

- (id) initWithType:(NSString *)type error:(NSError **)error;
- (void) windowControllerDidLoadNib:(NSWindowController *)windowController;
- (void) syncedPlaybackPanelAwokeFromNib;
- (void) observeWindowControllerVideoRate:(VideoWindowController *)vwc;
- (VSProject *) project;

- (void) anyTableViewSelectionDidChange:(NSNotification *)notification;
- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context;

- (IBAction) resetPreviewMagnification:(id)sender;
- (IBAction) setPreviewFiltersToDefaults:(id)sender;
- (void) updatePreviewImageWithPlayerLayer:(AVPlayerLayer *)playerLayer atPoint:(NSPoint)point;


- (IBAction) setCalibrationTime:(id)sender;
- (IBAction) goToCalibrationTime:(id)sender;

- (IBAction) saveObjectAndEventTypesToFile:(id)sender;
- (IBAction) loadObjectAndEventTypesFromFile:(id)sender;
- (IBAction) loadObjectAndEventTypesExample:(id)sender;
- (void) loadObjectAndEventTypesFromFileAtPath:(NSString *)filePath;

- (IBAction) refreshOverlaysOfAllClips:(id)sender;
- (IBAction) recalculateAllPoints:(id)sender;

- (void) setPortraitSubject:(VSTrackedObject *)subject; // Not synthesizing the getters and setters here because the synthesized ones don't seem to
- (VSTrackedObject *) portraitSubject;                  // play nice with the Interface Builder bindings

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath;

@end

@interface VidSyncDocument (SimultaneousPlayback)

- (void) playbackLoopActions;
- (void) updateMasterTimeDisplay;


- (CMTime) currentMasterTime;
- (NSString *) currentMasterTimeString;
- (void) goToMasterTime:(CMTime)time;
- (BOOL) currentMasterTimeIs:(CMTime)time;

- (IBAction) setBookmark:(id)sender;
- (IBAction) goToBookmark:(id)sender;

- (IBAction) playAll:(id)sender;
- (IBAction) pauseAll:(id)sender;
- (IBAction) playAllBackward:(id)sender;
- (IBAction) stepForwardAll:(id)sender;
- (IBAction) stepBackwardAll:(id)sender;

- (IBAction) advancedPlayAll:(id)sender;
- (IBAction) advancedStepAll:(id)sender;
- (IBAction) instantReplay:(id)sender;
- (CMTime) stopTimeForDuration:(float)duration atRate:(float)rate;
- (void) checkForStopAtCurrentTime;
- (IBAction) setTimeFromScrubber:(id)sender;

- (void) setAllVideoRates:(float)rate;
- (void) movieTimeDidChange:(NSNotification *)notification;
- (void) movieRateDidChange;
- (void) reSync;

@end // VidSyncDocument (SimultaneousPlayback)

@interface VidSyncDocument (Capture)

- (IBAction)captureStills:(id)sender;
- (IBAction)capturePortraits:(id)sender;
- (IBAction)setVideoCaptureTime:(id)sender;
- (IBAction)goToVideoCaptureTime:(id)sender;
- (IBAction)chooseCapturePath:(id)sender;
- (IBAction)openCapturePathInFinder:(id)sender;
- (IBAction)captureVideoClips:(id)sender;

- (void) captureWithOverlayFromVideoClip:(VSVideoClip *)videoClip toFile:(NSString *)destination;
- (void) captureWithoutOverlayFromVideoClip:(VSVideoClip *)videoClip usingPassthrough:(BOOL)usePassthrough;
- (void) updateExportProgressBar;
- (CVPixelBufferRef) pixelBufferFromCGImage:(CGImageRef)image size:(NSSize)inSize;

- (CGImageRef) stillCGImageFromVSVideoClip:(VSVideoClip *)videoClip atMasterTime:(CMTime)masterTime showOverlay:(BOOL)showOverlay;
- (NSImage*)currentOverlayImageFromVSVideoClip:(VSVideoClip *)videoClip;
- (CGImageRef)highQualityStillFromVSVideoClip:(VSVideoClip *)videoClip atMasterTime:(CMTime)masterTime;
- (void)saveNSImageAsJpeg:(NSImage*)img destination:(NSString*)destination overwriteWarnings:(BOOL)overwriteWarnings;
- (NSString *)fileNameForExportedFileFromClip:(VSVideoClip *)videoClip withExtension:(NSString *)extension;

@end // VidSyncDocument (Capture)


@interface VidSyncDocument (DataExport)

- (IBAction) copyAllConnectingLinesToClipboard:(id)sender;
- (IBAction) copyAll3DPointsToClipboard:(id)sender;
- (IBAction) exportCSVFile:(id)sender;
- (IBAction) exportXMLFile:(id)sender;
- (NSString *)fileNameForExportedFile:(NSString *)extension;

@end // VidSyncDocument (DataExport)
