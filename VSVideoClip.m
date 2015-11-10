//
//  VSVideoClip.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/23/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VSVideoClip.h"

@implementation VSVideoClip

@dynamic clipName;
@dynamic fileName;
@dynamic syncOffset;
@dynamic windowFrame;
@dynamic calibration;
@dynamic project;
@dynamic isMasterClipOf;
@dynamic syncIsLocked;
@dynamic eventScreenPoints;
@dynamic hintLines;
@dynamic annotations;
@dynamic muted;

@synthesize windowController;
@synthesize masterButtonText;

- (void) relocateClip
{
    __block NSOpenPanel *movieOpenPanel = [NSOpenPanel openPanel];
    NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"movieOpenDirectory"];
    BOOL directoryExists;
    if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) {
        [movieOpenPanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
    }
    [movieOpenPanel setMessage:[NSString stringWithFormat:@"Select the location of a valid video file for clip %@ (the previous file location was %@ ",self.clipName,self.fileName]];
    [movieOpenPanel setCanChooseFiles:YES];
    [movieOpenPanel setCanChooseDirectories:NO];
    [movieOpenPanel setAllowsMultipleSelection:NO];
    [movieOpenPanel beginSheetModalForWindow:[self.project.document mainWindow] completionHandler:^(NSModalResponse returnCode) {
        if (returnCode == NSFileHandlingPanelOKButton) {
            NSString *oldFileName = self.fileName;  // save the old value in case the new one is invalid
            self.fileName = [[[movieOpenPanel URLs] objectAtIndex:0] path];
            [[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[[[[movieOpenPanel URLs] objectAtIndex:0] path] stringByDeletingLastPathComponent] forKey:@"movieOpenDirectory"];
            VideoWindowController *__weak oldWindowController = self.windowController;
            VideoWindowController *__strong newWindowController = [[VideoWindowController alloc] initWithVideoClip:self inManagedObjectContext:self.managedObjectContext]; // is self.windowcontroller
            if (newWindowController != nil) {
                [self.project.document observeWindowControllerVideoRate:newWindowController];
                //  seems it's being observed by a keyValueObservance that traces back to the document
                [oldWindowController removeObserver:self.project.document forKeyPath:@"playerView.player.rate"];
                [self.project.document removeWindowController:oldWindowController];
                [oldWindowController close];
                [self.project.document addWindowController:newWindowController];
            } else {
                self.fileName = oldFileName;    // restore the old fine name if the new one was invalid
            }
        }
    }];
}

- (BOOL) respondsToSyncedControls
{
    BOOL showAdvancedControlsWithOnlyMasterClip = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"showAdvancedControlsWithOnlyMasterClip"] boolValue];
    
    return ([self.syncIsLocked boolValue] || (showAdvancedControlsWithOnlyMasterClip && [self.isMasterClipOf isEqualTo:self.project] && [self.project.videoClips count] == 1));
}

- (NSNumber *) timeScale
{
	return [NSNumber numberWithInt:self.windowController.videoTrack.naturalTimeScale];
}

- (float)frameRate {
	if (frameRate) return frameRate;
    return self.windowController.videoTrack.nominalFrameRate;
}


- (NSString *) clipLength
{
	return [UtilityFunctions CMStringFromTime:self.windowController.videoTrack.asset.duration];
}

- (NSString *) clipResolution
{
	CGSize rawClipResolution = self.windowController.videoTrack.naturalSize;
	return [NSString stringWithFormat:@"%dx%d",(int) rawClipResolution.width,(int) rawClipResolution.height];
}

- (double) clipHeight  // pixel height of the video clip
{
	CGSize rawClipResolution = self.windowController.videoTrack.naturalSize;
	return rawClipResolution.height;
}

- (double) clipWidth  // pixel width of the video clip
{
	CGSize rawClipResolution = self.windowController.videoTrack.naturalSize;
	return rawClipResolution.width;
}

- (BOOL) isAtCalibrationTime
{
    NSString *currentMasterTimeString = [self.project.document currentMasterTimeString];
    CMTime currentMasterTime = [self.project.document currentMasterTime];
	if ([UtilityFunctions timeString:self.project.calibrationTimecode isEqualToTimeString:currentMasterTimeString]) {   // If the master clip is at the calibration timecode
		CMTime currentTime = [windowController.playerView.player.currentItem currentTime];
        CMTime syncOffset = [UtilityFunctions CMTimeFromString:self.syncOffset];
        return [UtilityFunctions time:currentMasterTime isEqualToTime:CMTimeAdd(currentTime,syncOffset)];   // Return whether or not this clip is also at the calibration timecode
	} else {
		return NO;                                          // If the master clip isn't at the calibration timecode, nothing counts as being there
	}
}

- (BOOL) isCalibrated
{
	return ([self.calibration frontIsCalibrated] && [self.calibration backIsCalibrated]);
}

- (NSXMLNode *) representationAsXMLNode	// very partial implementation just to get me onto distortion lines ASAP, although the idea of flattening the calibration with the clip in the XML may remain
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"videoClip"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.clipName]];	
    [mainElement addChild:[self.calibration representationAsXMLNode]];
    for (VSAnnotation *annotation in self.annotations) [mainElement addChild:[annotation representationAsXMLNode]];
	return mainElement;
}

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath
// This is called by VideoWindowController to remove itself as an observer from the VSVideoClip.
// Doing this in the other way (removing the observers in the VSVideoClip results in maddeningly hard-to-trace crashes when the program closes, because
// the WindowController is deallocated first, and it's sent messages by the observers while deallocated before the VSVideoClip could be deallocated to kill the observers.
{
    if (observer != nil) {
        @try {
            [self removeObserver:observer forKeyPath:keyPath];
        } @catch (id exception) {
            NSLog(@"Error removing observer for keypath %@ from VSVideoClip: %@",keyPath,(NSException *)exception);
        }
    }
}

@end
