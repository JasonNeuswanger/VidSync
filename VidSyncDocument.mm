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

#import "opencv2/opencv.hpp"

#import "VidSyncDocument.h"

@implementation VidSyncDocument

@synthesize project;
@synthesize viewState;

@synthesize mainTabView;
@synthesize calibrationSurfaceTabView;
@synthesize calibrationInputTabView;

@synthesize videoClipArrayController;
@synthesize calibScreenPtFrontArrayController;
@synthesize calibScreenPtBackArrayController;
@synthesize trackedObjectsController;
@synthesize trackedEventsController;
@synthesize trackedObjectTypesController;
@synthesize trackedEventTypesController;
@synthesize eventsPointsController;
@synthesize annotationsController;
@synthesize distortionPointsController;
@synthesize distortionLinesController;	

@synthesize syncedPlaybackWindowController;
@synthesize syncedPlaybackScrubber;
@synthesize playForwardWhilePressedButton;
@synthesize playBackwardWhilePressedButton;
@synthesize playForwardAtRate1WhilePressedButton;
@synthesize playBackwardAtRate1WhilePressedButton;
@synthesize playForwardAtRate2WhilePressedButton;
@synthesize playBackwardAtRate2WhilePressedButton;

@synthesize playForwardAtRate1Button;
@synthesize playBackwardAtRate1Button;
@synthesize playForwardAtRate2Button;
@synthesize playBackwardAtRate2Button;

@synthesize decimalFormatter;

@synthesize mainWindow;
@synthesize frontVideoClip;
@synthesize syncedPlaybackPanel;

@synthesize magnifiedCalibrationPreview;
@synthesize magnifiedMeasurementPreview;
@synthesize magnifiedDistortionPreview;

@synthesize objectsPortraitsArrayController;

@synthesize bookmarkIsSet1;
@synthesize bookmarkIsSet2;

@synthesize objectsTableSelectionChangeNotificationCascadeEnabled;
@synthesize eventsTableSelectionChangeNotificationCascadeEnabled;

static void *AVSPPlayerCurrentTimeContext = &AVSPPlayerCurrentTimeContext;

#pragma mark
#pragma mark Initialization

- (id)init 
{
	self = [super init];
	if (self != nil) {
		// Created here, in the initializer both initWithType: and initWithContentsOfURL: funnel through,
		// because the main window's nib binds through it and is loaded later, in makeWindowControllers.
		viewState = [VSDocumentViewState new];

		shutterClick = [[NSSound alloc] initWithContentsOfFile:[[NSBundle mainBundle] pathForSoundResource:@"CameraClick"] byReference:YES];
		
		stopTime = kCMTimeIndefinite;
		bookmarkIsSet1 = NO;
		bookmarkIsSet2 = NO;
		objectsTableSelectionChangeNotificationCascadeEnabled = YES;
		eventsTableSelectionChangeNotificationCascadeEnabled = YES;
		
		decimalFormatter = [[NSNumberFormatter alloc] init];
		[decimalFormatter setFormatterBehavior:NSNumberFormatterBehavior10_4];
		[decimalFormatter setNumberStyle:NSNumberFormatterDecimalStyle];				// Prevents occasional numbers from being spit out in scientific notation, which screws up importers (Mathematica and others)
		[decimalFormatter setGroupingSeparator:@""];
		[decimalFormatter setMinimumFractionDigits:15];
		activeExportSessions = [NSMutableSet new];
	}
	return self;
}

- (void)makeWindowControllers
{
	NSWindowController *mainWindowController = [[NSWindowController alloc] initWithWindowNibName:@"VidSyncProject" owner:self];
	[mainWindowController setShouldCloseDocument:YES];
	[mainWindowController setShouldCascadeWindows:NO];
	[self addWindowController:mainWindowController];
	
	
	NSArray *playbackWindowTopLevelObjects;
	[[NSBundle mainBundle] loadNibNamed:@"SyncedPlaybackWindow" owner:self topLevelObjects:&playbackWindowTopLevelObjects];
	SyncedPlaybackPanel *loadingSyncedPlaybackPanel;
	for (id obj in playbackWindowTopLevelObjects) if ([obj isKindOfClass:[SyncedPlaybackPanel class]]) loadingSyncedPlaybackPanel = (SyncedPlaybackPanel *) obj;
	syncedPlaybackWindowController = [[NSWindowController alloc] initWithWindow:loadingSyncedPlaybackPanel];
	[self addWindowController:syncedPlaybackWindowController];
	
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) {
		if (clip.isMasterClipOf != nil) {
			// Fixes a weird glitch that appeared in the 2021 updates in which master clips were coming back with nil rather than zero syncOffsets,
			// leading to various errors down the line when treating clips the same including referencing their syncOffset.
			clip.syncOffset = [UtilityFunctions CMStringFromTime:CMTimeMake(0,[clip.timeScale intValue])];
		}
		VideoWindowController __strong *vwc = [[VideoWindowController alloc] initWithVideoClip:clip inManagedObjectContext:[self managedObjectContext]];
		[self observeWindowControllerVideoRate:vwc];
		if (vwc != nil) [self addWindowController:vwc];
	}
	
	// Explicitly bring the main window to front. Video windows use orderFrontRegardless and always
	// appear; without this call the main window can be skipped during crash-recovery restoration.
	[[mainWindowController window] makeKeyAndOrderFront:self];

	// The saved layout can't be judged until the videos have loaded, because their sizes depend on the
	// movie dimensions. Arm the check here; videoWindowControllerDidLoadVideo: fires it off when the
	// last video window is ready.
	awaitingInitialWindowLayout = ([[self videoWindowControllers] count] > 0);

	[self addObserver:self forKeyPath:@"portraitSubject" options:NSKeyValueObservingOptionNew context:NULL];

	[[NSNotificationCenter defaultCenter] addObserver:self
									 selector:@selector(movieTimeDidChange:)
										name:AVPlayerItemTimeJumpedNotification
									   object:project.masterClip.windowController.playerView.player.currentItem];
	
	[[NSNotificationCenter defaultCenter] addObserver:self
									 selector:@selector(anyTableViewSelectionDidChange:)
										name:NSTableViewSelectionDidChangeNotification object:nil];
	
	[[NSNotificationCenter defaultCenter] addObserver:self
									 selector:@selector(anyTableViewSelectionIsChanging:)
										name:NSTableViewSelectionIsChangingNotification object:nil];
	
	// The lines below sets up the timer used for frame-by-frame updates of the overlay layer; it's the main playback loop for the calibration, measurement, and annotation points.
	playbackTimer = [NSTimer timerWithTimeInterval:0.03 target:self selector:@selector(playbackLoopActions) userInfo:nil repeats:YES];
	[[NSRunLoop currentRunLoop] addTimer:playbackTimer forMode:NSRunLoopCommonModes];
	[[NSRunLoop currentRunLoop] addTimer:playbackTimer forMode:NSEventTrackingRunLoopMode]; // This keeps the timer running and overlays updating during play-while-pressed and other user interface actions
	
}

- (void) observeWindowControllerVideoRate:(VideoWindowController *)vwc  // called from above and also VideoClipArrayController when adding new clips
{
	[vwc addObserver:self forKeyPath:@"playerView.player.rate" options:NSKeyValueObservingOptionNew context:NULL];
}

#pragma mark
#pragma mark Window layout

- (NSArray *) videoWindowControllers
{
	NSMutableArray *controllers = [NSMutableArray new];
	for (NSWindowController *wc in [self windowControllers]) {
		if ([wc isKindOfClass:[VideoWindowController class]]) [controllers addObject:wc];
	}
	return controllers;
}

- (void) videoWindowControllerDidLoadVideo:(VideoWindowController *)vwc  // called by VideoWindowController at the end of setUpPlaybackOfAsset:
{
	if (!awaitingInitialWindowLayout) return;	// clips loaded later in the session shouldn't rearrange the windows
	for (VideoWindowController *controller in [self videoWindowControllers]) {
		if (![controller hasLoadedVideo]) return;
	}
	awaitingInitialWindowLayout = NO;
	[self applyTiledWindowLayoutIfSavedLayoutUnusable];
}

- (IBAction) tileWindows:(id)sender	// Window > Tile Windows
{
	[self applyTiledWindowLayout];
}

+ (BOOL) frame:(NSRect)frame fitsOnSomeScreen:(NSArray<NSScreen *> *)screens
{
	// A couple of points of slop, because a window nudged flush against a screen edge often ends up
	// a fraction of a point outside the visible frame.
	for (NSScreen *screen in screens) {
		if (NSContainsRect(NSInsetRect([screen visibleFrame], -2.0f, -2.0f), frame)) return YES;
	}
	return NO;
}

- (BOOL) anyWindowSignificantlyCoversTheControlWindows
{
	// A restored layout that buries the controls or the data window under something else is worth
	// replacing even when every window is technically on-screen, which is how a layout from a larger
	// display usually comes back: the frames get slid into view rather than left hanging off the edge.
	const CGFloat maximumCoveredFraction = 0.05f;
	NSMutableArray *coveringWindows = [NSMutableArray new];
	for (VideoWindowController *vwc in [self videoWindowControllers]) {
		if ([vwc window] != nil) [coveringWindows addObject:[vwc window]];
	}
	// The main window counts as a covering window too, because AppKit slides it up under the borderless
	// playback panel, which it doesn't know is there, whenever the saved frame reaches past the top of
	// the screen. The panel doesn't need to be in this list: the intersection is the same either way,
	// and measuring it against the panel's area is the more sensitive of the two tests.
	if (mainWindow != nil) [coveringWindows addObject:mainWindow];
	NSMutableArray *coveredWindows = [NSMutableArray new];
	if (mainWindow != nil) [coveredWindows addObject:mainWindow];
	if (syncedPlaybackPanel != nil) [coveredWindows addObject:syncedPlaybackPanel];
	for (NSWindow *coveringWindow in coveringWindows) {
		if (![coveringWindow isVisible]) continue;
		for (NSWindow *coveredWindow in coveredWindows) {
			if (coveredWindow == coveringWindow || ![coveredWindow isVisible]) continue;
			NSRect coveredFrame = [coveredWindow frame];
			CGFloat coveredArea = coveredFrame.size.width * coveredFrame.size.height;
			if (coveredArea <= 0.0f) continue;
			NSRect overlap = NSIntersectionRect([coveringWindow frame],coveredFrame);
			if ((overlap.size.width * overlap.size.height) / coveredArea > maximumCoveredFraction) return YES;
		}
	}
	return NO;
}

- (BOOL) savedWindowLayoutIsUsable
{
	// Video window frames live in the project file, so they travel between computers; a project last
	// worked on a big desktop display comes back with frames that run off the edge of a laptop screen.
	// The main window's and playback panel's frames are autosaved per-computer instead, so they may
	// simply be absent. Either way, the fix is the same: fall back to the tiled layout.
	for (VideoWindowController *vwc in [self videoWindowControllers]) {
		if (vwc.videoClip.windowFrame == nil) return NO;
	}
	NSArray<NSScreen *> *screens = [NSScreen screens];
	NSMutableArray *windowsToCheck = [NSMutableArray new];
	if (mainWindow != nil) [windowsToCheck addObject:mainWindow];
	if (syncedPlaybackPanel != nil) [windowsToCheck addObject:syncedPlaybackPanel];
	for (VideoWindowController *vwc in [self videoWindowControllers]) {
		if ([vwc window] != nil) [windowsToCheck addObject:[vwc window]];
	}
	for (NSWindow *window in windowsToCheck) {
		if (![VidSyncDocument frame:[window frame] fitsOnSomeScreen:screens]) return NO;
	}
	if ([self anyWindowSignificantlyCoversTheControlWindows]) return NO;
	return YES;
}

- (void) applyTiledWindowLayoutIfSavedLayoutUnusable
{
	if ([self savedWindowLayoutIsUsable]) return;
	BOOL documentWasEdited = [self isDocumentEdited];
	[self applyTiledWindowLayout];
	// Moving the video windows writes their new frames into the project, which would otherwise leave a
	// document dirty the moment it opened. The layout gets saved along with the user's next real edit.
	// Tiling asked for from the menu is left as an edit, because there the arrangement is what the user wants.
	if (!documentWasEdited) {
		dispatch_async(dispatch_get_main_queue(), ^{
			[self updateChangeCount:NSChangeCleared];
		});
	}
}

- (void) applyTiledWindowLayout
{
	// Playback controls maximized along the top of the screen, the main window tucked into the corner
	// underneath them on the left, and the video windows cascading from the inside corner formed by
	// those two down to the bottom right corner of the screen.
	if (mainWindow == nil) return;
	NSScreen *screen = [mainWindow screen];
	if (screen == nil) screen = [NSScreen mainScreen];
	if (screen == nil) return;
	NSRect visibleFrame = [screen visibleFrame];

	CGFloat controlsBottom = NSMaxY(visibleFrame);
	if (syncedPlaybackPanel != nil) {
		NSRect panelFrame = [syncedPlaybackPanel frame];
		panelFrame.size.width = visibleFrame.size.width;
		panelFrame.origin.x = NSMinX(visibleFrame);
		panelFrame.origin.y = NSMaxY(visibleFrame) - panelFrame.size.height;
		[syncedPlaybackPanel setFrame:panelFrame display:YES];
		controlsBottom = NSMinY(panelFrame);
	}

	NSRect mainFrame = [mainWindow frame];
	mainFrame.size.width = MIN(mainFrame.size.width, visibleFrame.size.width);
	mainFrame.size.height = MIN(mainFrame.size.height, controlsBottom - NSMinY(visibleFrame));
	mainFrame.size.height = MAX(mainFrame.size.height, [mainWindow minSize].height);
	mainFrame.origin.x = NSMinX(visibleFrame);
	mainFrame.origin.y = controlsBottom - mainFrame.size.height;
	[mainWindow setFrame:mainFrame display:YES];

	NSArray *controllers = [[self videoWindowControllers] sortedArrayUsingComparator:^NSComparisonResult(VideoWindowController *first, VideoWindowController *second) {
		NSString *firstName = (first.videoClip.clipName != nil) ? first.videoClip.clipName : @"";
		NSString *secondName = (second.videoClip.clipName != nil) ? second.videoClip.clipName : @"";
		return [firstName localizedCaseInsensitiveCompare:secondName];
	}];
	if ([controllers count] == 0) return;

	// The videos get everything to the right of the main window and below the controls, all the way into
	// the bottom right corner of the screen.
	NSRect videoRegion = NSMakeRect(NSMaxX(mainFrame),
									NSMinY(visibleFrame),
									NSMaxX(visibleFrame) - NSMaxX(mainFrame),
									controlsBottom - NSMinY(visibleFrame));
	if (videoRegion.size.width <= 0.0f || videoRegion.size.height <= 0.0f) return;

	// No video window may exceed 75% of the region in either dimension, which is what leaves room for
	// the cascade: with two clips the second one starts a quarter of the way across and down. A window
	// can still come back larger than this if the video window's own minimum size demands it.
	NSSize maxVideoWindowSize = NSMakeSize(0.75f*videoRegion.size.width, 0.75f*videoRegion.size.height);
	NSMutableArray *windowSizes = [NSMutableArray new];
	for (VideoWindowController *vwc in controllers) {
		[windowSizes addObject:[NSValue valueWithSize:[vwc windowFrameSizeFittingWithinSize:maxVideoWindowSize]]];
	}

	// The intervals are set by the last window, whose bottom right corner has to land exactly on the
	// bottom right corner of the region.
	NSSize lastWindowSize = [[windowSizes lastObject] sizeValue];
	NSInteger intervalCount = (NSInteger)[controllers count] - 1;
	CGFloat xInterval = 0.0f, yInterval = 0.0f;
	if (intervalCount > 0) {
		xInterval = MAX(0.0f, (videoRegion.size.width - lastWindowSize.width) / (CGFloat)intervalCount);
		yInterval = MAX(0.0f, (videoRegion.size.height - lastWindowSize.height) / (CGFloat)intervalCount);
	}

	for (NSUInteger i = 0; i < [controllers count]; i++) {
		VideoWindowController *vwc = [controllers objectAtIndex:i];
		NSSize windowSize = [[windowSizes objectAtIndex:i] sizeValue];
		CGFloat windowTop = NSMaxY(videoRegion) - (CGFloat)i*yInterval;
		NSRect windowFrame = NSMakeRect(NSMinX(videoRegion) + (CGFloat)i*xInterval,
										windowTop - windowSize.height,
										windowSize.width,
										windowSize.height);
		[[vwc window] setFrame:windowFrame display:YES];
		[vwc fitVideoOverlay];	// setFrame: skips the delegate notification when nothing actually changed
	}
}

- (void) windowControllerDidLoadNib:(NSWindowController *)windowController
{
	if ([[windowController windowNibName] isEqualToString:@"VidSyncProject"]) { // only do after the main window loads its nib (this is when videoClipArrayController is non-null, for example)
		NSString *fileName = [[self fileURL] absoluteString];
		if (fileName != nil) [[windowController window] setFrameAutosaveName:fileName];
		[[NSNotificationCenter defaultCenter] addObserver:videoClipArrayController
										 selector:@selector(keyWindowDidChange:)
											name:NSWindowDidBecomeKeyNotification object:nil];
		NSSortDescriptor *indexDescriptor = [[NSSortDescriptor alloc] initWithKey:@"index" ascending:YES];
		NSSortDescriptor *nameDescriptor = [[NSSortDescriptor alloc] initWithKey:@"name" ascending:YES];
		NSSortDescriptor *timecodeDescriptor = [[NSSortDescriptor alloc] initWithKey:@"timecode" ascending:YES];
		[calibScreenPtFrontArrayController setSortDescriptors:[NSArray arrayWithObjects: indexDescriptor, nil]];
		[calibScreenPtBackArrayController setSortDescriptors:[NSArray arrayWithObjects: indexDescriptor, nil]];
		[trackedEventTypesController setSortDescriptors:[NSArray arrayWithObject:nameDescriptor]];
		[trackedObjectTypesController setSortDescriptors:[NSArray arrayWithObject:nameDescriptor]];
		[distortionLinesController setSortDescriptors:[NSArray arrayWithObject:timecodeDescriptor]];
		[distortionPointsController setSortDescriptors:[NSArray arrayWithObject:indexDescriptor]];
		// Wire ourselves as the action delegate for portrait browsers so double-click and
		// delete events reach the document. The array controllers are the NSCollectionView
		// dataSource/delegate; they forward those action events on to us.
		objectsPortraitsArrayController.portraitActionDelegate = self;
		allPortraitsArrayController.portraitActionDelegate = self;
		NSMutableAttributedString *portraitWindowOpenButtonTitle =[[NSMutableAttributedString alloc] initWithAttributedString:[[NSMutableAttributedString alloc] initWithString:@"\uf030"]];
		[portraitWindowOpenButtonTitle addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:12.0f] range:NSMakeRange(0,1)];
		[allPortraitBrowserOpenButton setAttributedTitle:portraitWindowOpenButtonTitle];
		[textViewForQuadratNodesFront setUsesAdaptiveColorMappingForDarkAppearance:YES];
		[textViewForQuadratNodesBack setUsesAdaptiveColorMappingForDarkAppearance:YES];
		// Only now start writing tab and filter changes back as the remembered values, so that anything
		// the bindings pushed while they were being established can't overwrite the user's last choice.
		viewState.persistsChangesToUserDefaults = YES;
	}
}

- (void) syncedPlaybackPanelAwokeFromNib    // called by SyncedPlaybackPanel when it wakes up
{
	scrubberMaxTime = 1000000000;
	[syncedPlaybackScrubber setMaxValue:(double) scrubberMaxTime];
	[self addObserver:syncedPlaybackView forKeyPath:@"bookmarkIsSet1" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:syncedPlaybackView forKeyPath:@"bookmarkIsSet2" options:NSKeyValueObservingOptionNew context:NULL];
	playForwardWhilePressedButton.direction = 1.0;
	playForwardWhilePressedButton.advancedRateToUse = 0;
	playBackwardWhilePressedButton.direction = -1.0;
	playBackwardWhilePressedButton.advancedRateToUse = 0;
	playForwardAtRate1WhilePressedButton.direction = 1.0;
	playForwardAtRate1WhilePressedButton.advancedRateToUse = 1;
	playBackwardAtRate1WhilePressedButton.direction = -1.0;
	playBackwardAtRate1WhilePressedButton.advancedRateToUse = 1;
	playForwardAtRate2WhilePressedButton.direction = 1.0;
	playForwardAtRate2WhilePressedButton.advancedRateToUse = 2;
	playBackwardAtRate2WhilePressedButton.direction = -1.0;
	playBackwardAtRate2WhilePressedButton.advancedRateToUse = 2;
}

- (id)initWithType:(NSString *)type error:(NSError **)error {	// This method is called only when a new document is created.
	self = [super initWithType:type error:error];
	if (self != nil) {
		NSManagedObjectContext *managedObjectContext = [self managedObjectContext];
		[[managedObjectContext undoManager] disableUndoRegistration];
		self.project = [NSEntityDescription insertNewObjectForEntityForName:@"VSProject" inManagedObjectContext:managedObjectContext];
		self.project.document = self;
		self.project.dateCreated = [UtilityFunctions stringFromDateTime:[NSDate dateWithTimeIntervalSinceNow:0.0] format:@"yyy-MM-dd HH:mm:ss Z"];
		self.project.capturePathForMovies = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/VidSync Exports/Movies/"];
		self.project.capturePathForStills = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/VidSync Exports/Stills/"];
		self.project.exportPathForData = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/VidSync Exports/Data/"];
		[managedObjectContext processPendingChanges];
		[[managedObjectContext undoManager] enableUndoRegistration];
	}
	return self;
}

- (NSManagedObjectModel *)managedObjectModel {	// required when using migrations, to override the default behavior in order to tell it to only load one (the most current) data model
	if (managedObjectModel != nil) return managedObjectModel;
	NSString *path = [[NSBundle mainBundle] pathForResource:@"VidSyncProject" ofType:@"momd"];
	NSURL *momURL = [NSURL fileURLWithPath:path];
	managedObjectModel = [[NSManagedObjectModel alloc] initWithContentsOfURL:momURL];
	return managedObjectModel;
}

- (id)initWithContentsOfURL:(NSURL *)absoluteURL ofType:(NSString *)typeName error:(NSError **)outError		// This method is called only when an existing document is loaded.
{
	// I think this is where custom migrations are supposed to go, if/when I have to make any.
	NSString *savedPath = [[absoluteURL path] stringByDeletingLastPathComponent];
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:savedPath forKey:@"mainFileSaveDirectory"];
	return [super initWithContentsOfURL:absoluteURL ofType:typeName error:outError];
}

// This overriden NSPersistentDocument method is called whenever an existing document is loaded, but not when a new one is created.
// However, the settings here apply to new documents (particularly the journal mode) too, so it must be getting used somehow.

- (BOOL)configurePersistentStoreCoordinatorForURL:(NSURL *)url ofType:(NSString *)fileType modelConfiguration:(NSString *)configuration storeOptions:(NSDictionary *)storeOptions error:(NSError **)error
{    
	NSMutableDictionary *newOptions;
	if (storeOptions) {
		newOptions = [storeOptions mutableCopy];
	} else {
		newOptions = [[NSMutableDictionary alloc] init];
	}
	[newOptions setObject:[NSNumber numberWithBool:YES] forKey:NSMigratePersistentStoresAutomaticallyOption];
	[newOptions setObject:[NSNumber numberWithBool:YES] forKey:NSInferMappingModelAutomaticallyOption];
	[newOptions setObject:@{@"journal_mode":@"DELETE"} forKey:NSSQLitePragmasOption];   // Uses "rollback" journaling mode instead default WAL, so each VidSync document is saved in 1 file, not 3
	BOOL result = [super configurePersistentStoreCoordinatorForURL:url ofType:fileType modelConfiguration:configuration storeOptions:newOptions error:error];
	return result;
}

// This method fetches the current document instance's video pair from the managed object contest when it's nil, 
// such as after a saved document is loaded.

- (VSProject *)project
{
	if (project != nil) {
		return project;
	} else {
		NSManagedObjectContext *moc = [self managedObjectContext];
		NSFetchRequest *fetchRequest = [[NSFetchRequest alloc] init];
		NSError *fetchError = nil;
		NSArray *fetchResults;
		NSEntityDescription *entity = [NSEntityDescription entityForName:@"VSProject" inManagedObjectContext:moc];
		[fetchRequest setEntity:entity];
		fetchResults = [moc executeFetchRequest:fetchRequest error:&fetchError];
		if ((fetchResults != nil) && ([fetchResults count] == 1) && (fetchError == nil)) {
			project = [fetchResults objectAtIndex:0];
			project.document = self;
			return project;
		} else {
			if (fetchError != nil) {
				[self presentError:fetchError];
			} else {
				NSLog(@"Project wasn't correctly fetched from the managed object context.");
			}
			return nil;
		}
	}
}

#pragma mark
#pragma mark Event observing

- (void) anyTableViewSelectionIsChanging:(NSNotification *)notification
{
	// This would control what to do when a table view's selection is about to change but hasn't changed yet.
	// I used to have some things here, but removed them when they were no longer needed.
}

- (void) anyTableViewSelectionDidChange:(NSNotification *)notification	// Controls what to do once a table view's selection HAS changed
{
	// NSLog(@"Processing a change to selection from tableView %@",[[notification object] identifier]);
	if (self.project.masterClip != nil) {
		
		if ([[notification object] isEqualTo:eventsPointsTable]) {
			[[self managedObjectContext] processPendingChanges];
			if ([[eventsPointsController selectedObjects] count] > 0) {
				VSPoint *selectedPoint = [[eventsPointsController selectedObjects] objectAtIndex:0];
				VSEventScreenPoint *selectedScreenPoint = [selectedPoint screenPointForVideoClip:self.frontVideoClip];
				if ([selectedScreenPoint.screenX floatValue] > 0.0 || [selectedScreenPoint.screenY floatValue] > 0.0) {
					NSPoint newPoint = NSMakePoint([selectedScreenPoint.screenX floatValue],[selectedScreenPoint.screenY floatValue]);
					[self refreshOverlaysOfAllClips:nil];   // Refresh overlays before updating preview image, for speed
					[self updatePreviewImageWithPlayerLayer:self.frontVideoClip.windowController.playerLayer atPoint:newPoint];
				}
				[eventsPointsController scrollTableToSelectedObject];
			} else {
				[self refreshOverlaysOfAllClips:nil];   // Refresh overlays if we deselected a clip, too
			}
			
		} else if ([[notification object] isEqualTo:distortionLinesController.mainTableView]) {
			
			[distortionLinesController scrollTableToSelectedObject];
			if ([[distortionLinesController arrangedObjects] count] > 0) {
				[distortionPointsController setSelectionIndex:0];
				[self.frontVideoClip.windowController refreshOverlay];
				if ([[distortionPointsController arrangedObjects] count] > 0) {
					VSDistortionPoint *firstPoint = [[distortionPointsController arrangedObjects] objectAtIndex:0];
					[self updatePreviewImageWithPlayerLayer:firstPoint.distortionLine.calibration.videoClip.windowController.playerLayer atPoint:NSMakePoint([firstPoint.screenX floatValue],[firstPoint.screenY floatValue])];
				}
			}
			
		} else if ([[notification object] isEqualTo:[distortionPointsController mainTableView]]) {
			
			[distortionPointsController scrollTableToSelectedObject];
			
			if ([[distortionPointsController selectedObjects] count] > 0) {
				VSDistortionPoint *selectedPoint = [[distortionPointsController selectedObjects] objectAtIndex:0];
				[self updatePreviewImageWithPlayerLayer:selectedPoint.distortionLine.calibration.videoClip.windowController.playerLayer atPoint:NSMakePoint([selectedPoint.screenX floatValue],[selectedPoint.screenY floatValue])];
			}
			
			[self.frontVideoClip.windowController refreshOverlay];
			
		} else if ([[notification object] isEqualTo:[videoClipArrayController mainTableView]]) {
			
			if ([[videoClipArrayController selectedObjects] count] > 0) {
				VSVideoClip *selectedClip = [[videoClipArrayController selectedObjects] objectAtIndex:0];
				[[selectedClip.windowController window] orderFront:self];
			}
			
		} else if ([[notification object] isEqualTo:calibScreenPtFrontArrayController.mainTableView]) {
			
			if ([[calibScreenPtFrontArrayController selectedObjects] count] > 0) {
				VSCalibrationPoint *selectedPoint = [[calibScreenPtFrontArrayController selectedObjects] objectAtIndex:0];
				if ([selectedPoint.screenX floatValue] > 0.0 || [selectedPoint.screenY floatValue] > 0.0) {
					[self updatePreviewImageWithPlayerLayer:selectedPoint.calibration.videoClip.windowController.playerLayer atPoint:NSMakePoint([selectedPoint.screenX floatValue],[selectedPoint.screenY floatValue])];
				}
				[calibScreenPtFrontArrayController scrollTableToSelectedObject];
				[selectedPoint.calibration.videoClip.windowController refreshOverlay];
			}
			
		} else if ([[notification object] isEqualTo:calibScreenPtBackArrayController.mainTableView]) {
			
			if ([[calibScreenPtBackArrayController selectedObjects] count] > 0) {
				VSCalibrationPoint *selectedPoint = [[calibScreenPtBackArrayController selectedObjects] objectAtIndex:0];
				if ([selectedPoint.screenX floatValue] > 0.0 || [selectedPoint.screenY floatValue] > 0.0) {
					[self updatePreviewImageWithPlayerLayer:selectedPoint.calibration.videoClip.windowController.playerLayer atPoint:NSMakePoint([selectedPoint.screenX floatValue],[selectedPoint.screenY floatValue])];
				}
				[calibScreenPtBackArrayController scrollTableToSelectedObject];
				[selectedPoint.calibration.videoClip.windowController refreshOverlay];
			}
			
		} else if ([[notification object] isEqualTo:annotationsController.mainTableView]) {
			
			if ([[annotationsController selectedObjects] count] > 0) {
				VSAnnotation *selectedAnnotation = [[annotationsController selectedObjects] objectAtIndex:0];
				[annotationsController scrollTableToSelectedObject];
				[selectedAnnotation.videoClip.windowController refreshOverlay];
			} else {	// if no annotation is selected, find any annotation from the controller to figure out the right clip, and refresh its overlay to show the deselection
				if ([[annotationsController arrangedObjects] count] > 0) {
					VSAnnotation *anyAnnotation = [[annotationsController arrangedObjects] objectAtIndex:0];
					[anyAnnotation.videoClip.windowController refreshOverlay];
				}
			}
			
		} else if ([[notification object] isEqualTo:trackedObjectsController.mainTableView]) {
			
			if ([[trackedObjectsController selectedObjects] count] > 0) {
				[trackedObjectsController scrollTableToSelectedObject];
				if (objectsTableSelectionChangeNotificationCascadeEnabled) {
					[trackedEventsController setSelectionIndex:0];	// Select the object's first event
					[eventsPointsController setSelectionIndex:0];	// and that event's first point
				} else {
					objectsTableSelectionChangeNotificationCascadeEnabled = YES;
				}
				// the problem is if I disable the notification, they won't scroll and stuff... I just need to tell them not to trigger notifications on their own
				 
				[objectSynonymizeController rearrangeObjects];
				[objectsPortraitsArrayController refreshCollectionView];
				
			}
			
		} else if ([[notification object] isEqualTo:trackedEventsController.mainTableView]) {
			if ([[trackedEventsController selectedObjects] count] > 0) {
				[trackedEventsController scrollTableToSelectedObject];
				if (eventsTableSelectionChangeNotificationCascadeEnabled) {
					[eventsPointsController setSelectionIndex:0];	// Select the event's first point.
				} else {
					eventsTableSelectionChangeNotificationCascadeEnabled = YES;
				}
			}
		}
	}
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
	if ([keyPath isEqualToString:@"playerView.player.rate"]) {
		// trigger player rate change handler
		if (self.project.masterClip.windowController != nil && [object isEqualTo:self.project.masterClip.windowController]) {
			[self movieRateDidChange];
		}
	} else if ([keyPath isEqualToString:@"portraitSubject"]) {
		if (portraitSubject == nil) {
			[[NSCursor arrowCursor] set];
		} else {
			[[NSCursor crosshairCursor] set];
		}
	}
}


#pragma mark
#pragma mark NSTabView delegate (for "observing" tab changes)

- (void) tabView:(NSTabView *)tabView didSelectTabViewItem:(NSTabViewItem *)tabViewItem
{
	[self refreshOverlaysOfAllClips:self];
}

#pragma mark
#pragma mark Saving the main file

- (void) saveToURL:(NSURL *)url ofType:(NSString *)typeName forSaveOperation:(NSSaveOperationType)saveOperation completionHandler:(void (^)(NSError *))completionHandler
{
	self.project.dateLastSaved = [UtilityFunctions stringFromDateTime:[NSDate dateWithTimeIntervalSinceNow:0.0] format:@"yyy-MM-dd HH:mm:ss Z"];	// current date as a string
	[[self managedObjectContext] processPendingChanges];
	NSString *savedPath = [[url path] stringByDeletingLastPathComponent];
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:savedPath forKey:@"mainFileSaveDirectory"];
	if (self.project.capturePathForMovies == nil || [self.project.capturePathForMovies isEqualToString:@""] || [self.project.capturePathForMovies isEqualToString:[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/VidSync Exports/Movies/"]]) self.project.capturePathForMovies = savedPath;
	if (self.project.capturePathForStills == nil || [self.project.capturePathForStills isEqualToString:@""] || [self.project.capturePathForStills isEqualToString:[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/VidSync Exports/Stills/"]]) self.project.capturePathForStills = savedPath;
	if (self.project.exportPathForData == nil || [self.project.exportPathForData isEqualToString:@""] || [self.project.exportPathForData isEqualToString:[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/VidSync Exports/Data/"]]) self.project.exportPathForData = savedPath;
	[super saveToURL:url ofType:typeName forSaveOperation:saveOperation completionHandler:completionHandler];
}

- (BOOL) prepareSavePanel:(NSSavePanel *)savePanel
{
	// Set the default directory to the previous directory in which a .vsc file was saved
	NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"mainFileSaveDirectory"];
	BOOL directoryExists;
	if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) [savePanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
	// Set the default filename to the project name, if it exists
	if (![self.project.name isEqualToString:@""]) [savePanel setNameFieldStringValue:self.project.name];
	return YES;
}

#pragma mark
#pragma mark Object/event type files

- (IBAction) saveObjectAndEventTypesToFile:(id)sender
{
	NSMutableArray *objectTypesArray = [[NSMutableArray alloc] init];
	NSMutableArray *eventTypesArray = [[NSMutableArray alloc] init];
	for (VSTrackedObjectType *objectType in self.project.trackedObjectTypes) {
		[objectTypesArray addObject:[objectType contentsAsWriteableDictionary]];
	}
	for (VSTrackedEventType *eventType in self.project.trackedEventTypes) {
		[eventTypesArray addObject:[eventType contentsAsWriteableDictionary]];
	}
	NSArray *saveArray = [NSArray arrayWithObjects:objectTypesArray,eventTypesArray,nil];
	NSSavePanel *savePanel = [NSSavePanel savePanel];
	[savePanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncTypes",nil]];
	if ([savePanel runModal]) {
		[saveArray writeToFile:[[savePanel URL] path] atomically:NO];
	}
	
}

- (IBAction) loadObjectAndEventTypesFromFile:(id)sender
{
	NSString *filePath;
	NSOpenPanel *openPanel = [NSOpenPanel openPanel];
	[openPanel setCanChooseFiles:YES];
	[openPanel setAllowedFileTypes:[NSArray arrayWithObjects:@"VidSyncTypes",nil]];
	[openPanel setCanChooseDirectories:NO];
	[openPanel setAllowsMultipleSelection:NO];
	[openPanel setMessage:@"Loading types from a file will add them to the existing types list, not replace it. If loaded types have the same name as existing types, their attributes (color, etc.) will be updated from the new file."];
	if ([openPanel runModal]) {
		filePath = [[[openPanel URLs] objectAtIndex:0] path];
		[self loadObjectAndEventTypesFromFileAtPath:filePath];
	}
}

- (IBAction) loadObjectAndEventTypesExample:(id)sender
{
	NSString *filePath = [[NSBundle mainBundle] pathForResource:@"Example Types" ofType:@"VidSyncTypes"];
	[self loadObjectAndEventTypesFromFileAtPath:filePath];
}

- (void) loadObjectAndEventTypesFromFileAtPath:(NSString *)filePath
{
	NSArray *allTypes = [[NSArray alloc] initWithContentsOfFile:filePath];
	if (![allTypes isKindOfClass:[NSArray class]] || [allTypes count] < 2) {
		[UtilityFunctions InformUser:@"The types file could not be read or is from an unsupported version." withTitle:@"Invalid File"];
		return;
	}
	NSArray *objectTypesArray = [allTypes objectAtIndex:0];
	NSArray *eventTypesArray = [allTypes objectAtIndex:1];
	for (NSDictionary *objectTypeDictionary in objectTypesArray) {
		[VSTrackedObjectType insertNewTypeFromLoadedDictionary:objectTypeDictionary inProject:self.project inManagedObjectContext:[self managedObjectContext]];
	}
	for (NSDictionary *eventTypeDictionary in eventTypesArray) {
		[VSTrackedEventType insertNewTypeFromLoadedDictionary:eventTypeDictionary inProject:self.project inManagedObjectContext:[self managedObjectContext]];
	}
}

#pragma mark
#pragma mark Magnified preview control

- (void) updatePreviewImageWithPlayerLayer:(AVPlayerLayer *)playerLayer atPoint:(NSPoint)point;
{
	if (playerLayer != nil) {
		if ([[[mainTabView selectedTabViewItem] label] isEqualToString:@"Measurement"]) {
			[magnifiedMeasurementPreview setPlayerLayer:playerLayer];
			[magnifiedMeasurementPreview setCenterPoint:point];
		} else if ([[[mainTabView selectedTabViewItem] label] isEqualToString:@"Calibration"]) {
			if ([[[calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"3D Calibration Frame Input"]) {
				[magnifiedCalibrationPreview setPlayerLayer:playerLayer];
				[magnifiedCalibrationPreview setCenterPoint:point];
			} else if ([[[calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"Lens Distortion"]) {
				[magnifiedDistortionPreview setPlayerLayer:playerLayer];
				[magnifiedDistortionPreview setCenterPoint:point];
			}
		}
	}
}

- (IBAction) resetPreviewMagnification:(id)sender
{
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithFloat:1.0] forKey:@"previewMagnification"];
}

- (IBAction) setPreviewFiltersToDefaults:(id)sender
{
	[MagnifiedPreviewView setFiltersToDefaults];
}

#pragma mark
#pragma mark Calibration time

- (IBAction) setCalibrationTime:(id)sender
{
	BOOL doSet = YES;
	if (self.project.calibrationTimecode != nil) doSet = [UtilityFunctions ConfirmAction:@"You already set a calibration time. Are you sure you want to change it?" withTitle:nil];
	if (doSet) self.project.calibrationTimecode = [self currentMasterTimeString];
}

- (IBAction) goToCalibrationTime:(id)sender
{
	if (self.project.calibrationTimecode != nil) [self goToMasterTime:[UtilityFunctions CMTimeFromString:self.project.calibrationTimecode]];
}

#pragma mark
#pragma mark Refresh/recalculate

- (IBAction) refreshOverlaysOfAllClips:(id)sender
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) {
		[clip.windowController refreshOverlay];
	}
	
}

- (IBAction) recalculateAllPoints:(id)sender
{
	NSFetchRequest *fetchRequest = [[NSFetchRequest alloc] init];
	NSError *fetchError = nil;
	NSEntityDescription *allVSPoints = [NSEntityDescription entityForName:@"VSPoint" inManagedObjectContext:[self managedObjectContext]];
	[fetchRequest setEntity:allVSPoints];
	NSArray *fetchResults = [[self managedObjectContext] executeFetchRequest:fetchRequest error:&fetchError];
	if ((fetchResults != nil) && (fetchError == nil) && [fetchResults count] > 0) {
		[pointRecalculateProgressIndicator setDoubleValue:0.0];
		[pointRecalculatePanel makeKeyAndOrderFront:self];
		[pointRecalculateProgressIndicator displayIfNeeded];
		int i = 0;
		for (VSPoint *point in fetchResults) {
			for (VSEventScreenPoint *screenPoint in point.screenPoints) [screenPoint updateCalibrationFrameCoords];
			[point calculate3DCoords];
			[point clearPointToPointDistanceCache];
			i += 1;
			[pointRecalculateProgressIndicator setDoubleValue:(double) i / (double) [fetchResults count]];
			[pointRecalculateProgressIndicator displayIfNeeded];
		}
		[self refreshOverlaysOfAllClips:sender];
		[pointRecalculatePanel performClose:self];
		eventsPointsController.mainTableView.needsDisplay = YES;	// refresh the point table
	}
	if (fetchResults == nil) [UtilityFunctions InformUser:@"There are no measured points yet, so nothing is being recalculated." withTitle:@"No measurements yet"];
	if (fetchError != nil) [self presentError:fetchError];
}

#pragma mark
#pragma mark Portraits of objects

- (void) setPortraitSubject:(VSTrackedObject *)subject
{
	portraitSubject = subject;
}

- (VSTrackedObject *) portraitSubject
{
	return portraitSubject;
}

// PortraitBrowserViewDelegate — double-clicking a portrait navigates to the frame it was captured from
- (void)portraitBrowserView:(NSCollectionView *)browserView didDoubleClickPortrait:(VSTrackedObjectPortrait *)portrait
{
    [self goToMasterTime:[UtilityFunctions CMTimeFromString:portrait.timecode]];
    portrait.sourceVideoClip.windowController.shouldShowPortraitFrame = portrait.frameString;
    [[portrait.sourceVideoClip.windowController window] makeKeyAndOrderFront:self];
}

- (void)portraitBrowserViewDeleteSelectedItems:(NSCollectionView *)browserView
{
    if (![browserView.dataSource isKindOfClass:[PortraitsArrayController class]]) return;
    PortraitsArrayController *controller = (PortraitsArrayController *)browserView.dataSource;
    NSArray<NSIndexPath *> *sorted = [[browserView.selectionIndexPaths allObjects]
        sortedArrayUsingComparator:^(NSIndexPath *a, NSIndexPath *b) {
            return [@(b.item) compare:@(a.item)];
        }];
    for (NSIndexPath *indexPath in sorted) {
        [controller removeObjectAtArrangedObjectIndex:indexPath.item];
    }
}

#pragma mark
#pragma mark Help

- (IBAction) openHelpWebpage:(id)sender
{
	VSWebHelpButton *whb = (VSWebHelpButton *) sender;
	[[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:whb.helpURL]];
}

#pragma mark
#pragma mark Document-closing cleanup behavior

/*
 - (void) canCloseDocumentWithDelegate:(id)delegate shouldCloseSelector:(SEL)shouldCloseSelector contextInfo:(void *)contextInfo
 {
 
 // This is just called to check if the document CAN be closed; before the user has chosen yes/no/cancel
 
 }
 */

- (void) close
{
	[playbackTimer invalidate]; // This prevents the run loop from retaining the document via the timer after it's supposed to be released
	
	// Unregister various observers, or else there are complaints about deallocing objects with observers still attachced
	
	[syncedPlaybackWindowController close];
	syncedPlaybackWindowController = nil;
	for (id windowController in [self windowControllers]) { // Putting this here to remove observer on window controller before document no longer exists
		if ([windowController class] == [VideoWindowController class]) {
			VideoWindowController *__weak vwc = (VideoWindowController *)windowController;
			@try {
				[vwc removeObserver:self forKeyPath:@"playerView.player.rate"];
			} @catch (id exception) {
				NSLog(@"Exception when document tries to to remove observer form VideoWindowController: %@",(NSException *)exception);
			}
			@try {
				[self.project carefullyRemoveObserver:vwc.overlayView forKeyPath:@"distortionDisplayMode"];
			} @catch (id exception) {
				NSLog(@"Exception when document tries to to remove observer form VideoOverlayView: %@",(NSException *)exception);
			}
		}
	}
	
	@try {
		[[NSNotificationCenter defaultCenter] removeObserver:self];
	} @catch (id exception) {
	}
	@try {
		[[NSNotificationCenter defaultCenter] removeObserver:videoClipArrayController];  // registered on videoClipArrayController, not self, so removeObserver:self above doesn't cover it
	} @catch (id exception) {
	}
	[self carefullyRemoveObserver:self forKeyPath:@"portraitSubject"];
	[self carefullyRemoveObserver:syncedPlaybackView forKeyPath:@"bookmarkIsSet1"];
	[self carefullyRemoveObserver:syncedPlaybackView forKeyPath:@"bookmarkIsSet2"];

	// Close floating panels that were loaded from the main XIB but are not registered
	// as document window controllers. Without this, visible panels retain Core Data bindings
	// that keep the document's managed object context alive after close, causing a beachball
	// and binding conflicts when the next document opens.
	for (NSWindow *panel in [[NSApp windows] copy]) {
		if ([panel isKindOfClass:[NSPanel class]] && panel.isVisible) {
			[panel close];
		}
	}

	[super close];
}

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath
{
	if (observer != nil) {
		@try {
			[self removeObserver:observer forKeyPath:keyPath];
		} @catch (id exception) {
			// The "close" method is called twice when closing the document thorugh the menu, because the document closing the first time tells its main window to close, which tells
			// the document to close. This is normal, but the second time will always fail to find the observers because they're removed in the first run.
			// NSLog(@"Exception removing observer %@ from VidSyncDocument on close: %@",observer,(NSException *)exception);
		}
	}
}

@end





