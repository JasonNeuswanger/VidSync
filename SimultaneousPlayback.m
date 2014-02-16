//
//  SimultaneousPlayback.m
//  VidSync
//
//  Created by Jason Neuswanger on 11/10/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VidSyncDocument.h"

@implementation VidSyncDocument (SimultaneousPlayback)

- (void) playbackLoopActions // This is called by a timer every 0.03 seconds.  If the masterClip is playing, refresh all overlays. 
{
	if (project.masterClip.windowController.playerView.player.rate != 0.0) {
		for (VSVideoClip *videoClip in self.project.videoClips) [videoClip.windowController refreshOverlay];
		[eventsPointsController rearrangeObjects];
		[self updateMasterTimeDisplay];
		if (!CMTIME_IS_INDEFINITE(stopTime)) [self checkForStopAtCurrentTime];
	}
}

- (void) updateMasterTimeDisplay
{
	[masterTimeDisplay setStringValue:[UtilityFunctions CMStringFromTime:[self currentMasterTime]]];
}

#pragma mark
#pragma mark Simple Playback 

- (IBAction) playAll:(id)sender
{
	[self setAllVideoRates:1.0];
}

- (IBAction) pauseAll:(id)sender
{
	[self setAllVideoRates:0.0];
	[self reSync];
}

- (IBAction) playAllBackward:(id)sender
{
	[self setAllVideoRates:-1.0];
}

- (IBAction) fastForwardAll:(id)sender
{
	[self setAllVideoRates:3.0];
}

- (IBAction) fastBackwardAll:(id)sender
{
	[self setAllVideoRates:-3.0];
}

- (IBAction) stepForwardAll:(id)sender
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) [clip.windowController.playerView.player.currentItem stepByCount:1];
}

- (IBAction) stepBackwardAll:(id)sender
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) [clip.windowController.playerView.player.currentItem stepByCount:-1];
}

#pragma mark
#pragma mark Advanced Playback 

- (IBAction) advancedStepForwardAll:(id)sender
{
	// These step functions still don't work on just the right timescale all the time for all values of numFrames.  For example, with numFrames = 5, it works fine for a few runs and then 
	// subtracts three from the timeValue.  Deal with it later.
	int numFrames = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackStepFrames"] intValue];
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) [clip.windowController.playerView.player.currentItem stepByCount:numFrames];
}

- (IBAction) advancedStepBackwardAll:(id)sender
{
	int numFrames = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackStepFrames"] intValue];
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) [clip.windowController.playerView.player.currentItem stepByCount:-numFrames];
}

- (IBAction) advancedPlayAll:(id)sender
{
	float rateMultiplier;
	if ([sender tag] == 1) {	// playing forward
		rateMultiplier = 1.0;
	} else {					// [sender tag] == 0, playing backward
		rateMultiplier = -1.0;
	}
	float playRate = rateMultiplier * [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackRate1"] floatValue];
	[self setAllVideoRates:playRate];
	int durationType = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackDurationType"] floatValue];
	if (durationType == 1) {			// exact duration specified
		float duration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackExactDuration"] floatValue];
		[self setStopTimeForDuration:duration atRate:playRate];
	} else if (durationType == 2) {		// random duration in range specified
		float minDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackMinRandomDuration"] floatValue];
		float maxDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackMaxRandomDuration"] floatValue];
		float randomDuration = [UtilityFunctions randomFloatBetween:minDuration and:maxDuration];
		[self setStopTimeForDuration:randomDuration atRate:playRate];
	}
}

- (void) setStopTimeForDuration:(float)duration atRate:(float)rate
{
    int32_t myTimeScale = (int32_t) [[self.project.masterClip timeScale] longValue];
    CMTime durationScaled = CMTimeMakeWithSeconds(duration,myTimeScale);
    if (rate > 0) {
		stopTime = CMTimeSubtract([self currentMasterTime],durationScaled);
		stopTimeComparison = NSOrderedAscending;		// playing forward; stop when currentMasterTime > stopTime
	} else {
		stopTime = CMTimeSubtract([self currentMasterTime],durationScaled);
		stopTimeComparison = NSOrderedDescending;		// playing backward; stop when currentMasterTime < stopTime
	}
}

- (void) checkForStopAtCurrentTime		// note: movieTimeDidChange notification changes stopTime to nil
{
	// Only gets called from playbackLoopActions if video is playing and stopTime is not nil
	NSComparisonResult currentTimeComparedWithStopTime = CMTimeCompare(stopTime,[self currentMasterTime]);
	if (currentTimeComparedWithStopTime == stopTimeComparison || currentTimeComparedWithStopTime == NSOrderedSame) {
		[self setAllVideoRates:0.0];
		[self goToMasterTime:stopTime];
	}
}

#pragma mark
#pragma mark Bookmark

- (IBAction) setBookmark:(id)sender
{
	bookmarkTime = [self currentMasterTime];
	[bookmarkTextLabel setStringValue:CFBridgingRelease(CMTimeCopyDescription(kCFAllocatorDefault,bookmarkTime))];
	[goToBookmarkButton setEnabled:YES];
}

- (IBAction) goToBookmark:(id)sender
{
	[self goToMasterTime:bookmarkTime];	
}

#pragma mark
#pragma mark Utility Functions for Playback

- (void) reSync
{	
	CMTime currentMasterTime = [self currentMasterTime];
	self.project.currentTimecode = [UtilityFunctions CMStringFromTime:currentMasterTime];
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) {
		if (!clip.isMasterClipOf && [clip.syncIsLocked boolValue]) {	// if the clip is sync-locked, and isn't the master clip, then sync it
			CMTime offset = [UtilityFunctions CMTimeFromString:clip.syncOffset];	// correct a QuickTime bug that converts negative offsets as strings to positiveo ones as qttime
			[clip.windowController.playerView.player seekToTime:CMTimeSubtract(currentMasterTime,offset) toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero];
		}
		[clip.windowController refreshOverlay];	// refresh the overlay whenever the time changes
	}
}

- (CMTime) currentMasterTime
{
	return [self.project.masterClip.windowController.playerView.player currentTime];
}

- (void) goToMasterTime:(CMTime)time
{
	[self.project.masterClip.windowController.playerView.player seekToTime:time toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero];
	[self reSync];
}

- (BOOL) currentMasterTimeIs:(CMTime)time		// returns YES if 'time' is equal to the current master time, NO otherwise
{
	CMTime masterTime = [self.project.masterClip.windowController.playerView.player currentTime];
	return (CMTimeCompare(time,masterTime) == NSOrderedSame);
}

- (void) setAllVideoRates:(float)rate
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) {
        if (fabs(rate) > 0.0f) {
            clip.windowController.playerView.player.rate = rate;
        } else {
            clip.windowController.playerView.player.rate = 0.0f;
        }
        
    }
}


#pragma mark
#pragma mark Notification Handlers

- (void) movieRateDidChange	// makes the playOrPauseButton behave so that it pauses if anything is playing, and plays only if everything is paused
{
	if (self.project.masterClip.windowController.playerView.player.rate != 0.0) {	// some movie is playing; change simultaneous playback button text and action to "pause"
		[playOrPauseButton setTitle:@"Pause"];
		[playOrPauseButton setAction:@selector(pauseAll:)];
	} else {	// some movie is paused; check if all movies are paused, and if so, set simultaneous playback button text and action to "play"
		BOOL allArePaused = YES;
		for (VSVideoClip *clip in [self.project.videoClips allObjects]) {
			if (clip.windowController.playerView.player.rate != 0.0) {
				allArePaused = NO;
			}
		}
		if (allArePaused) {
			[playOrPauseButton setTitle:@"Play"];
			[playOrPauseButton setAction:@selector(playAll:)];			
		}
	}
}

- (void) movieTimeDidChange:(NSNotification *)notification
{
	// Only process these time change notifications for the masterClip.  Otherwise, reSync forces another movieTimeDidChange and there's an infinite loop that slows the program to a crawl.
	if (self.project.masterClip != nil) {
		if ([[notification object] isEqualTo:self.project.masterClip.windowController.playerView.player.currentItem]) {
			[self reSync];
			[eventsPointsController rearrangeObjects];
			[masterTimeDisplay setStringValue:[UtilityFunctions CMStringFromTime:[self currentMasterTime]]];
			stopTime = kCMTimeIndefinite;	// If the user does anything manually to the video while it's playing, it overrides and wipes out an advanced playback stopTime if one was set.
		}
	}
}

@end
