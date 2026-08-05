/*********************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2026 Jason Neuswanger
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

#import <Accelerate/Accelerate.h>
#import "VSExportQueue.h"
#import "VSExportQueueWindowController.h"
#import "VidSyncDocument.h"

@interface VSExportQueue () {
	VSClipExportTask *__strong _runningTask;
	AVAssetExportSession *__strong _currentExportSession;	// non-nil only while a plain export runs
	NSTimer *__strong _plainProgressTimer;
}
@end

@implementation VSExportQueue

@synthesize document = _document;
@synthesize tasks = _tasks;
@synthesize windowController = _windowController;

- (instancetype) initWithDocument:(VidSyncDocument *)document
{
	self = [super init];
	if (self) {
		_document = document;
		_tasks = [NSMutableArray new];
		_windowController = [[VSExportQueueWindowController alloc] initWithQueue:self];
	}
	return self;
}

#pragma mark
#pragma mark Queue management (main thread)

- (void) enqueueTask:(VSClipExportTask *)task
{
	[_tasks addObject:task];
	[self showWindow];
	[_windowController noteTasksChanged];
	[self startNextTaskIfIdle];
}

- (void) cancelTask:(VSClipExportTask *)task
{
	if (task.status == VSClipExportTaskStatusQueued) {
		task.status = VSClipExportTaskStatusCancelled;
		task.statusMessage = @"Cancelled before starting";
		[_windowController noteTasksChanged];
	} else if (task.status == VSClipExportTaskStatusRunning) {
		task.cancelRequested = YES;					// the overlay worker polls this between frames
		task.statusMessage = @"Cancelling…";
		if (task == _runningTask && _currentExportSession != nil) [_currentExportSession cancelExport];
		[_windowController noteTasksChanged];
	}
}

- (void) cancelAllActiveTasks
{
	for (VSClipExportTask *task in [_tasks copy]) if ([task isActive]) [self cancelTask:task];
}

+ (uint8_t) rotationConstantForPreferredTransform:(CGAffineTransform)transform
{
	// Rounded so encoder float wobble in a nominally-exact transform doesn't defeat the match.
	int a = (int) round(transform.a), b = (int) round(transform.b);
	int c = (int) round(transform.c), d = (int) round(transform.d);
	if (a == 1 && b == 0 && c == 0 && d == 1) return kRotate0DegreesClockwise;
	if (a == 0 && b == 1 && c == -1 && d == 0) return kRotate90DegreesClockwise;			// portrait phone: storage top row becomes display right column
	if (a == 0 && b == -1 && c == 1 && d == 0) return kRotate90DegreesCounterClockwise;
	if (a == -1 && b == 0 && c == 0 && d == -1) return kRotate180DegreesClockwise;
	return 255;
}

+ (BOOL) rotatePixelBuffer:(CVPixelBufferRef)source into:(CVPixelBufferRef)destination withRotationConstant:(uint8_t)rotationConstant
{
	vImage_Buffer src = { CVPixelBufferGetBaseAddress(source), CVPixelBufferGetHeight(source), CVPixelBufferGetWidth(source), CVPixelBufferGetBytesPerRow(source) };
	vImage_Buffer dst = { CVPixelBufferGetBaseAddress(destination), CVPixelBufferGetHeight(destination), CVPixelBufferGetWidth(destination), CVPixelBufferGetBytesPerRow(destination) };
	if (src.data == NULL || dst.data == NULL) return NO;
	uint8_t backColor[4] = {0,0,0,255};
	return (vImageRotate90_ARGB8888(&src,&dst,rotationConstant,backColor,kvImageNoFlags) == kvImageNoError);
}

- (void) clearInactiveTasks
{
	NSMutableArray *keep = [NSMutableArray new];
	for (VSClipExportTask *task in _tasks) if ([task isActive]) [keep addObject:task];
	[_tasks setArray:keep];
	[_windowController noteTasksChanged];
}

- (void) showWindow
{
	[_windowController showWindow:nil];
}

- (BOOL) hasActiveTasks
{
	for (VSClipExportTask *task in _tasks) if ([task isActive]) return YES;
	return NO;
}

- (void) startNextTaskIfIdle
{
	if (_runningTask != nil) return;
	VSClipExportTask *next = nil;
	for (VSClipExportTask *task in _tasks) {
		if (task.status == VSClipExportTaskStatusQueued) { next = task; break; }
	}
	if (next == nil) return;
	_runningTask = next;
	next.status = VSClipExportTaskStatusRunning;
	next.statusMessage = @"Starting…";
	next.progress = 0.0;
	[_windowController noteTasksChanged];
	if (next.type == VSClipExportTaskTypeOverlayClip) {
		[self runOverlayExportTask:next];
	} else {
		[self runPlainExportTask:next usingPassthrough:YES];
	}
}

- (void) finishTask:(VSClipExportTask *)task withStatus:(VSClipExportTaskStatus)status error:(NSError *)error
{
	// Always called on the main thread, exactly once per started task.
	task.status = status;
	task.error = error;
	switch (status) {
		case VSClipExportTaskStatusFinished:
			task.progress = 1.0;
			task.statusMessage = @"Finished";
			[self.document playShutterClickSound];
			break;
		case VSClipExportTaskStatusFailed:
			task.statusMessage = (error != nil) ? [NSString stringWithFormat:@"Failed: %@",[error localizedDescription]] : @"Failed";
			break;
		case VSClipExportTaskStatusCancelled:
			task.statusMessage = @"Cancelled";
			break;
		default:
			break;
	}
	if (task == _runningTask) _runningTask = nil;
	_currentExportSession = nil;
	[_plainProgressTimer invalidate];
	_plainProgressTimer = nil;
	[_windowController noteTasksChanged];
	[self startNextTaskIfIdle];
}

- (void) failTask:(VSClipExportTask *)task withMessage:(NSString *)message
{
	NSError *error = [NSError errorWithDomain:@"VidSyncExport" code:1 userInfo:@{NSLocalizedDescriptionKey: message}];
	[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:error];
}

#pragma mark
#pragma mark Plain (no-overlay) exports via AVAssetExportSession

/*-------
 Passthrough is the ideal export mode here, but sometimes it doesn't work for inexplicable reasons with error
 messages that don't lead to useful information. So we try first with passthrough, and if that fails we retry
 once with a fixed MP4 preset of an appropriate size, which seems to work more reliably.
 --------*/

- (void) runPlainExportTask:(VSClipExportTask *)task usingPassthrough:(BOOL)usePassthrough
{
	VSVideoClip *videoClip = task.videoClip;
	AVAsset *asset = videoClip.windowController.videoAsset;
	if (videoClip == nil || asset == nil) {
		[self failTask:task withMessage:@"The video clip is no longer available."];
		return;
	}
	if (!asset.exportable) {
		[self failTask:task withMessage:@"The video clip is not exportable."];
		return;
	}
	[asset loadTracksWithMediaType:AVMediaTypeVideo completionHandler:^(NSArray<AVAssetTrack *> *videoTracks, NSError *videoError) {
		[asset loadTracksWithMediaType:AVMediaTypeAudio completionHandler:^(NSArray<AVAssetTrack *> *audioTracks, NSError *audioError) {
			dispatch_async(dispatch_get_main_queue(), ^{
				if ([videoTracks count] == 0) {
					[self failTask:task withMessage:@"The video clip has no video track."];
					return;
				}
				[self beginPlainExportForTask:task videoTrack:[videoTracks objectAtIndex:0] audioTrack:([audioTracks count] > 0 ? [audioTracks objectAtIndex:0] : nil) usingPassthrough:usePassthrough];
			});
		}];
	}];
}

- (void) beginPlainExportForTask:(VSClipExportTask *)task videoTrack:(AVAssetTrack *)videoTrack audioTrack:(AVAssetTrack *)audioTrack usingPassthrough:(BOOL)usePassthrough
{
	VSVideoClip *videoClip = task.videoClip;
	if (task.cancelRequested) {
		[self finishTask:task withStatus:VSClipExportTaskStatusCancelled error:nil];
		return;
	}
	// The time range is given in master times; convert to this clip's own timeline using its sync offset,
	// the same correction the overlay path applies, so synced non-master clips export the intended interval.
	// Exporting a composition of exactly the tracks we want (rather than the raw asset with a timeRange)
	// is what lets the sound checkbox drop audio without giving up passthrough speed.
	CMTime offset = [UtilityFunctions CMTimeFromString:videoClip.syncOffset];
	CMTimeRange clipRange = CMTimeRangeFromTimeToTime(CMTimeSubtract(task.startMasterTime,offset),CMTimeSubtract(task.endMasterTime,offset));
	AVMutableComposition *composition = [AVMutableComposition composition];
	AVMutableCompositionTrack *compositionVideoTrack = [composition addMutableTrackWithMediaType:AVMediaTypeVideo preferredTrackID:kCMPersistentTrackID_Invalid];
	NSError *insertError = nil;
	if (![compositionVideoTrack insertTimeRange:clipRange ofTrack:videoTrack atTime:kCMTimeZero error:&insertError]) {
		[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:insertError];
		return;
	}
	compositionVideoTrack.preferredTransform = videoTrack.preferredTransform;
	if (task.includeSound && audioTrack != nil) {
		AVMutableCompositionTrack *compositionAudioTrack = [composition addMutableTrackWithMediaType:AVMediaTypeAudio preferredTrackID:kCMPersistentTrackID_Invalid];
		if (![compositionAudioTrack insertTimeRange:clipRange ofTrack:audioTrack atTime:kCMTimeZero error:NULL]) {
			[composition removeTrack:compositionAudioTrack];	// a bad audio track downgrades the export to silent rather than failing it
		}
	}

	AVAssetExportSession *exportSession;
	NSString *destination;
	if (task.useHEVC) {
		// H.265 always means a re-encode; passthrough would just copy the source's codec.
		exportSession = [AVAssetExportSession exportSessionWithAsset:composition presetName:AVAssetExportPresetHEVCHighestQuality];
		exportSession.outputFileType = AVFileTypeMPEG4;
		destination = [[task.outputPath stringByDeletingPathExtension] stringByAppendingPathExtension:@"mp4"];
		task.outputPath = destination;
		if (exportSession == nil) {
			[self failTask:task withMessage:@"H.265 exporting isn't available on this Mac; choose H.264 on the Capture tab instead."];
			return;
		}
	} else if (usePassthrough) {
		// Every export is a clean .mp4 now: passthrough keeps the source's H.264/H.265 track but writes
		// it into an MPEG-4 container (the old QuickTime container under an .mp4 name misrepresented
		// itself to strict MP4 consumers). A source codec MP4 can't hold (ProRes, MJPEG, ...) makes this
		// session fail, and the existing failure handler below retries with the H.264 re-encode presets.
		exportSession = [AVAssetExportSession exportSessionWithAsset:composition presetName:AVAssetExportPresetPassthrough];
		exportSession.outputFileType = AVFileTypeMPEG4;
		destination = [[task.outputPath stringByDeletingPathExtension] stringByAppendingPathExtension:@"mp4"];
		task.outputPath = destination;
	} else {
		NSString *exportPreset;
		if (videoClip.clipWidth > 1280) {
			exportPreset = AVAssetExportPreset1920x1080;
		} else if (videoClip.clipWidth > 960) {
			exportPreset = AVAssetExportPreset1280x720;
		} else if (videoClip.clipWidth > 640) {
			exportPreset = AVAssetExportPreset960x540;
		} else {
			exportPreset = AVAssetExportPreset640x480;
		}
		exportSession = [AVAssetExportSession exportSessionWithAsset:composition presetName:exportPreset];
		exportSession.outputFileType = AVFileTypeMPEG4;
		destination = [[task.outputPath stringByDeletingPathExtension] stringByAppendingPathExtension:@"mp4"];
		task.outputPath = destination;
	}
	if (exportSession == nil) {
		[self failTask:task withMessage:@"Could not create an export session for this video."];
		return;
	}
	[[NSFileManager defaultManager] removeItemAtPath:destination error:NULL];	// overwriting was approved when the task was queued; export sessions fail on existing files
	exportSession.outputURL = [NSURL fileURLWithPath:destination];

	_currentExportSession = exportSession;
	task.statusMessage = usePassthrough ? @"Exporting (passthrough)" : @"Exporting (re-encoding)";
	[_windowController noteTasksChanged];
	[_plainProgressTimer invalidate];
	_plainProgressTimer = [NSTimer scheduledTimerWithTimeInterval:0.1 repeats:YES block:^(NSTimer *timer) {
		task.progress = exportSession.progress;
	}];

	[exportSession exportAsynchronouslyWithCompletionHandler:^{
		dispatch_async(dispatch_get_main_queue(), ^{
			if (exportSession.status == AVAssetExportSessionStatusCompleted) {
				[self finishTask:task withStatus:VSClipExportTaskStatusFinished error:nil];
			} else if (exportSession.status == AVAssetExportSessionStatusCancelled || task.cancelRequested) {
				[[NSFileManager defaultManager] removeItemAtPath:destination error:NULL];
				[self finishTask:task withStatus:VSClipExportTaskStatusCancelled error:nil];
			} else if (exportSession.status == AVAssetExportSessionStatusFailed && usePassthrough && !task.useHEVC) {	// the H.265 path has no passthrough to fall back from
				task.statusMessage = @"Passthrough failed; retrying with re-encode";
				task.progress = 0.0;
				[self->_plainProgressTimer invalidate];
				self->_plainProgressTimer = nil;
				self->_currentExportSession = nil;
				[self runPlainExportTask:task usingPassthrough:NO];
			} else {
				[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:exportSession.error];
			}
		});
	}];
}

#pragma mark
#pragma mark Overlay exports via AVAssetReader + AVAssetWriter

/*-------
 Returns a +1 retained copy of the sample buffer with every timestamp shifted earlier by 'shift', or NULL
 on failure. The video path re-times each frame by passing an explicit presentation time to the pixel
 buffer adaptor, but audio samples are appended as whole sample buffers, so the export interval's samples
 have to be re-stamped this way to land at the start of the output timeline.
 --------*/
static CMSampleBufferRef VSCreateRetimedSampleBuffer(CMSampleBufferRef sample, CMTime shift)
{
	CMItemCount count = 0;
	if (CMSampleBufferGetSampleTimingInfoArray(sample,0,NULL,&count) != noErr) return NULL;
	if (count < 1) {	// no timing entries to adjust; the buffer is usable as-is
		CFRetain(sample);
		return sample;
	}
	CMSampleTimingInfo *timings = (CMSampleTimingInfo *) malloc(sizeof(CMSampleTimingInfo) * count);
	if (timings == NULL) return NULL;
	if (CMSampleBufferGetSampleTimingInfoArray(sample,count,timings,&count) != noErr) {
		free(timings);
		return NULL;
	}
	for (CMItemCount i = 0; i < count; i++) {
		timings[i].presentationTimeStamp = CMTimeSubtract(timings[i].presentationTimeStamp,shift);
		if (CMTIME_IS_VALID(timings[i].decodeTimeStamp)) timings[i].decodeTimeStamp = CMTimeSubtract(timings[i].decodeTimeStamp,shift);
	}
	CMSampleBufferRef retimed = NULL;
	OSStatus status = CMSampleBufferCreateCopyWithNewTiming(kCFAllocatorDefault,sample,count,timings,&retimed);
	free(timings);
	return (status == noErr) ? retimed : NULL;
}

- (void) runOverlayExportTask:(VSClipExportTask *)task
{
	VSVideoClip *videoClip = task.videoClip;
	VideoWindowController *vwc = videoClip.windowController;
	if (videoClip == nil || vwc == nil || vwc.overlayView == nil) {
		[self failTask:task withMessage:@"The video clip's window is no longer available."];
		return;
	}
	if (vwc.movieSize.width < 1 || vwc.movieSize.height < 1) {
		[self failTask:task withMessage:@"The video's dimensions could not be determined."];
		return;
	}
	if ([videoClip frameRate] <= 0) {
		[self failTask:task withMessage:@"This video's frame rate could not be determined."];
		return;
	}
	NSURL *sourceURL = ([vwc.videoAsset isKindOfClass:[AVURLAsset class]]) ? [(AVURLAsset *)vwc.videoAsset URL] : nil;
	if (sourceURL == nil) {
		[self failTask:task withMessage:@"The video's source file could not be located."];
		return;
	}

	// Read from a fresh asset, independent of the one AVPlayer is using, so the export never disturbs
	// (and is never disturbed by) whatever the user does with playback while it runs.
	AVURLAsset *asset = [AVURLAsset URLAssetWithURL:sourceURL options:nil];
	[asset loadTracksWithMediaType:AVMediaTypeVideo completionHandler:^(NSArray<AVAssetTrack *> *tracks, NSError *error) {
		if (error != nil || [tracks count] == 0) {
			dispatch_async(dispatch_get_main_queue(), ^{
				[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:error];
			});
			return;
		}
		if (!task.includeSound) {	// sound turned off on the Capture tab: don't even look for an audio track
			dispatch_async(dispatch_get_main_queue(), ^{
				[self beginOverlayWritingForTask:task asset:asset videoTrack:[tracks objectAtIndex:0] audioTrack:nil];
			});
			return;
		}
		[asset loadTracksWithMediaType:AVMediaTypeAudio completionHandler:^(NSArray<AVAssetTrack *> *audioTracks, NSError *audioError) {
			dispatch_async(dispatch_get_main_queue(), ^{
				// Audio is optional: a silent source (or a failed audio-track load) still exports its video.
				AVAssetTrack *audioTrack = (audioError == nil && [audioTracks count] > 0) ? [audioTracks objectAtIndex:0] : nil;
				[self beginOverlayWritingForTask:task asset:asset videoTrack:[tracks objectAtIndex:0] audioTrack:audioTrack];
			});
		}];
	}];
}

- (void) beginOverlayWritingForTask:(VSClipExportTask *)task asset:(AVAsset *)asset videoTrack:(AVAssetTrack *)videoTrack audioTrack:(AVAssetTrack *)audioTrack
{
	VSVideoClip *videoClip = task.videoClip;
	VideoWindowController *vwc = videoClip.windowController;
	VideoOverlayView *overlayView = vwc.overlayView;
	if (task.cancelRequested || overlayView == nil) {
		[self finishTask:task withStatus:VSClipExportTaskStatusCancelled error:nil];
		return;
	}
	CGSize movieSize = vwc.movieSize;
	// movieSize (and everything composited onto the canvas) is in display orientation, but the reader
	// below delivers storage-orientation buffers; rotation-flagged clips (vertical phone video) used to
	// export sideways and cropped. Frames are normalized with a vImage rotate in the loop below.
	uint8_t rotationConstant = [VSExportQueue rotationConstantForPreferredTransform:videoTrack.preferredTransform];
	if (rotationConstant == 255) {
		[self failTask:task withMessage:@"This video has an unusual orientation transform (a flip or skew) that overlay exports can't reproduce. Export it without overlays instead."];
		return;
	}
	CMTime offset = [UtilityFunctions CMTimeFromString:videoClip.syncOffset];
	CMTime clipStart = CMTimeSubtract(task.startMasterTime,offset);
	CMTime clipEnd = CMTimeSubtract(task.endMasterTime,offset);
	float frameRate = [videoClip frameRate];
	CMTime frameDuration = CMTimeMake(1000000,(int32_t) round(frameRate*1000000.0f));
	double durationSeconds = CMTimeGetSeconds(CMTimeSubtract(clipEnd,clipStart));

	NSError *error = nil;
	AVAssetReader *reader = [AVAssetReader assetReaderWithAsset:asset error:&error];
	if (reader == nil) {
		[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:error];
		return;
	}
	NSDictionary *readerSettings = @{(id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA)};
	AVAssetReaderTrackOutput *readerOutput = [AVAssetReaderTrackOutput assetReaderTrackOutputWithTrack:videoTrack outputSettings:readerSettings];
	readerOutput.alwaysCopiesSampleData = NO;
	if (![reader canAddOutput:readerOutput]) {
		[self failTask:task withMessage:@"Could not read frames from this video."];
		return;
	}
	[reader addOutput:readerOutput];
	// Extend the range by one frame so the frame at the end time is included, matching the old
	// step-through capture loop, whose while condition was inclusive of the end time.
	reader.timeRange = CMTimeRangeFromTimeToTime(clipStart,CMTimeAdd(clipEnd,frameDuration));

	[[NSFileManager defaultManager] removeItemAtPath:task.outputPath error:NULL];	// overwriting was approved when the task was queued; AVAssetWriter fails on existing files
	AVAssetWriter *writer = [[AVAssetWriter alloc] initWithURL:[NSURL fileURLWithPath:task.outputPath] fileType:AVFileTypeMPEG4 error:&error];
	if (writer == nil) {
		[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:error];
		return;
	}
	NSDictionary *videoSettings = @{AVVideoCodecKey: (task.useHEVC ? AVVideoCodecTypeHEVC : AVVideoCodecTypeH264),
							  AVVideoWidthKey: [NSNumber numberWithInt:(int) round(movieSize.width)],
							  AVVideoHeightKey: [NSNumber numberWithInt:(int) round(movieSize.height)]};
	AVAssetWriterInput *writerInput = [AVAssetWriterInput assetWriterInputWithMediaType:AVMediaTypeVideo outputSettings:videoSettings];
	writerInput.expectsMediaDataInRealTime = NO;	// this is a file export, not a live capture; let the writer pace itself
	NSDictionary *pixelBufferAttributes = @{(id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA),
									(id)kCVPixelBufferWidthKey: [NSNumber numberWithInt:(int) round(movieSize.width)],
									(id)kCVPixelBufferHeightKey: [NSNumber numberWithInt:(int) round(movieSize.height)],
									(id)kCVPixelBufferCGBitmapContextCompatibilityKey: @YES};
	AVAssetWriterInputPixelBufferAdaptor *adaptor = [AVAssetWriterInputPixelBufferAdaptor assetWriterInputPixelBufferAdaptorWithAssetWriterInput:writerInput sourcePixelBufferAttributes:pixelBufferAttributes];
	if (![writer canAddInput:writerInput]) {
		[self failTask:task withMessage:@"Could not configure the video writer."];
		return;
	}
	[writer addInput:writerInput];

	// Carry the source's audio into the output alongside the re-rendered video, trimmed by the reader's
	// shared timeRange and re-timed to start at zero like the video. Compressed samples pass straight
	// through when the source codec is one MP4 can hold; otherwise (e.g. PCM in a MOV) the reader
	// decodes to PCM and the writer re-encodes as AAC. Audio problems here downgrade the export to
	// video-only rather than failing it.
	AVAssetReaderTrackOutput *audioReaderOutput = nil;
	AVAssetWriterInput *audioWriterInput = nil;
	if (audioTrack != nil) {
		BOOL passthroughCompatible = ([audioTrack.formatDescriptions count] > 0);
		double audioSampleRate = 44100.0;
		NSUInteger audioChannels = 2;
		for (id untypedDescription in audioTrack.formatDescriptions) {
			CMFormatDescriptionRef formatDescription = (__bridge CMFormatDescriptionRef) untypedDescription;
			FourCharCode codec = CMFormatDescriptionGetMediaSubType(formatDescription);
			if (codec != kAudioFormatMPEG4AAC && codec != kAudioFormatMPEG4AAC_HE && codec != kAudioFormatMPEG4AAC_HE_V2 && codec != kAudioFormatMPEGLayer3) passthroughCompatible = NO;
			const AudioStreamBasicDescription *asbd = CMAudioFormatDescriptionGetStreamBasicDescription(formatDescription);
			if (asbd != NULL) {
				if (asbd->mSampleRate > 0) audioSampleRate = MIN(asbd->mSampleRate,48000.0);	// AAC tops out at 48 kHz
				if (asbd->mChannelsPerFrame == 1) audioChannels = 1;
			}
		}
		NSDictionary *audioReaderSettings = passthroughCompatible ? nil : @{AVFormatIDKey: @(kAudioFormatLinearPCM)};
		NSDictionary *audioWriterSettings = passthroughCompatible ? nil : @{AVFormatIDKey: @(kAudioFormatMPEG4AAC),
																	 AVSampleRateKey: @(audioSampleRate),
															   AVNumberOfChannelsKey: @(audioChannels),
																AVEncoderBitRateKey: @(audioChannels == 1 ? 96000 : 192000)};
		audioReaderOutput = [AVAssetReaderTrackOutput assetReaderTrackOutputWithTrack:audioTrack outputSettings:audioReaderSettings];
		audioReaderOutput.alwaysCopiesSampleData = NO;
		// A passthrough input (nil settings) must be given the source format as a hint; without one the
		// writer can't verify the audio fits an MP4 and canAddInput: refuses it.
		CMFormatDescriptionRef audioFormatHint = passthroughCompatible ? (__bridge CMFormatDescriptionRef) [audioTrack.formatDescriptions firstObject] : NULL;
		audioWriterInput = [[AVAssetWriterInput alloc] initWithMediaType:AVMediaTypeAudio outputSettings:audioWriterSettings sourceFormatHint:audioFormatHint];
		audioWriterInput.expectsMediaDataInRealTime = NO;
		if ([reader canAddOutput:audioReaderOutput] && [writer canAddInput:audioWriterInput]) {
			[reader addOutput:audioReaderOutput];
			[writer addInput:audioWriterInput];
		} else {
			audioReaderOutput = nil;
			audioWriterInput = nil;
		}
	}

	if (![reader startReading]) {
		[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:reader.error];
		return;
	}
	if (![writer startWriting]) {
		[reader cancelReading];
		[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:writer.error];
		return;
	}
	[writer startSessionAtSourceTime:kCMTimeZero];
	task.statusMessage = @"Exporting with overlay";
	[_windowController noteTasksChanged];

	// With two streams feeding the writer from separate queues, all terminal decisions funnel through
	// the main thread, which serializes them and guarantees finishTask: runs exactly once. Each stream
	// reports in exactly once — as drained (status Finished), or with the cancel/failure it hit — after
	// marking its own input finished so the writer never stalls waiting to interleave the other stream.
	// The first bad report cancels the reader, which drains the other stream promptly; only after both
	// streams have reported does the writer get its single finishWriting or cancelWriting call.
	NSUInteger expectedStreams = (audioWriterInput != nil) ? 2 : 1;
	__block NSUInteger streamsEnded = 0;			// these five are main thread only
	__block BOOL abortPending = NO;
	__block VSClipExportTaskStatus abortStatus = VSClipExportTaskStatusFailed;
	__block NSError *abortError = nil;
	__block NSString *abortMessage = nil;
	void (^streamEnded)(VSClipExportTaskStatus, NSError *, NSString *) = ^(VSClipExportTaskStatus status, NSError *error, NSString *message) {
		dispatch_async(dispatch_get_main_queue(), ^{
			if (task.status != VSClipExportTaskStatusRunning) return;
			streamsEnded += 1;
			if (status != VSClipExportTaskStatusFinished && !abortPending) {
				abortPending = YES;
				abortStatus = status;
				abortError = error;
				abortMessage = message;
				[reader cancelReading];
			}
			if (streamsEnded < expectedStreams) return;
			if (abortPending) {
				[writer cancelWriting];
				if (abortStatus == VSClipExportTaskStatusCancelled) {
					[[NSFileManager defaultManager] removeItemAtPath:task.outputPath error:NULL];
					[self finishTask:task withStatus:VSClipExportTaskStatusCancelled error:nil];
				} else if (abortError != nil) {
					[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:abortError];
				} else {
					[self failTask:task withMessage:(abortMessage != nil) ? abortMessage : @"The export failed."];
				}
			} else {
				[writer finishWritingWithCompletionHandler:^{
					dispatch_async(dispatch_get_main_queue(), ^{
						if (task.status != VSClipExportTaskStatusRunning) return;
						if (writer.status == AVAssetWriterStatusCompleted) {
							[self finishTask:task withStatus:VSClipExportTaskStatusFinished error:nil];
						} else {
							[self finishTask:task withStatus:VSClipExportTaskStatusFailed error:writer.error];
						}
					});
				}];
			}
		});
	};

	// The worker queue owns the frame loop: decode, composite, and encode all happen here. The only
	// main-thread work is one brief offscreen overlay render per frame, so the app stays responsive
	// and the user can keep working (even playing the videos) while the export runs.
	dispatch_queue_t workQueue = dispatch_queue_create("org.vidsync.overlayExport", DISPATCH_QUEUE_SERIAL);
	__block BOOL donePulling = NO;	// only touched on workQueue

	[writerInput requestMediaDataWhenReadyOnQueue:workQueue usingBlock:^{
		if (donePulling) return;
		while ([writerInput isReadyForMoreMediaData]) {
			if (task.cancelRequested) {
				donePulling = YES;
				[writerInput markAsFinished];
				streamEnded(VSClipExportTaskStatusCancelled,nil,nil);
				return;
			}
			CMSampleBufferRef sample = [readerOutput copyNextSampleBuffer];
			if (sample == NULL) {
				donePulling = YES;
				[writerInput markAsFinished];
				if (reader.status == AVAssetReaderStatusFailed) {
					streamEnded(VSClipExportTaskStatusFailed,reader.error,nil);
				} else {
					streamEnded(VSClipExportTaskStatusFinished,nil,nil);
				}
				return;
			}

			CVImageBufferRef sourceBuffer = CMSampleBufferGetImageBuffer(sample);
			CMTime framePTS = CMSampleBufferGetPresentationTimeStamp(sample);
			CMTime masterTime = CMTimeAdd(framePTS,offset);

			// Render this frame's overlay on the main thread; drawing walks the document's live
			// Core Data objects and AppKit views, which are main-thread-only.
			__block CGImageRef overlayImage = NULL;
			dispatch_sync(dispatch_get_main_queue(), ^{
				overlayImage = [overlayView newOverlayImageForExportAtMasterTime:masterTime pixelSize:movieSize];
			});

			BOOL appended = NO;
			CVPixelBufferRef outBuffer = NULL;
			CVPixelBufferPoolRef pool = adaptor.pixelBufferPool;
			if (pool != NULL) {
				CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault,pool,&outBuffer);
			} else {	// the adaptor's pool can lag the session start; fall back to a one-off buffer rather than dropping the frame
				CVPixelBufferCreate(kCFAllocatorDefault,(size_t) round(movieSize.width),(size_t) round(movieSize.height),kCVPixelFormatType_32BGRA,(__bridge CFDictionaryRef) pixelBufferAttributes,&outBuffer);
			}
			if (outBuffer != NULL && sourceBuffer != NULL) {
				CVPixelBufferLockBaseAddress(sourceBuffer,kCVPixelBufferLock_ReadOnly);
				CVPixelBufferLockBaseAddress(outBuffer,0);
				// Bring the decoded frame into our own buffer in display orientation -- a straight row
				// copy when the clip carries no rotation, a vImage rotate when it does -- then burn the
				// overlay in on top.
				size_t srcBytesPerRow = CVPixelBufferGetBytesPerRow(sourceBuffer);
				size_t dstBytesPerRow = CVPixelBufferGetBytesPerRow(outBuffer);
				size_t rowsToCopy = MIN(CVPixelBufferGetHeight(sourceBuffer),CVPixelBufferGetHeight(outBuffer));
				size_t bytesPerRowToCopy = MIN(srcBytesPerRow,dstBytesPerRow);
				uint8_t *src = (uint8_t *) CVPixelBufferGetBaseAddress(sourceBuffer);
				uint8_t *dst = (uint8_t *) CVPixelBufferGetBaseAddress(outBuffer);
				if (src != NULL && dst != NULL) {
					if (rotationConstant == kRotate0DegreesClockwise) {
						for (size_t row = 0; row < rowsToCopy; row++) memcpy(dst + row*dstBytesPerRow,src + row*srcBytesPerRow,bytesPerRowToCopy);
					} else {
						[VSExportQueue rotatePixelBuffer:sourceBuffer into:outBuffer withRotationConstant:rotationConstant];
					}
					if (overlayImage != NULL) {
						CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
						CGContextRef context = CGBitmapContextCreate(dst,
															CVPixelBufferGetWidth(outBuffer),
															CVPixelBufferGetHeight(outBuffer),
															8,
															dstBytesPerRow,
															colorSpace,
															kCGBitmapByteOrder32Little | kCGImageAlphaPremultipliedFirst);
						if (context != NULL) {
							CGContextDrawImage(context,CGRectMake(0,0,CVPixelBufferGetWidth(outBuffer),CVPixelBufferGetHeight(outBuffer)),overlayImage);
							CGContextRelease(context);
						}
						CGColorSpaceRelease(colorSpace);
					}
				}
				CVPixelBufferUnlockBaseAddress(outBuffer,0);
				CVPixelBufferUnlockBaseAddress(sourceBuffer,kCVPixelBufferLock_ReadOnly);
				appended = [adaptor appendPixelBuffer:outBuffer withPresentationTime:CMTimeSubtract(framePTS,clipStart)];
			}
			if (outBuffer != NULL) CVPixelBufferRelease(outBuffer);
			if (overlayImage != NULL) CGImageRelease(overlayImage);
			CFRelease(sample);

			if (!appended) {
				donePulling = YES;
				NSError *writeError = writer.error;
				[writerInput markAsFinished];
				streamEnded(VSClipExportTaskStatusFailed,writeError,@"Could not append a frame to the output video.");
				return;
			}
			if (durationSeconds > 0) {
				double fractionDone = CMTimeGetSeconds(CMTimeSubtract(framePTS,clipStart)) / durationSeconds;
				task.progress = MAX(0.0,MIN(1.0,fractionDone));
			}
		}
	}];

	// Audio is pulled on its own queue so the two streams can interleave at the writer's pace without
	// either loop blocking the other; the samples need no compositing, just the re-timing shift.
	if (audioWriterInput != nil) {
		dispatch_queue_t audioQueue = dispatch_queue_create("org.vidsync.overlayExportAudio", DISPATCH_QUEUE_SERIAL);
		AVAssetReaderTrackOutput *audioOutput = audioReaderOutput;
		AVAssetWriterInput *audioInput = audioWriterInput;
		__block BOOL doneAudio = NO;	// only touched on audioQueue
		[audioInput requestMediaDataWhenReadyOnQueue:audioQueue usingBlock:^{
			if (doneAudio) return;
			while ([audioInput isReadyForMoreMediaData]) {
				if (task.cancelRequested) {
					doneAudio = YES;
					[audioInput markAsFinished];
					streamEnded(VSClipExportTaskStatusCancelled,nil,nil);
					return;
				}
				CMSampleBufferRef sample = [audioOutput copyNextSampleBuffer];
				if (sample == NULL) {
					doneAudio = YES;
					[audioInput markAsFinished];
					if (reader.status == AVAssetReaderStatusFailed) {
						streamEnded(VSClipExportTaskStatusFailed,reader.error,nil);
					} else {
						streamEnded(VSClipExportTaskStatusFinished,nil,nil);
					}
					return;
				}
				if (CMSampleBufferGetNumSamples(sample) == 0) {	// readers emit empty marker buffers at range edges; nothing to append
					CFRelease(sample);
					continue;
				}
				CMSampleBufferRef retimed = VSCreateRetimedSampleBuffer(sample,clipStart);
				BOOL appended = (retimed != NULL) && [audioInput appendSampleBuffer:retimed];
				if (retimed != NULL) CFRelease(retimed);
				CFRelease(sample);
				if (!appended) {
					doneAudio = YES;
					NSError *writeError = writer.error;
					[audioInput markAsFinished];
					streamEnded(VSClipExportTaskStatusFailed,writeError,@"Could not append audio to the output video.");
					return;
				}
			}
		}];
	}
}

@end
