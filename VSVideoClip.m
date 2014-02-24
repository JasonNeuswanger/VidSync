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

@synthesize windowController;
@synthesize masterButtonText;

- (void) relocateClip
{
    __block NSOpenPanel *movieOpenPanel = [NSOpenPanel openPanel];
    [movieOpenPanel setMessage:[NSString stringWithFormat:@"Select the location of a valid video file for clip %@ (the previous file location was %@ ",self.clipName,self.fileName]];
    [movieOpenPanel setCanChooseFiles:YES];
    [movieOpenPanel setCanChooseDirectories:NO];
    [movieOpenPanel setAllowsMultipleSelection:NO];
    [movieOpenPanel beginSheetModalForWindow:[self.project.document mainWindow] completionHandler:^(NSModalResponse returnCode) {
        if (returnCode == NSFileHandlingPanelOKButton) {
            NSString *oldFileName = self.fileName;  // save the old value in case the new one is invalid
            self.fileName = [[[movieOpenPanel URLs] objectAtIndex:0] path];
            VideoWindowController *newWindowController = [[VideoWindowController alloc] initWithVideoClip:self inManagedObjectContext:self.managedObjectContext];
            if (newWindowController != nil) {
                NSWindowController *oldWindowController = self.windowController;
                self.windowController = newWindowController;
                if (self.windowController != nil) {     // If there's already a valid file with a window and we're replacing it, remove the old one first
                    NSLog(@"Should be removing the old window controller %@ and closing its window %@",oldWindowController,[self.windowController window]);
                    [[oldWindowController window] setReleasedWhenClosed:YES];
                    [self.project.document removeWindowController:oldWindowController];
                    [oldWindowController close];
                }
            [self.project.document addWindowController:newWindowController];
            } else {
                self.fileName = oldFileName;    // restore the old fine name if the new one was invalid
            }
        }
    }];
}

- (void) setMasterControls
{
	if (self.isMasterClipOf == self.project) {
		self.masterButtonText = @"Is Master Clip";
        self.syncIsLocked = [NSNumber numberWithBool:FALSE];    // In the the new Mavericks version, syncIsLocked is always false for the master clip. This adjusts legacy files accordingly when they're loaded.
        BOOL allClipsAreUnsynced = YES;
        for (VSVideoClip *clip in self.project.videoClips) if ([clip.syncIsLocked boolValue]) allClipsAreUnsynced = FALSE;
        if (allClipsAreUnsynced) {
            [self.project.masterClip.windowController setMovieViewControllerVisible:YES];
        } else {
            [self.project.masterClip.windowController setMovieViewControllerVisible:NO];
        }
	} else {
		self.masterButtonText = @"Set as Master";
        if ([self.syncIsLocked boolValue]) {
            [self.windowController setMovieViewControllerVisible:NO];
        } else {
            [self.windowController setMovieViewControllerVisible:YES];
        }
	}
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

- (void) setAsMaster 
{
	VSVideoClip *oldMasterClip = self.project.masterClip;
	self.project.masterClip = self;
	self.syncOffset = [UtilityFunctions CMStringFromTime:CMTimeMake(0,[[self timeScale] floatValue])];	// set syncOffset to string for 0; must use self.syncOffset rather than syncOffset for key-value observing to update interface
//	self.syncIsLocked = [NSNumber numberWithBool:YES];
	[self setMasterControls];
	[oldMasterClip setMasterControls];
}

- (void) setSyncOffset
{
	CMTime currentMasterTime = [self.project.document currentMasterTime];
	CMTime currentClipTime = [self.windowController.playerView.player currentTime];
	self.syncOffset = [UtilityFunctions CMStringFromTime:CMTimeSubtract(currentMasterTime,currentClipTime)];
}

- (BOOL) isAtCalibrationTime
{
    // This function might not work right if the videos use different framerates.
	CMTime currentMasterTime = [self.project.masterClip.windowController.playerView.player.currentItem currentTime];
	if (CMTimeCompare(currentMasterTime,[UtilityFunctions CMTimeFromString:self.project.calibrationTimecode]) == NSOrderedSame) {
		CMTime currentTime = [windowController.playerView.player.currentItem currentTime];
		if (CMTimeCompare(currentMasterTime,CMTimeAdd(currentTime,[UtilityFunctions CMTimeFromString:self.syncOffset])) == NSOrderedSame) {
			return YES;
		} else {
			return NO;
		}
	} else {
		return NO;
	}
}

- (BOOL) isCalibrated
{
	return (self.calibration.matrixQuadratBackToScreen != nil && self.calibration.matrixQuadratFrontToScreen != nil && self.calibration.matrixScreenToQuadratFront != nil && self.calibration.matrixScreenToQuadratBack != nil);
}

- (NSXMLNode *) representationAsXMLNode	// very partial implementation just to get me onto distortion lines ASAP, although the idea of flattening the calibration with the clip in the XML may remain
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"videoClip"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.clipName]];	
    [mainElement addChild:[self.calibration representationAsXMLNode]];
	return mainElement;
}

@end
