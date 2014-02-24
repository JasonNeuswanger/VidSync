//
//  VideoWindowController.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/26/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VideoWindowController.h"


@implementation VideoWindowController

@synthesize movie;
@synthesize videoClip;
@synthesize videoTrack;
@synthesize movieSize;
@synthesize managedObjectContext;
@synthesize overlayWidth;
@synthesize overlayHeight;
@synthesize overlayView;
@synthesize playerView;
@synthesize playerItem;
@synthesize playerLayer;
@synthesize assetImageGenerator;
@synthesize videoAsset;
@synthesize portraitDragStartCoords;
@synthesize portraitDragCurrentCoords;
@synthesize shouldShowPortraitFrame;

#pragma mark
#pragma mark Initialization

- (VideoWindowController *)initWithVideoClip:(VSVideoClip *)inVideoClip inManagedObjectContext:(NSManagedObjectContext *)moc
{
    AVAsset *movieAsset = [self playableAssetForClipName:inVideoClip.clipName atPath:inVideoClip.fileName];
    if (movieAsset != nil) {
        
        
        NSArray *assetKeysToLoadAndTest = [NSArray arrayWithObjects:@"playable", @"tracks", @"duration", nil];
        
        
        
        [movieAsset loadValuesAsynchronouslyForKeys:assetKeysToLoadAndTest completionHandler:^(void) {
            // The asset invokes its completion handler on an arbitrary queue when loading is complete.
            // Because we want to access our AVPlayer in our ensuing set-up, we must dispatch our handler to the main queue.
            dispatch_async(dispatch_get_main_queue(), ^(void) {
                [self setUpPlaybackOfAsset:movieAsset withKeys:assetKeysToLoadAndTest];
            });
        }];
        
        // maybe I need to put this stuff in the
        
        self = [super initWithWindowNibName:@"VideoClipWindow"];
        [self setShouldCascadeWindows:NO];
        self.videoClip = inVideoClip;
        self.videoClip.windowController = self;
        managedObjectContext = moc;
        if (self.videoClip.windowFrame != nil) [[self window] setFrameFromString:self.videoClip.windowFrame];
        [self window]; // calling [self window] here used to be required to trigger windowDidLoad, and prevent odd video loading bugs in the release but not debug build... I don't know why
        return self;
        
        
        
    } else {
        return nil;
    }
}

- (AVAsset *) playableAssetForClipName:(NSString *)clipName atPath:(NSString *)filePath
{
    // All validation of the file as a playable video asset occurs in this function, and the user is prompted to find a valid file if this one isn't playable.
    NSMutableString *invalidFileMessage = [NSMutableString new];
    NSURL *movieURL = [NSURL fileURLWithPath:filePath isDirectory:NO];
    NSError *urlFoundError;
    BOOL foundFileAtURL = [movieURL checkResourceIsReachableAndReturnError:&urlFoundError];
    NSString *mavericksFormatExplanation = @"\n\nGenerally, VidSync can play any file Quicktime can play on the same computer. However, Quicktime in OS X 10.9 (Mavericks) invalidated many older codecs, so some files that used to work with VidSync might now require a conversion to a more modern codec such as H.264. Quicktime Player can do this for free, and some third-party applications can do batches of videos more quickly.";
    if (foundFileAtURL) {
        AVAsset *movieAsset = [AVAsset assetWithURL:movieURL];
        if ([[movieAsset tracksWithMediaType:AVMediaTypeVideo] count] > 0) {
            AVAssetTrack *movieTrack = [[movieAsset tracksWithMediaType:AVMediaTypeVideo] objectAtIndex:0];
            if ([movieTrack isPlayable]) {
                return movieAsset;              // Here's where the function returns if it actually finds a playable movie asset
            } else {
                [invalidFileMessage setString:[NSString stringWithFormat:@"A video file was found for clip '%@' at location %@, but it is not playable.%@",clipName,filePath,mavericksFormatExplanation]];
            }
        } else {
            [movieAsset cancelLoading];
            [invalidFileMessage setString:[NSString stringWithFormat:@"A file was found for clip '%@' at location %@, but it is not recognized as a playable video.%@",clipName,filePath,mavericksFormatExplanation]];
        }
    } else {
        [invalidFileMessage setString:[NSString stringWithFormat:@"No file was found for clip '%@' at location %@.",clipName,filePath]];
    }
    
    NSAlert *invalidFileAlert = [NSAlert new];
    [invalidFileAlert setMessageText:@"Video file missing or not in a recognized/playable format"];
    [invalidFileAlert setInformativeText:[invalidFileMessage stringByAppendingString:@"\n\nTo load a video for this clip, select a valid video file location using the 'Relocate Selected Clip' button under the 'Project' tab."]];
    [invalidFileAlert addButtonWithTitle:@"Ok"];
    [invalidFileAlert setAlertStyle:NSCriticalAlertStyle];
    [invalidFileAlert runModal];
    return nil;
}

- (void)setUpPlaybackOfAsset:(AVAsset *)asset withKeys:(NSArray *)keys // modified from Apple's AVSimplePlayer example
{
    // This method is called when the AVAsset for our URL has completing the loading of the values of the specified array of keys.
    
    // Set up an AVPlayerLayer according to whether the asset contains video.
    assetImageGenerator = [AVAssetImageGenerator assetImageGeneratorWithAsset:asset];  // first, initializing the asset image generator quickly for screenshots etc later
    assetImageGenerator.requestedTimeToleranceBefore = kCMTimeZero;
    assetImageGenerator.requestedTimeToleranceAfter = kCMTimeZero;
    videoTrack = [[asset tracksWithMediaType:AVMediaTypeVideo] firstObject];
    videoAsset = asset;
    // Create a new AVPlayerItem.
    AVPlayerItem *thePlayerItem = [AVPlayerItem playerItemWithAsset:asset];
    AVPlayer *thePlayer = [AVPlayer playerWithPlayerItem:thePlayerItem];
    playerView.player = thePlayer;
    self.playerItem = thePlayerItem; // don't know why I can't just initialize it normally
    playerLayer = [AVPlayerLayer playerLayerWithPlayer:thePlayer];

    movieSize = videoTrack.naturalSize;
    
    [self.videoClip setMasterControls];
    [self fitVideoOverlay];
    
    if (self.videoClip.isMasterClipOf == self.videoClip.project && self.videoClip.project.currentTimecode) {	// If the master clip is loaded and there's a saved current time, go to it
        // The next three lines set the number of ticks in the synced playback scrubber to approximately 1 per minute
        CMTimeRange masterTimeRange = [[[self.videoClip.project.masterClip.windowController.videoAsset tracksWithMediaType:AVMediaTypeVideo] firstObject] timeRange];
        NSInteger masterTimeDurationMinutes = round(CMTimeGetSeconds(masterTimeRange.duration)/60.0f);
        [self.videoClip.project.document.syncedPlaybackScrubber setNumberOfTickMarks:masterTimeDurationMinutes+1];  // adds 1 extra tickmark because there's a tick at 0. will be close but not exactly 1 tick/minute now
        [self.videoClip.windowController.playerView.player seekToTime:[UtilityFunctions CMTimeFromString:self.videoClip.project.currentTimecode] toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero];
        [self.videoClip.project.document reSync];
    }
    if (self.videoClip.syncIsLocked) {
        [self.videoClip.project.document.syncedPlaybackPanel orderFront:self]; // this will make the synced playback panel visible if any videos are synced
        [self.videoClip.project.document reSync];                               // synchronizes the document once the new clip is loaded
    }
    
    [[self window] orderFrontRegardless];
}

- (void) windowDidLoad
{
    [[self window] orderFrontRegardless];
}

- (NSString *)windowTitleForDocumentDisplayName:(NSString *)displayName
{
	if(self.videoClip.clipName)
		return [NSString stringWithFormat:@"%@ - %@", self.videoClip.clipName, displayName];
	else
		return displayName;
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
    if ([keyPath isEqual:@"width"] || [keyPath isEqual:@"color"] || [keyPath isEqual:@"size"] || [keyPath isEqual:@"shape"] || [keyPath isEqual:@"notes"]) {
		[self refreshOverlay];
    }
}


- (void) updateMagnifiedPreviewWithCenter:(NSPoint)point // point should be in base video coords, not current overlay coords
{
    [[self document] updatePreviewImageWithPlayerLayer:playerLayer atPoint:point];
}

- (void)windowDidResize:(NSNotification *)notification // delegate method for the NSWindow being controlled
{
	if (self.playerItem != nil) { // ignores the resize event when the windows first pop up, before the media is loaded
        [self fitVideoOverlay];
        self.videoClip.windowFrame = [[self window] stringWithSavedFrame];
        [overlayView calculateQuadratCoordinateGrids];
    }
}

- (void)windowDidMove:(NSNotification *)notification
{
	self.videoClip.windowFrame = [[self window] stringWithSavedFrame];
}

- (void) makeOverlayKeyWindow
{
	[overlayWindow makeKeyWindow];
}

- (void) fitVideoOverlay // creates the video overlay and/or fits it to the video view
{
	float videoAspectRatio = movieSize.width / movieSize.height;
	float viewAspectRatio = [playerView frame].size.width / [playerView frame].size.height;
	float xPosOffset,yPosOffset;
	if (viewAspectRatio < videoAspectRatio) { // Movie width determines window size; black-space above and below
		overlayWidth = [playerView frame].size.width;
		overlayHeight = overlayWidth / videoAspectRatio;
		xPosOffset = 0.0f;
		yPosOffset = ([playerView frame].size.height - overlayHeight) / 2.0f;
	} else { // Movie height determines window size; black-space left and right
		overlayHeight = [playerView frame].size.height;
		overlayWidth = overlayHeight * videoAspectRatio;
		xPosOffset = ([playerView frame].size.width - overlayWidth) / 2.0f;
		yPosOffset = 0.0f;
	}
    
	NSPoint baseOrigin, screenOrigin;
	baseOrigin = NSMakePoint([playerView frame].origin.x,[playerView frame].origin.y);
	screenOrigin = [[playerView window] convertBaseToScreen:baseOrigin];
	NSRect overlayWindowFrameRect = NSMakeRect(screenOrigin.x + xPosOffset,
											   screenOrigin.y + yPosOffset,
											   overlayWidth,
											   overlayHeight);
	if (overlayWindow == nil) {
		overlayWindow = [[VideoOverlayWindow alloc] initWithContentRect:overlayWindowFrameRect
													styleMask:NSBorderlessWindowMask 
													  backing:NSBackingStoreBuffered 
														defer:YES];
		[overlayWindow setOpaque:NO];
		[overlayWindow setHasShadow:NO];
		[overlayWindow setIgnoresMouseEvents:NO];
		[overlayWindow setAlphaValue:1.0];
		[overlayWindow useOptimizedDrawing:YES];
	} else {
		[overlayWindow setFrame:overlayWindowFrameRect display:YES];
	}
	NSRect overlaySubViewRect = NSMakeRect([playerView bounds].origin.x,
										   [playerView bounds].origin.y,
										   overlayWidth,
										   overlayHeight);
	if (overlayView == nil) {
		overlayView = [[VideoOverlayView alloc] initWithFrame:overlaySubViewRect];
		[overlayView setDelegate:self];
		[[overlayWindow contentView] addSubview:overlayView];
		[[playerView window] addChildWindow:overlayWindow ordered:NSWindowAbove];
		[overlayWindow orderFront:self];
	} else {
		[overlayView setFrame:overlaySubViewRect];
	}
	[self refreshOverlay];
}

- (NSPoint) convertVideoToOverlayCoords:(NSPoint)videoCoords 
{
	float scaleFactor = movieSize.width / overlayWidth; 
	return NSMakePoint(videoCoords.x/scaleFactor,videoCoords.y/scaleFactor);
}

- (NSRect) convertVideoToOverlayRect:(NSRect)videoRect
{
	float scaleFactor = movieSize.width / overlayWidth;
    return NSMakeRect(videoRect.origin.x/scaleFactor,videoRect.origin.y/scaleFactor,videoRect.size.width/scaleFactor,videoRect.size.height/scaleFactor);
}

- (NSPoint) convertOverlayToVideoCoords:(NSPoint)overlayCoords 
{
	float scaleFactor = movieSize.width / overlayWidth; 
	return NSMakePoint(overlayCoords.x*scaleFactor,overlayCoords.y*scaleFactor);
}

#pragma mark
#pragma mark Key Events

- (void) handleOverlayKeyUp:(NSEvent *)theEvent
{
	VidSyncDocument *doc = self.document;
    if ([theEvent modifierFlags] & NSAlternateKeyMask) {            // Forward option+leftarrow and option+rightarrow keypresses to the appropriate PlayWhilePressedButton
        unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
        if (key == NSLeftArrowFunctionKey) {
            if ([theEvent modifierFlags] & NSControlKeyMask) {
                [doc.playBackwardAtRate2WhilePressedButton stopPlaying];
            } else {
                [doc.playBackwardAtRate1WhilePressedButton stopPlaying];
            }
        } else if (key == NSRightArrowFunctionKey ) {
            if ([theEvent modifierFlags] & NSControlKeyMask || [theEvent modifierFlags] & NSCommandKeyMask) {
                [doc.playForwardAtRate2WhilePressedButton stopPlaying];
            } else {
                [doc.playForwardAtRate1WhilePressedButton stopPlaying];
            }
        }
	}
}

- (void) handleOverlayKeyDown:(NSEvent *)theEvent
{
	VidSyncDocument *doc = self.document;
	if ([theEvent modifierFlags] & NSCommandKeyMask) {				// Forward all keypresses with the Command key down (mainly playback controls) to the main window
		[doc.mainWindow keyDown:theEvent];
		return;
	}
    if ([theEvent modifierFlags] & NSAlternateKeyMask) {            // Forward option+leftarrow and option+rightarrow keypresses to the appropriate PlayWhilePressedButton
        if (![theEvent isARepeat]) {
            unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
            if (key == NSLeftArrowFunctionKey) {
                if ([theEvent modifierFlags] & NSControlKeyMask) {
                    [doc.playBackwardAtRate2WhilePressedButton startPlaying];
                } else {
                    [doc.playBackwardAtRate1WhilePressedButton startPlaying];
                }
            } else if (key == NSRightArrowFunctionKey) {
                if ([theEvent modifierFlags] & NSControlKeyMask) {
                    [doc.playForwardAtRate2WhilePressedButton startPlaying];
                } else {
                    [doc.playForwardAtRate1WhilePressedButton startPlaying];
                }
            }
        }
        return;
	}
	if ([[theEvent charactersIgnoringModifiers] isEqualToString:@" "]) {
		if ([[doc videoClipArrayController] canSelectNext]) {
			[[doc videoClipArrayController] selectNext:self];
		} else {
			[[doc videoClipArrayController] setSelectionIndex:0];
		}
		
		return;
	}
	if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Measurement"]) {
		[self handleOverlayKeyDownInMeasureMode:theEvent];
	} else if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Calibration"]) {
		if ([[[doc.calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"3D Calibration Frame Input"]) {	// don't process clicks while on "Results" tab
			if ([videoClip isAtCalibrationTime]) [self handleOverlayKeyDownInCalibrateMode:theEvent];
		} else if ([[[doc.calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"Lens Distortion"]) {
			[self handleOverlayKeyDownInDistortionMode:theEvent];
		}
	} else if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Annotation"]) {
		[self handleOverlayKeyDownInAnnotateMode:theEvent];
	}	
}

- (void) handleOverlayKeyDownInDistortionMode:(NSEvent *)theEvent
{
	VidSyncDocument *doc = self.document;
	unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
	float selectedPointNudgeDistance = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"selectedPointNudgeDistance"] floatValue];
	if ([[doc.distortionPointsController selectedObjects] count] > 0) {
		VSDistortionPoint *selectedPoint = [[doc.distortionPointsController selectedObjects] objectAtIndex:0];
		if (key == NSDeleteCharacter || key == NSDeleteFunctionKey) {
			[managedObjectContext deleteObject:selectedPoint];
			[managedObjectContext processPendingChanges];		
		} else if (key == NSUpArrowFunctionKey) {
			selectedPoint.screenY = [NSNumber numberWithFloat:[selectedPoint.screenY floatValue] + selectedPointNudgeDistance];
		} else if (key == NSDownArrowFunctionKey) {
			selectedPoint.screenY = [NSNumber numberWithFloat:[selectedPoint.screenY floatValue] - selectedPointNudgeDistance];
		} else if (key == NSLeftArrowFunctionKey) {
			selectedPoint.screenX = [NSNumber numberWithFloat:[selectedPoint.screenX floatValue] - selectedPointNudgeDistance];
		} else if (key == NSRightArrowFunctionKey) {
			selectedPoint.screenX = [NSNumber numberWithFloat:[selectedPoint.screenX floatValue] + selectedPointNudgeDistance];
		}
		if (key == NSDeleteCharacter || key == NSDeleteFunctionKey || key == NSUpArrowFunctionKey || key == NSDownArrowFunctionKey || key == NSLeftArrowFunctionKey || key == NSRightArrowFunctionKey) {
			[doc.distortionPointsController.mainTableView display];																				// refresh the point table
			[doc.distortionLinesController.mainTableView display];	// refresh the line table's # Points column
			[self updateMagnifiedPreviewWithCenter:NSMakePoint([selectedPoint.screenX floatValue],[selectedPoint.screenY floatValue])];
			[self refreshOverlay];
		}
		
	}	
}

- (void) handleOverlayKeyDownInCalibrateMode:(NSEvent *)theEvent
{
	VidSyncDocument *doc = self.document;
	unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
	float selectedPointNudgeDistance = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"selectedPointNudgeDistance"] floatValue];
	CalibScreenPtArrayController *pointsArrayController = nil;
	NSString *currentSurface = [[doc.calibrationSurfaceTabView selectedTabViewItem] label];
	if ([currentSurface isEqualToString:@"Front Frame Surface"]) {
		pointsArrayController = self.videoClip.project.document.calibScreenPtFrontArrayController;
	} else if ([currentSurface isEqualToString:@"Back Surface"]) {
		pointsArrayController = self.videoClip.project.document.calibScreenPtBackArrayController;
	}
	if ([[pointsArrayController selectedObjects] count] > 0) {
		VSCalibrationPoint *selectedPoint = [[pointsArrayController selectedObjects] objectAtIndex:0];
		if (key == NSDeleteCharacter || key == NSDeleteFunctionKey) {
			selectedPoint.screenX = [NSNumber numberWithFloat:0.0];
			selectedPoint.screenY = [NSNumber numberWithFloat:0.0];			
		} else if (key == NSUpArrowFunctionKey) {
			selectedPoint.screenY = [NSNumber numberWithFloat:[selectedPoint.screenY floatValue] + selectedPointNudgeDistance];
		} else if (key == NSDownArrowFunctionKey) {
			selectedPoint.screenY = [NSNumber numberWithFloat:[selectedPoint.screenY floatValue] - selectedPointNudgeDistance];
		} else if (key == NSLeftArrowFunctionKey) {
			selectedPoint.screenX = [NSNumber numberWithFloat:[selectedPoint.screenX floatValue] - selectedPointNudgeDistance];
		} else if (key == NSRightArrowFunctionKey) {
			selectedPoint.screenX = [NSNumber numberWithFloat:[selectedPoint.screenX floatValue] + selectedPointNudgeDistance];
		}
		if (key == NSDeleteCharacter || key == NSDeleteFunctionKey || key == NSUpArrowFunctionKey || key == NSDownArrowFunctionKey || key == NSLeftArrowFunctionKey || key == NSRightArrowFunctionKey) {
			[pointsArrayController.mainTableView setNeedsDisplayInRect:[doc.trackedEventsController.mainTableView rectOfColumn:2]];	// refresh the event table's # Points column
			[pointsArrayController.mainTableView setNeedsDisplayInRect:[doc.trackedEventsController.mainTableView rectOfColumn:3]];	// refresh the event table's # Points column
			[self updateMagnifiedPreviewWithCenter:NSMakePoint([selectedPoint.screenX floatValue],[selectedPoint.screenY floatValue])];
			[self refreshOverlay];
		}
		
	}	
}

- (void) handleOverlayKeyDownInMeasureMode:(NSEvent *)theEvent
{
	unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
	float selectedPointNudgeDistance = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"selectedPointNudgeDistance"] floatValue];
	if ([[self.videoClip.project.document.eventsPointsController selectedObjects] count] > 0) {
		VSPoint *selectedPoint = [[self.videoClip.project.document.eventsPointsController selectedObjects] objectAtIndex:0];
		VSEventScreenPoint *selectedScreenPoint = [selectedPoint screenPointForVideoClip:self.videoClip];
		if (selectedScreenPoint != nil) {
			if (key == NSDeleteCharacter || key == NSDeleteFunctionKey) {
				[managedObjectContext deleteObject:selectedScreenPoint];
				[managedObjectContext processPendingChanges];	// have to do this to get a correct screenPoints count in handleScreenPointChange
				[selectedPoint handleScreenPointChange];
				[self refreshOverlay];
			} else if (key == NSUpArrowFunctionKey) {
				selectedScreenPoint.screenY = [NSNumber numberWithFloat:[selectedScreenPoint.screenY floatValue] + selectedPointNudgeDistance];
			} else if (key == NSDownArrowFunctionKey) {
				selectedScreenPoint.screenY = [NSNumber numberWithFloat:[selectedScreenPoint.screenY floatValue] - selectedPointNudgeDistance];
			} else if (key == NSLeftArrowFunctionKey) {
				selectedScreenPoint.screenX = [NSNumber numberWithFloat:[selectedScreenPoint.screenX floatValue] - selectedPointNudgeDistance];
			} else if (key == NSRightArrowFunctionKey) {
				selectedScreenPoint.screenX = [NSNumber numberWithFloat:[selectedScreenPoint.screenX floatValue] + selectedPointNudgeDistance];
			}
			if (key == NSUpArrowFunctionKey || key == NSDownArrowFunctionKey || key == NSLeftArrowFunctionKey || key == NSRightArrowFunctionKey) {
				if ([self.document currentMasterTimeIs:[UtilityFunctions CMTimeFromString:[selectedPoint timecode]]]) {
					[selectedPoint handleScreenPointChange];
					if ([self.videoClip isCalibrated]) [selectedScreenPoint calculateHintLines];
					[self updateMagnifiedPreviewWithCenter:NSMakePoint([selectedScreenPoint.screenX floatValue],[selectedScreenPoint.screenY floatValue])];
					[self.videoClip.project.document refreshOverlaysOfAllClips:self];
				} else {
					NSUInteger nudgeWarningResult = NSRunAlertPanel(@"Can't nudge that point right now.",
									@"You can only nudge a point while the video is on the frame/timecode at which the point was created, even though the point is visible for selection after that.",
									@"Ok, ignore the nudge.",
									@"Go to the point's original timecode.",
									nil);
					if (nudgeWarningResult == NSAlertAlternateReturn) {
						[self.document goToMasterTime:[UtilityFunctions CMTimeFromString:selectedPoint.timecode]];
					}
				}
			}
		}
	}
}

- (void) handleOverlayKeyDownInAnnotateMode:(NSEvent *)theEvent
{
	unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
	float selectedPointNudgeDistance = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"selectedPointNudgeDistance"] floatValue] * 10.0;
	if ([[self.videoClip.project.document.annotationsController selectedObjects] count] > 0) {
		VSAnnotation *selectedAnnotation = [[self.videoClip.project.document.annotationsController selectedObjects] objectAtIndex:0];
		if (key == NSDeleteCharacter || key == NSDeleteFunctionKey) {
			[managedObjectContext deleteObject:selectedAnnotation];
			[managedObjectContext processPendingChanges];	// have to do this to get a correct screenPoints count in handleScreenPointChange
			[self refreshOverlay];
		} else if (key == NSUpArrowFunctionKey) {
			selectedAnnotation.screenY = [NSNumber numberWithFloat:[selectedAnnotation.screenY floatValue] + selectedPointNudgeDistance];
		} else if (key == NSDownArrowFunctionKey) {
			selectedAnnotation.screenY = [NSNumber numberWithFloat:[selectedAnnotation.screenY floatValue] - selectedPointNudgeDistance];
		} else if (key == NSLeftArrowFunctionKey) {
			selectedAnnotation.screenX = [NSNumber numberWithFloat:[selectedAnnotation.screenX floatValue] - selectedPointNudgeDistance];
		} else if (key == NSRightArrowFunctionKey) {
			selectedAnnotation.screenX = [NSNumber numberWithFloat:[selectedAnnotation.screenX floatValue] + selectedPointNudgeDistance];
		}
		if (key == NSUpArrowFunctionKey || key == NSDownArrowFunctionKey || key == NSLeftArrowFunctionKey || key == NSRightArrowFunctionKey) {
			[self refreshOverlay];
		}
	}
}

#pragma mark
#pragma mark Drag and Mouseup Events (for portraits)

- (void) handleOverlayMouseUp:(NSPoint)coords fromEvent:(NSEvent *)theEvent
{
    if (self.videoClip.project.document.portraitSubject != nil && [[[[self.document mainTabView] selectedTabViewItem] label] isEqualToString:@"Measurement"]) {
        portraitDragCurrentCoords = [self convertOverlayToVideoCoords:coords];
        //NSImage *returnImage = [NSImage alloc];
        NSPoint startPoint = NSMakePoint(portraitDragStartCoords.x,portraitDragStartCoords.y);
        NSPoint endPoint = portraitDragCurrentCoords;
        if (startPoint.x != endPoint.x && startPoint.y != endPoint.y) {
            float width = fabs(startPoint.x - endPoint.x);
            float height = fabs(startPoint.y - endPoint.y);
            NSRect imageRect = NSMakeRect(MIN(startPoint.x,endPoint.x),MIN(startPoint.y,endPoint.y),width,height);
            imageRect.origin.y = movieSize.height - imageRect.origin.y - imageRect.size.height;    // Flips the rect around to account for difference between top-left and bottom-left zeroed coordinate systems
            CMTime offset = [UtilityFunctions CMTimeFromString:videoClip.syncOffset];
            CMTime movieTime = CMTimeSubtract([[self document] currentMasterTime],offset);
            CMTime actualCopiedTime;
            NSError *err;
            CGImageRef fullScreenImage = [assetImageGenerator copyCGImageAtTime:movieTime actualTime:&actualCopiedTime error:&err];
            CGImageRef portraitImage = CGImageCreateWithImageInRect(fullScreenImage,imageRect);
            if (err != nil) [NSApp presentError:err];
            
            NSImage *__strong returnImage = [[NSImage alloc] initWithCGImage:portraitImage size:NSZeroSize];
            VSTrackedObject *__weak currentObject = [[[[self document] trackedObjectsController] selectedObjects] firstObject];
            
            [[[self document] objectsPortraitsArrayController] addImage:returnImage ofObject:currentObject fromSourceClip:self.videoClip inRect:imageRect withTimecode:[[self document] currentMasterTimeString]];
        }
        self.videoClip.project.document.portraitSubject = nil;
        [self refreshOverlay];
    }
}

- (void) handleOverlayMouseDrag:(NSPoint)coords fromEvent:(NSEvent *)theEvent
{
    if (self.videoClip.project.document.portraitSubject != nil && [[[[self.document mainTabView] selectedTabViewItem] label] isEqualToString:@"Measurement"]) {
        [self updateMagnifiedPreviewWithCenter:[self convertOverlayToVideoCoords:coords]];
        portraitDragCurrentCoords = [self convertOverlayToVideoCoords:coords];
        [self refreshOverlay];
    }
}


#pragma mark
#pragma mark Click Events

- (void) handleOverlayClick:(NSPoint)coords fromEvent:(NSEvent *)theEvent;
{
    NSPoint videoCoords;
    if (([theEvent modifierFlags] & NSCommandKeyMask) || [theEvent buttonNumber] == 3) {    // If clicking with command key held down, or clicking mouse button 4
        videoCoords = [self.videoClip.calibration snapToFeatureNearestToClick:[self convertOverlayToVideoCoords:coords]];
    } else {
        videoCoords = [self convertOverlayToVideoCoords:coords];
    }
    VidSyncDocument *doc = self.document;
	
    if (self.videoClip.project.document.portraitSubject != nil && [[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Measurement"]) {   // if in portrait mode, handle everything differently
        portraitDragStartCoords = videoCoords;
    } else {
        if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Calibration"]) {
            if ([[[doc.calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"3D Calibration Frame Input"]) {	// don't process clicks while on "Results" tab
                if ([videoClip isAtCalibrationTime]) {
                    [self.videoClip.calibration processClickOnSurface:[[doc.calibrationSurfaceTabView selectedTabViewItem] label] withCoords:videoCoords];
                } else {
                    NSRunAlertPanel(@"Not At Calibration Frame",@"Ignoring calibration click because this video isn't at the current calibration time.  Use 'Go to Calibration Frame' to go there, or 'Use Current Frame' to select this frame as the calibration frame.",@"Ok",nil,nil);
                }
            } else if ([[[doc.calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"Lens Distortion"]) {
                [doc.distortionLinesController appendPointToSelectedLineAt:videoCoords];
                [self updateMagnifiedPreviewWithCenter:videoCoords];
            }
        } else if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Measurement"]) {
            if ([[doc.trackedObjectsController selectedObjects] count] == 1) {
                if ([[doc.trackedEventsController selectedObjects] count] == 1) {
                    VSTrackedEvent *activeEvent = [[doc.trackedEventsController selectedObjects] objectAtIndex:0];
                    VSEventScreenPoint *newScreenPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSEventScreenPoint" inManagedObjectContext:managedObjectContext];
                    newScreenPoint.videoClip = videoClip;
                    newScreenPoint.screenX = [NSNumber numberWithFloat:videoCoords.x];
                    newScreenPoint.screenY = [NSNumber numberWithFloat:videoCoords.y];
                    CMTime masterTime = [videoClip.project.document currentMasterTime];		// Current timecode of the project's masterClip
                    VSPoint *point = [activeEvent pointToTakeScreenPointFromClip:videoClip atTime:masterTime];	// Retrieve or create the appropriate VSPoint to add this VSScreenPoint to
                    newScreenPoint.point = point;
                    [point handleScreenPointChange];
                    [doc.eventsPointsController setSelectedObjects:[NSArray arrayWithObject:point]];
                    if ([self.videoClip isCalibrated]) [newScreenPoint calculateHintLines];
                } else {
                    NSRunAlertPanel(@"No Selected Event",@"Ignoring measurement click because there is no selected event.",@"Ok",nil,nil);
                }
            } else {
                NSRunAlertPanel(@"No Selected Object",@"Ignoring measurement click because there is no selected object.",@"Ok",nil,nil);
            }
        } else if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Annotation"]) {
            // The work of creating an annotation is handled by the createNewAnnotation action.
            // However, I have to lock in the timecode and coordinate values from the click immediately, since they may change after the panel button is submitted.
            newAnnotationStartTimecode = [UtilityFunctions CMStringFromTime:[videoClip.project.document currentMasterTime]];
            newAnnotationCoords = videoCoords;
            NSRect currentWindowFrame = [[self window] frame];
            [newAnnotationContents setStringValue:@""];
            [newAnnotationPanel setFrameTopLeftPoint:NSMakePoint(coords.x + currentWindowFrame.origin.x,coords.y + currentWindowFrame.origin.y)];
            [newAnnotationPanel makeKeyAndOrderFront:self];
        }
        [self.videoClip.project.document refreshOverlaysOfAllClips:self];
    }
}

- (IBAction) createNewAnnotation:(id)sender
{	
	[newAnnotationPanel close];
	if (![[newAnnotationContents stringValue] isEqualToString:@""]) {
		VSAnnotation *newAnnotation = [NSEntityDescription insertNewObjectForEntityForName:@"VSAnnotation" inManagedObjectContext:managedObjectContext]; 
		newAnnotation.screenX = [NSNumber numberWithFloat:newAnnotationCoords.x];
		newAnnotation.screenY = [NSNumber numberWithFloat:newAnnotationCoords.y];		
		newAnnotation.startTimecode = newAnnotationStartTimecode;
		newAnnotation.color = [UtilityFunctions userDefaultColorForKey:@"newAnnotationColor"];
		newAnnotation.notes = [newAnnotationContents stringValue];
		newAnnotation.shape = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"newAnnotationFontFace"];
		newAnnotation.duration = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"newAnnotationDuration"];
		newAnnotation.fadeTime = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"newAnnotationFadeTime"];
		newAnnotation.size = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"newAnnotationFontSize"];
		newAnnotation.videoClip = self.videoClip;
		[self.videoClip.project.document.annotationsController setSelectedObjects:[NSArray arrayWithObject:newAnnotation]];
	}
	[self refreshOverlay];
}

- (void) handleOverlayRightClick:(NSPoint)coords
{
	NSPoint videoCoords = [self convertOverlayToVideoCoords:coords];
	VidSyncDocument *doc = self.document;
	if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Measurement"]) {
		[self handleOverlayRightClickInMeasureMode:videoCoords];
	} else if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Calibration"]) {
		if ([[[doc.calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"3D Calibration Frame Input"]) {	// don't process clicks while on "Results" tab
			if ([videoClip isAtCalibrationTime]) [self handleOverlayRightClickInCalibrateMode:videoCoords];
		} else if ([[[doc.calibrationInputTabView selectedTabViewItem] label] isEqualToString:@"Lens Distortion"]) {
			[self handleOverlayRightClickInDistortionMode:videoCoords];
		}
	} else if ([[[doc.mainTabView selectedTabViewItem] label] isEqualToString:@"Annotation"]) {
		[self handleOverlayRightClickInAnnotateMode:videoCoords];
	}
}

- (void) handleOverlayRightClickInDistortionMode:(NSPoint)coords
{
	VidSyncDocument *doc = self.document;
	
	float shortestDistanceFromClick = 1000000.0;								// initialize with an absurdly high number, so the first real click will be "closer"
	float distanceFromClick;
	float clickToPointVector[2];
	VSDistortionPoint *pointToSelect = nil;
	for (VSDistortionLine *distortionLine in self.videoClip.calibration.distortionLines) {
		for (VSDistortionPoint *distortionPoint in distortionLine.distortionPoints) {
			clickToPointVector[0] = coords.x - [distortionPoint.screenX floatValue];
			clickToPointVector[1] = coords.y - [distortionPoint.screenY floatValue];
			distanceFromClick = cblas_snrm2(2, clickToPointVector, 1);
			if (distanceFromClick < shortestDistanceFromClick) {
				pointToSelect = distortionPoint;
				shortestDistanceFromClick = distanceFromClick;
			}
		}
	}
	if (pointToSelect != nil) {
		if ([[doc.distortionPointsController selectedObjects] count] > 0 && [[[doc.distortionPointsController selectedObjects] objectAtIndex:0] isEqualTo:pointToSelect]) {		// if the point is already selected, deselect it
			[doc.distortionPointsController setSelectedObjects:nil];
		} else {
			[doc.distortionLinesController setSelectedObjects:[NSArray arrayWithObject:pointToSelect.distortionLine]];
			[doc.distortionPointsController setSelectedObjects:[NSArray arrayWithObject:pointToSelect]];		
		}
	}
	[self refreshOverlay];
}

- (void) handleOverlayRightClickInCalibrateMode:(NSPoint)coords
{	
	VidSyncDocument *doc = self.document;
	NSString *currentSurface = [[doc.calibrationSurfaceTabView selectedTabViewItem] label];
	NSArrayController *pointsArrayController = nil;
	if ([currentSurface isEqualToString:@"Front Frame Surface"]) {
		pointsArrayController = self.videoClip.project.document.calibScreenPtFrontArrayController;
	} else if ([currentSurface isEqualToString:@"Back Surface"]) {
		pointsArrayController = self.videoClip.project.document.calibScreenPtBackArrayController;
	}
	NSArray *pointsWithScreenCoordinates = [NSArray array];
	for (VSCalibrationPoint *testPoint in [pointsArrayController arrangedObjects]) {	// filter out the points that don't have any screen coordinates yet
		if ([testPoint.screenX floatValue] != 0.0 || [testPoint.screenY floatValue] != 0.0) pointsWithScreenCoordinates = [pointsWithScreenCoordinates arrayByAddingObject:testPoint];
	}	
	if ([pointsWithScreenCoordinates count] > 0) {
		VSCalibrationPoint *pointToSelect = nil;
		if ([pointsWithScreenCoordinates count] > 1) {
			float shortestDistanceFromClick = 1000000.0;								// initialize with an absurdly high number, so the first real click will be "closer"
			float distanceFromClick;
			float clickToPointVector[2];
			for (VSCalibrationPoint *point in pointsWithScreenCoordinates) {
				clickToPointVector[0] = coords.x - [point.screenX floatValue];
				clickToPointVector[1] = coords.y - [point.screenY floatValue];
				distanceFromClick = cblas_snrm2(2, clickToPointVector, 1);
				if (distanceFromClick < shortestDistanceFromClick) {
					pointToSelect = point;
					shortestDistanceFromClick = distanceFromClick;
				}
			}
		} else {
			pointToSelect = [pointsWithScreenCoordinates objectAtIndex:0];
		}
		if ([[pointsArrayController selectedObjects] count] > 0 && [[[pointsArrayController selectedObjects] objectAtIndex:0] isEqualTo:pointToSelect]) {		// if the point is already selected, deselect it
			[pointsArrayController setSelectedObjects:nil];
			[self refreshOverlay];
		} else {																														// otherwise, select the point
			[pointsArrayController setSelectedObjects:[NSArray arrayWithObject:pointToSelect]];
		}		
	}
}

- (void) handleOverlayRightClickInMeasureMode:(NSPoint)coords
{
	if ([overlayView.visibleScreenPoints count] > 0) {
		VSPoint *pointToSelect = nil;
		
		if ([overlayView.visibleScreenPoints count] > 1) {								// if there are 2+ points, find the one closest (smallest 2-norm) to the click
			float shortestDistanceFromClick = 1000000.0;								// initialize with an absurdly high number, so the first real click will be "closer"
			float distanceFromClick;
			float clickToPointVector[2];
			for (VSEventScreenPoint *screenPoint in overlayView.visibleScreenPoints) {
				clickToPointVector[0] = coords.x - [screenPoint.screenX floatValue];
				clickToPointVector[1] = coords.y - [screenPoint.screenY floatValue];
				distanceFromClick = cblas_snrm2(2, clickToPointVector, 1);
				if (distanceFromClick < shortestDistanceFromClick) {
					pointToSelect = screenPoint.point;
					shortestDistanceFromClick = distanceFromClick;
				}
			}
		} else {																		// There's only one visible screenPoint, must select its point.
			pointToSelect = [[overlayView.visibleScreenPoints anyObject] point];
		}
		if ([[self.videoClip.project.document.eventsPointsController selectedObjects] count] > 0 && [[[self.videoClip.project.document.eventsPointsController selectedObjects] objectAtIndex:0] isEqualTo:pointToSelect]) {		// if the point is already selected, deselect it
			[self.videoClip.project.document.eventsPointsController setSelectedObjects:nil];
		} else { // otherwise, select the point and its event and object
			VSTrackedObject *objectToSelect = [pointToSelect.trackedEvent.trackedObjects anyObject];
			VSTrackedObject *previouslySelectedObject = nil;
			if ([[self.videoClip.project.document.trackedObjectsController selectedObjects] count] > 0) {
				previouslySelectedObject = [[self.videoClip.project.document.trackedObjectsController selectedObjects] objectAtIndex:0];
			}
			if (previouslySelectedObject != nil && ![previouslySelectedObject isEqualTo:objectToSelect]) {	// If and only if we're selecting a new object, post a selection change notification for the object table.
				[[NSNotificationCenter defaultCenter] postNotificationName:NSTableViewSelectionIsChangingNotification object:self.videoClip.project.document.trackedObjectsController.mainTableView];
			}
			[self.videoClip.project.document.trackedObjectsController setSelectedObjects:[NSArray arrayWithObject:objectToSelect]];
			[self.videoClip.project.document.trackedEventsController setSelectedObjects:[NSArray arrayWithObject:pointToSelect.trackedEvent]];
			[self.videoClip.project.document.eventsPointsController setSelectedObjects:[NSArray arrayWithObject:pointToSelect]];
		}
	}
}

- (void) handleOverlayRightClickInAnnotateMode:(NSPoint)coords
{
	if ([overlayView.visibleAnnotations count] > 0) {
		VSAnnotation *annotationToSelect = nil;
		
		if ([overlayView.visibleAnnotations count] > 1) {								// if there are 2+ annotations, find the one closest (smallest 2-norm) to the click
			float shortestDistanceFromClick = 1000000.0;								// initialize with an absurdly high number, so the first real click will be "closer"
			float distanceFromClick;
			float clickToPointVector[2];
			for (VSAnnotation *annotation in overlayView.visibleAnnotations) {
				clickToPointVector[0] = coords.x - [annotation.screenX floatValue];
				clickToPointVector[1] = coords.y - [annotation.screenY floatValue];
				distanceFromClick = cblas_snrm2(2, clickToPointVector, 1);
				if (distanceFromClick < shortestDistanceFromClick) {
					annotationToSelect = annotation;
					shortestDistanceFromClick = distanceFromClick;
				}
			}
		} else {																		// There's only one visible annotation, must select it.
			annotationToSelect = [overlayView.visibleAnnotations anyObject];
		}
		if ([[self.videoClip.project.document.annotationsController selectedObjects] count] > 0 && [[[self.videoClip.project.document.annotationsController selectedObjects] objectAtIndex:0] isEqualTo:annotationToSelect]) {		// if the annotation is already selected, deselect it
			[[NSNotificationCenter defaultCenter] postNotificationName:NSTableViewSelectionIsChangingNotification object:self.videoClip.project.document.annotationsController.mainTableView];	
			[self.videoClip.project.document.annotationsController setSelectedObjects:nil];
		} else {																														// otherwise, select the point and its event and object
			[[NSNotificationCenter defaultCenter] postNotificationName:NSTableViewSelectionIsChangingNotification object:self.videoClip.project.document.annotationsController.mainTableView];
			[self.videoClip.project.document.annotationsController setSelectedObjects:[NSArray arrayWithObject:annotationToSelect]];
		}
	}
}


#pragma mark
#pragma mark Misc

- (void) refreshOverlay
{
	[overlayView display];
}

- (IBAction) resizeToVideoPercent:(id)sender;
{
	NSString *percentageStr = [[sender selectedItem] title];
	float sizeFactor = 1.0;
	if ([percentageStr isEqualToString:@"100%"]) {
		sizeFactor = 1.0;
	} else if ([percentageStr isEqualToString:@"67%"]) {
		sizeFactor = 0.67;
	} else if ([percentageStr isEqualToString:@"50%"]) {
		sizeFactor = 0.5;
	} else if ([percentageStr isEqualToString:@"33%"]) {
		sizeFactor = 0.33;
	}
	[self resizeVideoToFactor:sizeFactor];
}

- (void) resizeVideoToFactor:(float)sizeFactor
{
	NSSize newSize = NSMakeSize(sizeFactor*movieSize.width,sizeFactor*movieSize.height+26);
	NSSize minSize = [[self window] minSize];
	if (newSize.width < minSize.width) newSize.width = minSize.width;
	if (newSize.height < minSize.height) newSize.height = minSize.height;
	[[self window] setContentSize:newSize];
	[self refreshOverlay];
}

- (IBAction) setAsMaster:(id)sender
{	
	[self.videoClip setAsMaster];
	for (VSVideoClip *clip in self.videoClip.project.videoClips) {
        clip.syncIsLocked = [NSNumber numberWithBool:NO];
        [clip.windowController setMovieViewControllerVisible:YES];
    }
}

- (IBAction) lockSyncOffset:(id)sender
{
    NSButton *button = (NSButton *) sender;
	if ([button state] == NSOnState) {
        self.videoClip.syncIsLocked = [NSNumber numberWithBool:YES];
		[self setMovieViewControllerVisible:NO];
        [self.videoClip.project.masterClip.windowController setMovieViewControllerVisible:NO];
        [self.videoClip setSyncOffset];
        [self.videoClip.project.document.syncedPlaybackPanel orderFront:self];
	} else {
        self.videoClip.syncIsLocked = [NSNumber numberWithBool:FALSE];
        BOOL allClipsAreUnsynced = YES;
        for (VSVideoClip *clip in self.videoClip.project.videoClips) if ([clip.syncIsLocked boolValue]) allClipsAreUnsynced = NO;
        if (allClipsAreUnsynced) [self.videoClip.project.masterClip.windowController setMovieViewControllerVisible:YES];
		[self setMovieViewControllerVisible:YES];
        [self.videoClip.project.document.syncedPlaybackPanel close];
	}
}

- (void) setMovieViewControllerVisible:(BOOL)setting
{
    if (setting) {
		playerView.controlsStyle = AVPlayerViewControlsStyleFloating;
        playerView.showsFrameSteppingButtons = YES;
        [overlayWindow setIgnoresMouseEvents:TRUE];
    } else {
		playerView.controlsStyle = AVPlayerViewControlsStyleNone;
        [overlayWindow setIgnoresMouseEvents:FALSE];
    }
}

@end
