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
                [self.project.document removeWindowController:oldWindowController];
                [oldWindowController close];
                [self.project.document addWindowController:newWindowController];
            } else {
                self.fileName = oldFileName;    // restore the old fine name if the new one was invalid
            }
        }
    }];
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
	return (self.calibration.matrixQuadratBackToScreen != nil && self.calibration.matrixQuadratFrontToScreen != nil && self.calibration.matrixScreenToQuadratFront != nil && self.calibration.matrixScreenToQuadratBack != nil);
}

- (NSXMLNode *) representationAsXMLNode	// very partial implementation just to get me onto distortion lines ASAP, although the idea of flattening the calibration with the clip in the XML may remain
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"videoClip"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.clipName]];	
    [mainElement addChild:[self.calibration representationAsXMLNode]];
	return mainElement;
}

- (void) dealloc
{
    NSLog(@"deallocing VSVideoClip");
    if (windowController != nil) {
        @try {
            [self removeObserver:windowController forKeyPath:@"syncIsLocked"];
            [self removeObserver:windowController forKeyPath:@"syncOffset"];
            [self removeObserver:windowController forKeyPath:@"isMasterClipOf"];
        } @catch (id exception) {
        }
    }
}

@end
