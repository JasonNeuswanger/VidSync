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
    
    // It seems to not be calling this function at all while the button is pressed down
    
	if (project.masterClip.windowController != nil && project.masterClip.windowController.playerView.player.rate != 0.0) {
		for (VSVideoClip *videoClip in self.project.videoClips) [videoClip.windowController refreshOverlay];
		[eventsPointsController rearrangeObjects];
		[self updateMasterTimeDisplay];
		if (!CMTIME_IS_INDEFINITE(stopTime)) [self checkForStopAtCurrentTime];
	}
}

- (void) updateMasterTimeDisplay // also updates the synced playback scrubber
{
    if (self.project.masterClip.windowController != nil) {
        [masterTimeDisplay setStringValue:[self currentMasterTimeString]];
        
        CMTimeRange masterTimeRange = [[[self.project.masterClip.windowController.videoAsset tracksWithMediaType:AVMediaTypeVideo] firstObject] timeRange];
        CMTimeRange sliderRange = CMTimeRangeMake(CMTimeMake(0,scrubberMaxTime),CMTimeMake(scrubberMaxTime,scrubberMaxTime));
        CMTime sliderTimeToSet = CMTimeMapTimeFromRangeToRange([self currentMasterTime],masterTimeRange,sliderRange);
        
        double newSliderTime = (double) sliderTimeToSet.value;
        [syncedPlaybackScrubber setDoubleValue:newSliderTime];
    }

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

- (IBAction) stepForwardAll:(id)sender
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) if ([clip.syncIsLocked boolValue]) [clip.windowController.playerView.player.currentItem stepByCount:1];
}

- (IBAction) stepBackwardAll:(id)sender
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) if ([clip.syncIsLocked boolValue]) [clip.windowController.playerView.player.currentItem stepByCount:-1];
}

#pragma mark
#pragma mark Advanced Playback

- (IBAction) advancedStepAll:(id)sender
{
    NSString *stepUnits = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackStepUnits"];
	double stepAmount = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackStepAmount"] doubleValue];
    BOOL isForward = ([sender tag] == 2);   // otherwise it's backward, [sender tag] == 1
    if ([stepUnits isEqualToString:@"frames"]) {
        int numFrames = (isForward) ? roundf(stepAmount) : -roundf(stepAmount);
        for (VSVideoClip *clip in [self.project.videoClips allObjects]) if ([clip.syncIsLocked boolValue]) [clip.windowController.playerView.player.currentItem stepByCount:numFrames];
    } else {
        double stepUnitFactor = ([stepUnits isEqualToString:@"seconds"]) ? 1.0 : 60.0;  // if not "seconds," must be "minutes"
        double directionFactor = (isForward) ? 1.0 : -1.0;
        CMTime masterTime = [self currentMasterTime];
        CMTime stepTime = CMTimeMakeWithSeconds(stepAmount*stepUnitFactor*directionFactor,masterTime.timescale);
        [self goToMasterTime:CMTimeAdd(masterTime,stepTime)];
    }
}

- (IBAction) advancedPlayAll:(id)sender
{
	float rateMultiplier;
    NSString *whichRate;
	if ([sender tag] == 1) {            // playing forward at rate 1
		rateMultiplier = 1.0;
        whichRate = @"1";
	} else if ([sender tag] == 2) {		// playing backward at rate 1
		rateMultiplier = -1.0;
        whichRate = @"1";
	} else if ([sender tag] == 3) {		// playing forward at rate 2
		rateMultiplier = 1.0;
        whichRate = @"2";
    } else {                            // playing backward at rate 2
        rateMultiplier = -1.0;
        whichRate = @"2";
	}
	float playRate = rateMultiplier * [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackRate%@",whichRate]] floatValue];
	[self setAllVideoRates:playRate];
	int durationType = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackMode%@",whichRate]] floatValue];
	if (durationType == 1) {			// exact duration specified
		float exactDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackExactDuration%@",whichRate]] floatValue];
		[self setStopTimeForDuration:exactDuration atRate:playRate];
	} else if (durationType == 2) {		// random duration in range specified
		float minDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackMinRandomDuration%@",whichRate]] floatValue];
		float maxDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackMaxRandomDuration%@",whichRate]] floatValue];
		float randomDuration = [UtilityFunctions randomFloatBetween:minDuration and:maxDuration];
		[self setStopTimeForDuration:randomDuration atRate:playRate];
	}
}

- (void) setStopTimeForDuration:(float)duration atRate:(float)rate
{
    int32_t myTimeScale = (int32_t) [[self.project.masterClip timeScale] longValue];
    CMTime durationScaled = CMTimeMakeWithSeconds(duration,myTimeScale);
    if (rate > 0) {
		stopTime = CMTimeAdd([self currentMasterTime],durationScaled);
		stopTimeComparison = NSOrderedAscending;		// playing forward; stop when currentMasterTime > stopTime
	} else {
		stopTime = CMTimeSubtract([self currentMasterTime],durationScaled);
		stopTimeComparison = NSOrderedDescending;		// playing backward; stop when currentMasterTime < stopTime
	}
}

- (void) checkForStopAtCurrentTime		// note: movieRateDidChange notification changes stopTime to nil, so user-generated rate changes interrupt a play-until-stopped command
{
	// Only gets called from playbackLoopActions if video is playing and stopTime is not nil
	NSComparisonResult currentTimeComparedWithStopTime = CMTimeCompare(stopTime,[self currentMasterTime]);  // Should return ascending if stoptime < masterTime, descending if masterTime > stopTime
    if (currentTimeComparedWithStopTime == stopTimeComparison || currentTimeComparedWithStopTime == NSOrderedSame) {
		[self setAllVideoRates:0.0];
		[self goToMasterTime:stopTime];
	}
}

#pragma mark
#pragma mark Bookmark

- (IBAction) setBookmark:(id)sender
{
    if ([sender tag] == 1) {
        bookmarkTime1 = [self currentMasterTime];
        self.bookmarkIsSet1 = YES;
    } else if ([sender tag] == 2) {
        bookmarkTime2 = [self currentMasterTime];
        self.bookmarkIsSet2 = YES;
    }
}

- (IBAction) goToBookmark:(id)sender
{
    if ([sender tag] == 1 && self.bookmarkIsSet1) {
        [self goToMasterTime:bookmarkTime1];
    } else if ([sender tag] == 2 && self.bookmarkIsSet2) {
        [self goToMasterTime:bookmarkTime2];
    }
}

#pragma mark
#pragma mark Utility Functions for Playback

- (void) reSync
{	
	CMTime currentMasterTime = [self currentMasterTime];
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) {
		if (!clip.isMasterClipOf && [clip.syncIsLocked boolValue]) {	// if the clip is sync-locked, and isn't the master clip, then sync it
			CMTime offset = [UtilityFunctions CMTimeFromString:clip.syncOffset];
			[clip.windowController.playerView.player seekToTime:CMTimeSubtract(currentMasterTime,offset) toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero];
		}
		[clip.windowController refreshOverlay];	// refresh the overlay whenever the time changes
	}
}

- (CMTime) currentMasterTime
{
	return [self.project.masterClip.windowController.playerView.player currentTime];
}

- (NSString *) currentMasterTimeString
{
    return [UtilityFunctions CMStringFromTime:[self currentMasterTime] onScale:[[self.project.masterClip timeScale] longValue]];
}

- (void) goToMasterTime:(CMTime)time
{
	[self.project.masterClip.windowController.playerView.player seekToTime:time toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero];
	[self reSync];
}

- (BOOL) currentMasterTimeIs:(CMTime)time		// returns YES if 'time' is equal to the current master time, NO otherwise
{
	CMTime masterTime = [self.project.masterClip.windowController.playerView.player currentTime];
	return [UtilityFunctions time:time isEqualToTime:masterTime];
}

- (void) setAllVideoRates:(float)rate
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) {
        if ([clip.syncIsLocked boolValue]) {
            if (fabs(rate) > 0.0f) {
                clip.windowController.playerView.player.rate = rate;
            } else {
                clip.windowController.playerView.player.rate = 0.0f;
            }
        }
    }
}

- (IBAction) setTimeFromScrubber:(id)sender
{
    NSSlider *slider = (NSSlider *)sender;
    CMTimeRange masterTimeRange = [[[self.project.masterClip.windowController.videoAsset tracksWithMediaType:AVMediaTypeVideo] firstObject] timeRange];
    CMTime newTimeOnSliderScale = CMTimeMake(round([slider doubleValue]),scrubberMaxTime);
    CMTimeRange sliderRange = CMTimeRangeMake(CMTimeMake(0,scrubberMaxTime),CMTimeMake(scrubberMaxTime,scrubberMaxTime));
    CMTime timeToSet = CMTimeMapTimeFromRangeToRange(newTimeOnSliderScale,sliderRange,masterTimeRange);
    [self goToMasterTime:timeToSet];
}


#pragma mark
#pragma mark Notification Handlers

- (void) movieRateDidChange	// makes the playOrPauseButton behave so that it pauses if the masterClip is playing, and plays only if the masterClip is paused. this function is only called for masterClip rate changes
{
	if (fabs(self.project.masterClip.windowController.playerView.player.rate) > 0.0f) {	// masterClip is playing; change simultaneous playback button text and action to "pause"
        [playOrPauseButton setCustomTitle:@"\uf04c"];
		[playOrPauseButton setAction:@selector(pauseAll:)];
	} else {	// masterClip is paused; check if all movies are paused, and if so, set simultaneous playback button text and action to "play"
        [playOrPauseButton setCustomTitle:@"\uf04b"];
        [playOrPauseButton setAction:@selector(playAll:)];
        
	}
    stopTime = kCMTimeIndefinite;	// If the user does anything manually to the video while it's playing, it overrides and wipes out an advanced playback stopTime if one was set.
}

- (void) movieTimeDidChange:(NSNotification *)notification
{
	// Only process these time change notifications for the masterClip.  Otherwise, reSync forces another movieTimeDidChange and there's an infinite loop that slows the program to a crawl.
	if (self.project.masterClip != nil) {
		if ([[notification object] isEqualTo:self.project.masterClip.windowController.playerView.player.currentItem]) {
            self.project.currentTimecode = [self currentMasterTimeString];
			[self reSync];
			[eventsPointsController rearrangeObjects];
            [self updateMasterTimeDisplay];
		}
	}
}

@end
