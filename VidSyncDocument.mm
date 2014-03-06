//
//  VidSyncProject.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/22/09.
//  Copyright University of Alaska Fairbanks 2009 . All rights reserved.
//
#import "opencv2/opencv.hpp"

#import "VidSyncDocument.h"

@implementation VidSyncDocument

@synthesize project;

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

@synthesize decimalFormatter;

@synthesize mainWindow;
@synthesize frontVideoClip;
@synthesize syncedPlaybackPanel;

@synthesize directOpenCVView;
@synthesize directOpenCVWindow;

@synthesize magnifiedCalibrationPreview;
@synthesize magnifiedMeasurementPreview;
@synthesize magnifiedDistortionPreview;

@synthesize objectsPortraitsArrayController;

@synthesize bookmarkIsSet1;
@synthesize bookmarkIsSet2;

@synthesize objectsTableSelectionChangeNotificationCascadeEnabled;
@synthesize eventsTableSelectionChangeNotificationCascadeEnabled;

static void *AVSPPlayerRateContext = &AVSPPlayerRateContext;
static void *AVSPPlayerCurrentTimeContext = &AVSPPlayerCurrentTimeContext;

#pragma mark
#pragma mark Initialization

- (id)init 
{
    self = [super init];
    if (self != nil) {
		shutterClick = [[NSSound alloc] initWithContentsOfFile:[[NSBundle mainBundle] pathForSoundResource:@"CameraClick"] byReference:YES];
         
		stopTime = kCMTimeIndefinite;
        bookmarkIsSet1 = NO;
        bookmarkIsSet2 = NO;
        objectsTableSelectionChangeNotificationCascadeEnabled = YES;
        objectsTableSelectionChangeNotificationCascadeEnabled = YES;
		
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
        VideoWindowController __strong *vwc = [[VideoWindowController alloc] initWithVideoClip:clip inManagedObjectContext:[self managedObjectContext]];
        [self observeWindowControllerVideoRate:vwc];
        if (vwc != nil) [self addWindowController:vwc];
    }

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
    [vwc addObserver:self forKeyPath:@"playerView.player.rate" options:NSKeyValueObservingOptionNew context:AVSPPlayerRateContext];
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
        NSMutableAttributedString *portraitWindowOpenButtonTitle =[[NSMutableAttributedString alloc] initWithAttributedString:[[NSMutableAttributedString alloc] initWithString:@"\uf030"]];
        [portraitWindowOpenButtonTitle addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:12.0f] range:NSMakeRange(0,1)];
        [allPortraitBrowserOpenButton setAttributedTitle:portraitWindowOpenButtonTitle];
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
		self.project.dateCreated = [[NSDate dateWithTimeIntervalSinceNow:0.0] description];	// current date as a string
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

- (void) anyTableViewSelectionIsChanging:(NSNotification *)notification		// Controls what to do when a table view's selection is ABOUT to change but hasn't yet.
{
	if (self.project.masterClip != nil) {
		if ([[notification object] isEqualTo:annotationsController.mainTableView]) {
			if ([[annotationsController selectedObjects] count] > 0) {
				VSAnnotation *selectedAnnotation = [[annotationsController selectedObjects] objectAtIndex:0];
				// When an annotation is deselected, remove the observers that are watching to see if its properties change so they can update the overlay.
				[selectedAnnotation removeObserver:selectedAnnotation.videoClip.windowController forKeyPath:@"width"];
				[selectedAnnotation removeObserver:selectedAnnotation.videoClip.windowController forKeyPath:@"color"];
				[selectedAnnotation removeObserver:selectedAnnotation.videoClip.windowController forKeyPath:@"size"];
				[selectedAnnotation removeObserver:selectedAnnotation.videoClip.windowController forKeyPath:@"shape"];
				[selectedAnnotation removeObserver:selectedAnnotation.videoClip.windowController forKeyPath:@"notes"];				
			}
		} else if ([[notification object] isEqualTo:trackedObjectsController.mainTableView]) {
			if ([[notification object] isEqualTo:trackedObjectsController.mainTableView]) {
				if ([[trackedObjectsController selectedObjects] count] > 0) {
					VSTrackedObject *selectedObject = [[trackedObjectsController selectedObjects] objectAtIndex:0];
					// When an object is deselected (often via selecting a point or event belonging to a different object)
					// remove the observer that is watching to see if its color changes so it can update the overlay.
					[selectedObject removeObserver:self forKeyPath:@"color"];
				}
			}		
		}
	}
}

- (void) anyTableViewSelectionDidChange:(NSNotification *)notification	// Controls what to do once a table view's selection HAS changed
{
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
				VSTrackedObject *selectedObject = [[trackedObjectsController selectedObjects] objectAtIndex:0];
				[selectedObject addObserver:self forKeyPath:@"color" options:NSKeyValueObservingOptionNew context:NULL];
                if (objectsTableSelectionChangeNotificationCascadeEnabled) {
                    [trackedEventsController setSelectionIndex:0];	// Select the object's first event
                    [eventsPointsController setSelectionIndex:0];	// and that event's first point
                } else {
                    objectsTableSelectionChangeNotificationCascadeEnabled = YES;
                }
                // the problem is if I disable the notification, they won't scroll and stuff... I just need to tell them not to trigger notifications on their own
                
				[objectSynonymizeController rearrangeObjects];
                [objectsPortraitsArrayController refreshImageBrowserView];
				
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
    if ([keyPath isEqual:@"color"] && [object class] == [VSTrackedObject class]) {
		[self refreshOverlaysOfAllClips:self];
    } else if ([keyPath isEqualToString:@"playerView.player.rate"]) {
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
	self.project.dateLastSaved = [[NSDate dateWithTimeIntervalSinceNow:0.0] description];	// current date as a string
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
    if (self.project.calibrationTimecode != nil) doSet = [UtilityFunctions ConfirmAction:@"You already set a calibration time. Are you sure you want to change it?"];
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
		[eventsPointsController.mainTableView setNeedsDisplay];	// refresh the point table
    }	
	if (fetchResults == nil) [UtilityFunctions InformUser:@"There are no measured points yet, so nothing is being recalculated."];
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

// Delegate method for PortraitBrowserView, following IKImageBrowserDelegate informal protocol)

// Double-clicking on a portrait takes the video to the time at which the portrait was created, and brings that window to the front

- (void)imageBrowser:(IKImageBrowserView *)aBrowser cellWasDoubleClickedAtIndex:(NSUInteger)index
{
    VSTrackedObjectPortrait *portrait = (VSTrackedObjectPortrait *) [[[aBrowser dataSource] arrangedObjects] objectAtIndex:index];
    [self goToMasterTime:[UtilityFunctions CMTimeFromString:portrait.timecode]];
    portrait.sourceVideoClip.windowController.shouldShowPortraitFrame = portrait.frameString;
    [[portrait.sourceVideoClip.windowController window] makeKeyAndOrderFront:self];
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
    // I CAN COMMENT OUT THE PLAYBACK TIMER INVALIDATION TO MAKE DOCUMENTS "CLOSE" WITHOUT CRASHING, EXCEPT THEY AREN'T ACTUALLY CLOSED
    [playbackTimer invalidate]; // This prevents the run loop from retaining the document via the timer after it's supposed to be released

    // Unregister various observers, or else there are complaints about deallocing objects with observers still attachced
    
    [syncedPlaybackWindowController close];
    syncedPlaybackWindowController = nil;
    
    for (id windowController in [self windowControllers]) { // Putting this here to remove observer on window controller before document no longer exists
        if ([windowController class] == [VideoWindowController class]) {
            VideoWindowController *__weak vwc = (VideoWindowController *)windowController;
            @try {
                [windowController removeObserver:self forKeyPath:@"playerView.player.rate"];
            } @catch (id exception) {
                NSLog(@"exception when document tries to to remove observer form VideoWindowController: %@",(NSException *)exception);
            }
            @try {
                [self.project carefullyRemoveObserver:vwc.overlayView forKeyPath:@"distortionDisplayMode"];
            } @catch (id exception) {
                NSLog(@"exception when document tries to to remove observer form VideoOverlayView: %@",(NSException *)exception);
            }
        }
    }
    
    @try {
        [[NSNotificationCenter defaultCenter] removeObserver:self];
    } @catch (id exception) {
    }
    [self carefullyRemoveObserver:self forKeyPath:@"portraitSubject"];
    [self carefullyRemoveObserver:syncedPlaybackView forKeyPath:@"bookmarkIsSet1"];
    [self carefullyRemoveObserver:syncedPlaybackView forKeyPath:@"bookmarkIsSet2"];
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





