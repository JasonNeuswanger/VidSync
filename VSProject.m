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


#import "VSProject.h"


@implementation VSProject

@dynamic name;
@dynamic notes;
@dynamic currentTimecode;
@dynamic calibrationTimecode;
@dynamic dateCreated;
@dynamic dateLastSaved;
@dynamic masterClip;
@dynamic videoClips;
@dynamic useIterativeTriangulation;
@dynamic trackedObjectTypes;
@dynamic trackedEventTypes;
@dynamic trackedObjects;
@dynamic trackedEvents;

@dynamic exportPathForData;
@dynamic exportClipSelectedClipName;
@dynamic capturePathForMovies;
@dynamic capturePathForStills;
@dynamic movieCaptureStartTime;
@dynamic movieCaptureEndTime;
@dynamic distortionDisplayMode;
@dynamic updatedSinceLastExport;

@synthesize document;
@synthesize frameRateWarning;

- (void) updateFrameRateWarning
{
	// Clips whose frame rates disagree cannot be synchronized to better than the beat between them, and the
	// sub-frame offset between the two cameras drifts through the video instead of staying a fixed bias, so the
	// synchronization error is not even constant. A rate of zero means the clip has not finished loading or its
	// rate is not advertised, which is also worth saying rather than silently comparing against nothing.
	float firstKnownRate = 0.0f;
	BOOL ratesDisagree = NO;
	BOOL anyRateUnknown = NO;
	NSUInteger loadedClipCount = 0;
	for (VSVideoClip *clip in self.videoClips) {
		if (clip.windowController == nil) continue;   // not loaded yet; it will call back here when it is
		loadedClipCount += 1;
		const float rate = [clip frameRate];
		if (rate <= 0.0f) {
			anyRateUnknown = YES;
		} else if (firstKnownRate == 0.0f) {
			firstKnownRate = rate;
		} else if (fabsf(rate - firstKnownRate) > 0.01f) {   // tolerance absorbs 29.97 reported slightly differently by different encoders
			ratesDisagree = YES;
		}
	}
	if (loadedClipCount < 2) {
		self.frameRateWarning = @"";
	} else if (ratesDisagree) {
		self.frameRateWarning = @"Clips have different frame rates!";
	} else if (anyRateUnknown) {
		self.frameRateWarning = @"A clip's frame rate is unknown!";
	} else {
		self.frameRateWarning = @"";
	}
}

- (NSDate *) dateCreatedAsNSDate
{
	return [UtilityFunctions dateTimeFromString:self.dateCreated format:@"yyy-MM-dd HH:mm:ss Z"];
}

- (NSDate *) dateLastSavedAsNSDate
{
	return [UtilityFunctions dateTimeFromString:self.dateLastSaved format:@"yyy-MM-dd HH:mm:ss Z"];
}

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath
{
	if (observer != nil) {
		@try {
			[self removeObserver:observer forKeyPath:keyPath];
		} @catch (id exception) {
		}
	}
}

@end
