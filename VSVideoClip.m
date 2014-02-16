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

- (void) setMasterControls
{
	if (self.isMasterClipOf == self.project) {
		self.masterButtonText = @"Is Master Clip";
		[self.windowController setMovieViewControllerVisible:YES];
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
	return [NSNumber numberWithInt:self.windowController.videoTrack.naturalTimeScale];	// Will return 2997 for all my videos, but I don't want to hard-code that anywhere.
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
	self.syncIsLocked = [NSNumber numberWithBool:YES];
	[self setMasterControls];
	[oldMasterClip setMasterControls];
}

- (void) setSyncOffset
{
	CMTime currentMasterTime = [self.project.document currentMasterTime];
	CMTime currentTime = [self.windowController.playerView.player currentTime];
	self.syncOffset = [UtilityFunctions CMStringFromTime:CMTimeSubtract(currentMasterTime,currentTime)];
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
