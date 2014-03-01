//
//  MyDocument.h
//  VidSync
//
//  Created by Jason Neuswanger on 10/22/09.
//  Copyright University of Alaska Fairbanks 2009 . All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class MagnifiedPreviewView;
@class VideoClipArrayController;
@class TrackedObjectArrayController;
@class TrackedEventArrayController;
@class EventsPointsController;
@class CalibScreenPtArrayController;
@class VSVideoClip;
@class VSTrackedObject;
@class VSVisibleItemArrayController;
@class ObjectSynonymizeArrayController;
@class TypesArrayController;
@class CalibDistortionLineArrayController;
@class VideoControlButton;
@class PlayWhilePressedButton;
@class SyncedPlaybackView;
@class SyncedPlaybackPanel;
@class ObjectsPortraitsArrayController;
@class MainProjectWindow;

@interface VidSyncDocument: NSPersistentDocument {
	
	NSManagedObjectModel *managedObjectModel;
	
	VSProject *__weak project;
    
	NSTimer *__strong playbackTimer;
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
	
	IBOutlet VideoControlButton *__weak playOrPauseButton;
    IBOutlet SyncedPlaybackPanel *__weak syncedPlaybackPanel;
    IBOutlet SyncedPlaybackView *__weak syncedPlaybackView;
    IBOutlet NSSlider *__weak syncedPlaybackScrubber;
    int scrubberMaxTime;
    
	IBOutlet PlayWhilePressedButton *__weak playForwardAtRate1WhilePressedButton,*__weak playBackwardAtRate1WhilePressedButton,*__weak playForwardAtRate2WhilePressedButton,*__weak playBackwardAtRate2WhilePressedButton, *__weak playForwardWhilePressedButton, *__weak playBackwardWhilePressedButton;
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
    
    AVAssetExportSession *__strong exportSession;   // used for exporting videos without overlays -- needs to be an instance variable so I can use it from the progress bar update function
    
    IBOutlet NSImageView *__weak directOpenCVView;
    IBOutlet NSWindow *__weak directOpenCVWindow;
    
    VSTrackedObject *__weak portraitSubject;
    
    IBOutlet ObjectsPortraitsArrayController *__weak objectsPortraitsArrayController;
    IBOutlet NSButton *__weak allPortraitBrowserOpenButton;
    
    BOOL objectsTableSelectionChangeNotificationCascadeEnabled, eventsTableSelectionChangeNotificationCascadeEnabled;
	
}

@property (weak, nonatomic) VSProject *project;
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
@property (readonly, weak) IBOutlet NSWindow *mainWindow;

@property (weak) IBOutlet SyncedPlaybackPanel *syncedPlaybackPanel;
@property (weak) IBOutlet NSSlider *syncedPlaybackScrubber;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playForwardWhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playBackwardWhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playForwardAtRate1WhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playBackwardAtRate1WhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playForwardAtRate2WhilePressedButton;
@property (readonly, weak) IBOutlet PlayWhilePressedButton *playBackwardAtRate2WhilePressedButton;

@property (strong) NSNumberFormatter *decimalFormatter;
@property (weak) VSVideoClip *frontVideoClip;

@property (weak) IBOutlet NSImageView *directOpenCVView;
@property (weak) IBOutlet NSWindow *directOpenCVWindow;
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
- (IBAction) advancedStepForwardAll:(id)sender;
- (IBAction) advancedStepBackwardAll:(id)sender;
- (void) setStopTimeForDuration:(float)duration atRate:(float)rate;
- (void) checkForStopAtCurrentTime;
- (IBAction) setTimeFromScrubber:(id)sender;

- (void) setAllVideoRates:(float)rate;
- (void) movieTimeDidChange:(NSNotification *)notification;
- (void) movieRateDidChange;
- (void) reSync;

@end // VidSyncDocument (SimultaneousPlayback)

@interface VidSyncDocument (Capture)

- (IBAction)captureStills:(id)sender;
- (IBAction)setVideoCaptureTime:(id)sender;
- (IBAction)goToVideoCaptureTime:(id)sender;
- (IBAction)chooseCapturePath:(id)sender;
- (IBAction)openCapturePathInFinder:(id)sender;
- (IBAction)captureVideoClips:(id)sender;

- (void) captureWithOverlayFromVideoClip:(VSVideoClip *)videoClip toFile:(NSString *)destination;
- (void) captureWithoutOverlayFromVideoClip:(VSVideoClip *)videoClip toFile:(NSString *)destination;
- (void) updateExportProgressBar;
- (CVPixelBufferRef) pixelBufferFromCGImage:(CGImageRef)image size:(NSSize)inSize;

- (CGImageRef) stillCGImageFromVSVideoClip:(VSVideoClip *)videoClip atMasterTime:(CMTime)masterTime showOverlay:(BOOL)showOverlay;
- (NSImage*)currentOverlayImageFromVSVideoClip:(VSVideoClip *)videoClip;
- (CGImageRef)highQualityStillFromVSVideoClip:(VSVideoClip *)videoClip atMasterTime:(CMTime)masterTime;
- (void)saveNSImageAsJpeg:(NSImage*)img destination:(NSString*)destination;
- (NSString *)fileNameForExportedFileFromClip:(VSVideoClip *)videoClip withExtension:(NSString *)extension;

@end // VidSyncDocument (Capture)


@interface VidSyncDocument (DataExport)

- (IBAction) copyAllConnectingLinesToClipboard:(id)sender;
- (IBAction) copyAll3DPointsToClipboard:(id)sender;
- (IBAction) exportCSVFile:(id)sender;
- (IBAction) exportXMLFile:(id)sender;
- (NSString *)fileNameForExportedFile:(NSString *)extension;

@end // VidSyncDocument (DataExport)


@interface VidSyncDocument (NSApplicationDelegate) // spot to write out the delegate methods for NSApplication so I don't get lots of "not found" warnings

+ (void)initialize;
+ (NSMutableDictionary *) userDefaultsInitialValues;
+ (void) setUserDefaultsInitialValues;

- (NSError*) application:(NSApplication*)application willPresentError:(NSError*)error;

@end
