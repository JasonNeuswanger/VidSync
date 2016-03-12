/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
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
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) if ([clip respondsToSyncedControls]) [clip.windowController.playerView.player.currentItem stepByCount:1];
}

- (IBAction) stepBackwardAll:(id)sender
{
	for (VSVideoClip *clip in [self.project.videoClips allObjects]) if ([clip respondsToSyncedControls]) [clip.windowController.playerView.player.currentItem stepByCount:-1];
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
        for (VSVideoClip *clip in [self.project.videoClips allObjects]) if ([clip respondsToSyncedControls]) [clip.windowController.playerView.player.currentItem stepByCount:numFrames];
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
    } else {                            // tag = 4; playing backward at rate 2
        rateMultiplier = -1.0;
        whichRate = @"2";
	}
	float playRate = rateMultiplier * [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackRate%@",whichRate]] floatValue];
    CMTime newStopTime;
	int durationType = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackMode%@",whichRate]] floatValue];
	if (durationType == 1) {			// exact duration specified
		float exactDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackExactDuration%@",whichRate]] floatValue];
		newStopTime = [self stopTimeForDuration:exactDuration atRate:playRate];
	} else if (durationType == 2) {		// random duration in range specified
		float minDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackMinRandomDuration%@",whichRate]] floatValue];
		float maxDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackMaxRandomDuration%@",whichRate]] floatValue];
		float randomDuration = [UtilityFunctions randomFloatBetween:minDuration and:maxDuration];
		newStopTime = [self stopTimeForDuration:randomDuration atRate:playRate];
	}
    [self setAllVideoRates:playRate];   // Because videoRateDidChange wipes stopTime clean, I have to set it after triggering this rate change, but still calculate it above before playback begins
    if (durationType == 1 || durationType == 2) {
        stopTime = newStopTime;
    }
}

- (IBAction) instantReplay:(id)sender
{
    float exactDuration, playRate;
    if ([sender tag] == 3) {    // Using the main replay button, use rate 1 for 2 seconds.
        exactDuration = 2.0f;
        playRate = 1.0f;
    } else { // Using one of the advanced playback buttons; figure out which on.
        NSString *whichRate = [NSString stringWithFormat:@"%ld",(long)[sender tag]];
        [[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithInt:1] forKey:[NSString stringWithFormat:@"advancedPlaybackMode%@",whichRate]];
        exactDuration = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackExactDuration%@",whichRate]] floatValue];
        playRate = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:[NSString stringWithFormat:@"advancedPlaybackRate%@",whichRate]] floatValue];
    }
    CMTime newStopTime = [self currentMasterTime];
    CMTime stepTime = CMTimeMakeWithSeconds(-exactDuration,newStopTime.timescale);
    [self goToMasterTime:CMTimeAdd(newStopTime,stepTime)];
    [self setAllVideoRates:playRate];
    stopTimeComparison = NSOrderedAscending; // Because we're always playing forward in this case
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (exactDuration/2.0) * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        // Setting the video rates resets the stop time to 0, so any user playback input interrupts a "play until time" sequence. Therefore we
        // set the new stopTime after setting the video rates, and on a bit of a delay, in case the rateDidChange notification doesn't fire immediately.
        stopTime = newStopTime;
    });
}

- (CMTime) stopTimeForDuration:(float)duration atRate:(float)rate
{
    CMTime newStopTime;
    int32_t myTimeScale = (int32_t) [[self.project.masterClip timeScale] longValue];
    CMTime durationScaled = CMTimeMakeWithSeconds(duration,myTimeScale);
    if (rate > 0) {
		newStopTime = CMTimeAdd([self currentMasterTime],durationScaled);
		stopTimeComparison = NSOrderedAscending;		// playing forward; stop when currentMasterTime > stopTime
	} else {
		newStopTime = CMTimeSubtract([self currentMasterTime],durationScaled);
		stopTimeComparison = NSOrderedDescending;		// playing backward; stop when currentMasterTime < stopTime
	}
    return newStopTime;
}

- (void) checkForStopAtCurrentTime		// note: movieRateDidChange notification changes stopTime to nil, so user-generated rate changes interrupt a play-until-stopped command
{
	// Only gets called from playbackLoopActions if video is playing and stopTime is not nil
	NSComparisonResult currentTimeComparedWithStopTime = CMTimeCompare(stopTime,[self currentMasterTime]);  // Should return ascending if stoptime < masterTime, descending if masterTime > stopTime
    if (currentTimeComparedWithStopTime == stopTimeComparison || currentTimeComparedWithStopTime == NSOrderedSame) {
        CMTime newStopTime = stopTime;  // save this here because it's set to null by a notification by the rate change in the next line
		[self setAllVideoRates:0.0];
		[self goToMasterTime:newStopTime];
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
		if (!clip.isMasterClipOf && [clip respondsToSyncedControls]) {	// if the clip is sync-locked, and isn't the master clip, then sync it
			CMTime offset = [UtilityFunctions CMTimeFromString:clip.syncOffset];
			[clip.windowController.playerView.player seekToTime:CMTimeSubtract(currentMasterTime,offset) toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero];
		}
		[clip.windowController refreshOverlay];	// refresh the overlay whenever the time changes
	}
}

- (CMTime) currentMasterTime
{
    // Sometimes the player's time separates from the video's timescale by minute amounts like 1/3000 second. The conversion here prevents that quirk from messing up overlays of points recorded at the current time.
    CMTime rawCurrentTime = [self.project.masterClip.windowController.playerView.player currentTime];
	return CMTimeConvertScale(rawCurrentTime,[[self.project.masterClip timeScale] longValue],kCMTimeRoundingMethod_RoundHalfAwayFromZero);
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
        if ([clip respondsToSyncedControls]) {
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
        [playBackwardButton setAction:@selector(pauseAll:)];
        [playForwardAtRate1Button setAction:@selector(pauseAll:)];
        [playBackwardAtRate1Button setAction:@selector(pauseAll:)];
        [playForwardAtRate2Button setAction:@selector(pauseAll:)];
        [playBackwardAtRate2Button setAction:@selector(pauseAll:)];
	} else {	// masterClip is paused; check if all movies are paused, and if so, set simultaneous playback button text and action to "play"
        [playOrPauseButton setCustomTitle:@"\uf04b"];
        [playOrPauseButton setAction:@selector(playAll:)];
        [playBackwardButton setAction:@selector(playAllBackward:)];
        [playForwardAtRate1Button setAction:@selector(advancedPlayAll:)];
        [playBackwardAtRate1Button setAction:@selector(advancedPlayAll:)];
        [playForwardAtRate2Button setAction:@selector(advancedPlayAll:)];
        [playBackwardAtRate2Button setAction:@selector(advancedPlayAll:)];
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
