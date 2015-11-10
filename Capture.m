//
//  Capture.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/2/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VidSyncDocument.h"

@implementation VidSyncDocument (Capture)

#pragma mark
#pragma mark IBActions

- (IBAction)captureStills:(id)sender
{
    BOOL showOverlaysInExportedFiles = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeOverlaysInExportedFiles"] boolValue];

	[self setAllVideoRates:0.0];				// pause all movies
	[self reSync];								// make sure they're all perfectly synchronized (also refreshes all their overlays)
	NSMutableSet *clipsToExportFrom = [NSMutableSet set];
	if ([[exportClipSelectionPopUpButton selectedItem] representedObject] == nil) {								// if the null placeholder "All Clips" is selected, select all clips
		for  (VSVideoClip *videoClip in self.project.videoClips) [clipsToExportFrom addObject:videoClip];
	} else {																									// otherwise, select only the clip(s) with the selected name
		NSString *exportClipName = [[exportClipSelectionPopUpButton selectedItem] representedObject];
		for  (VSVideoClip *videoClip in self.project.videoClips) if ([videoClip.clipName isEqualToString:exportClipName]) [clipsToExportFrom addObject:videoClip];
	}
	NSString *outFilePath;
    NSImage *writeImage;
    [writeImage setCacheMode:NSImageCacheNever];
	BOOL success = YES;
	for (VSVideoClip *videoClip in clipsToExportFrom) {
        CGImageRef outImage = [self stillCGImageFromVSVideoClip:videoClip atMasterTime:[self currentMasterTime] showOverlay:showOverlaysInExportedFiles];
        writeImage = [[NSImage alloc] initWithCGImage:outImage size:NSZeroSize];
		if ([writeImage isValid]) {
			outFilePath = [self fileNameForExportedFileFromClip:videoClip withExtension:@"jpg"];				// construct the filename & path
			[self saveNSImageAsJpeg:writeImage destination:outFilePath overwriteWarnings:YES];											// write the image
		} else {
			success = NO;
			NSRunAlertPanel(@"Error saving frames",@"The frame image generated was not valid.",@"Ok",nil,nil);
		}
	}
	if (success) [shutterClick play];
}

- (IBAction)capturePortraits:(id)sender
{
    NSImage *portraitImage;
    if ([[allPortraitsArrayController arrangedObjects] count] > 0) {
        
        NSFileManager *fm = [NSFileManager defaultManager];
        NSString *fileSafeProjectName = [[self.project.name stringByReplacingOccurrencesOfString:@":" withString:@"-"] stringByReplacingOccurrencesOfString:@"/" withString:@"+"];
        NSString *portraitsFolder = [NSString stringWithFormat:@"%@/%@ Portraits",self.project.capturePathForStills,fileSafeProjectName];
        if (![fm fileExistsAtPath:portraitsFolder]) [fm createDirectoryAtPath:portraitsFolder withIntermediateDirectories:YES attributes:nil error:NULL];
        for (VSTrackedObjectPortrait *portrait in [allPortraitsArrayController arrangedObjects]) {
            portraitImage = (NSImage *) [portrait imageRepresentation];
            if ([portraitImage isValid]) {
                NSMutableString *filePath = [NSMutableString new];
                [filePath appendString:self.project.capturePathForStills];
                NSString *nameString = ([portrait.trackedObject.name isEqualToString:@""]) ? @"" : [NSString stringWithFormat:@" (%@)",portrait.trackedObject.name];
                NSString *fileSafeTimecode = [[portrait.timecode stringByReplacingOccurrencesOfString:@":" withString:@"-"] stringByReplacingOccurrencesOfString:@"/" withString:@"+"];
                [filePath appendFormat:@"/%@ Portraits/%@ %@%@ from %@ (%@) at %@.jpg",fileSafeProjectName,portrait.trackedObject.type.name,portrait.trackedObject.index,nameString,fileSafeProjectName,portrait.sourceVideoClip.clipName,fileSafeTimecode];
                [self saveNSImageAsJpeg:portraitImage destination:filePath overwriteWarnings:NO];
            }
        }
        [shutterClick play];
    } else {
        NSRunAlertPanel(@"There are no portraits yet",@"You have to create portraits of objects before you can export them.",@"Ok",nil,nil);
    }
}

- (IBAction)setVideoCaptureTime:(id)sender
{
	if ([sender tag] == 1) {
		self.project.movieCaptureStartTime = [self currentMasterTimeString];
	} else if ([sender tag] == 2) {
		self.project.movieCaptureEndTime = [self currentMasterTimeString];
	}	
}

- (IBAction)goToVideoCaptureTime:(id)sender
{
	if ([sender tag] == 1) {
		[self goToMasterTime:[UtilityFunctions CMTimeFromString:self.project.movieCaptureStartTime]];
	} else if ([sender tag] == 2) {
		[self goToMasterTime:[UtilityFunctions CMTimeFromString:self.project.movieCaptureEndTime]];
	}	
}

- (IBAction)chooseCapturePath:(id)sender
{
	NSString *capturePath = nil;
	NSOpenPanel *dirSelectPanel = [NSOpenPanel openPanel];
	[dirSelectPanel setCanChooseFiles:NO];
	[dirSelectPanel setCanChooseDirectories:YES];
	[dirSelectPanel setCanCreateDirectories:YES];
	[dirSelectPanel setAllowsMultipleSelection:NO];
	if ([dirSelectPanel runModal]) {
		capturePath = [[[dirSelectPanel URLs] objectAtIndex:0] path];
		if ([sender tag] == 1) {
			self.project.capturePathForStills = capturePath;
		} else if ([sender tag] == 2) {
			self.project.capturePathForMovies = capturePath;			
		} else if ([sender tag] == 3) {
			self.project.exportPathForData = capturePath;			
		} 
	}
	
}

- (IBAction)openCapturePathInFinder:(id)sender
{
	BOOL appendsProjectName = YES;	
	NSString *capturePath = nil;
	if ([sender tag] == 1) {
		capturePath = self.project.capturePathForStills;
		appendsProjectName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"createFolderForProjectCaptures"] boolValue];
	} else if ([sender tag] == 2) {
		capturePath = self.project.capturePathForMovies;			
		appendsProjectName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"createFolderForProjectCaptures"] boolValue];
	} else if ([sender tag] == 3) {
		capturePath = self.project.exportPathForData;			
		appendsProjectName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"createFolderForProjectExports"] boolValue];
	}
	if (appendsProjectName) capturePath = [capturePath stringByAppendingFormat:@"/%@",self.project.name];
	
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create video capture directory if it doesn't exist yet
	if (![fm fileExistsAtPath:capturePath]) [fm createDirectoryAtPath:capturePath withIntermediateDirectories:YES attributes:nil error:NULL];
	
	[[NSWorkspace sharedWorkspace] selectFile:capturePath inFileViewerRootedAtPath:@""];
}

- (IBAction)captureVideoClips:(id)sender
{
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create video capture directory if it doesn't exist yet
	BOOL showOverlaysInExportedFiles = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeOverlaysInExportedFiles"] boolValue];
	NSMutableSet *clipsToExportFrom = [NSMutableSet set];
	if ([[exportClipSelectionPopUpButton selectedItem] representedObject] == nil) {								// if the null placeholder "All Clips" is selected, select all clips
		for  (VSVideoClip *videoClip in self.project.videoClips) [clipsToExportFrom addObject:videoClip];
	} else {																									// otherwise, select only the clip(s) with the selected name
		NSString *exportClipName = [[exportClipSelectionPopUpButton selectedItem] representedObject];
		for  (VSVideoClip *videoClip in self.project.videoClips) if ([videoClip.clipName isEqualToString:exportClipName]) [clipsToExportFrom addObject:videoClip];
	}
	for (VSVideoClip *videoClip in clipsToExportFrom) {
		BOOL doWrite = YES;
		NSString *destination = [self fileNameForExportedFileFromClip:videoClip withExtension:@"mp4"];
		if ([fm fileExistsAtPath:destination]) {
			NSInteger alertResult = NSRunAlertPanel(@"Overwrite file?",@"The file you would be writing already exists. Overwrite it?",@"No",@"Yes",nil);
			if (alertResult == 1) {
                doWrite = NO;
            } else {
                NSError *fileRemovalError;
                [fm removeItemAtPath:destination error:&fileRemovalError];
            }
		} 
		if ([destination length] == 0) doWrite = NO;
		if (doWrite) {
			if (showOverlaysInExportedFiles) {
				[self captureWithOverlayFromVideoClip:videoClip toFile:destination];
			} else {
				[self captureWithoutOverlayFromVideoClip:videoClip usingPassthrough:YES];
			}		
		}
	}	

}

#pragma mark
#pragma mark Fuctions for Movies Only


- (void) captureWithoutOverlayFromVideoClip:(VSVideoClip *)videoClip usingPassthrough:(BOOL)usePassthrough
{
    CMTime clipStartTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureStartTime];
	CMTime clipEndTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureEndTime];
    
    if (!videoClip.windowController.videoAsset.exportable) {
        NSLog(@"The video clip is not exportable.");
        return;
    }
    
    AVAssetExportSession *__block exportSession; // used for exporting videos without overlays -- needs to be an instance variable so I can use it from the progress bar update function
    
    /*-------
     Passthrough is the ideal export mode here, but sometimes it doesn't work for inexplicable reasons with error messages that don't lead me to useful information.
     So instead we try first with passthrough, and if passthrough fails then we try a single recursive call with passthrough = NO that forces an MP4 format ith fixed presets 
     of an appropriate size, which seems to work more reliably, at least for my test videos.
     --------*/
    
    NSString *newDestination;
    if (usePassthrough) {
        exportSession = [AVAssetExportSession exportSessionWithAsset:videoClip.windowController.videoAsset presetName:AVAssetExportPresetPassthrough];
        exportSession.outputFileType = AVFileTypeQuickTimeMovie;
        newDestination = [self fileNameForExportedFileFromClip:videoClip withExtension:[videoClip.fileName pathExtension]];
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
        exportSession = [AVAssetExportSession exportSessionWithAsset:videoClip.windowController.videoAsset presetName:exportPreset];
        exportSession.outputFileType = AVFileTypeMPEG4;
        newDestination = [self fileNameForExportedFileFromClip:videoClip withExtension:@"mp4"];
    }
    exportSession.outputURL = [NSURL fileURLWithPath:newDestination];
    exportSession.timeRange = CMTimeRangeFromTimeToTime(clipStartTime,clipEndTime);
    
    NSTimer *__block exportProgressBarTimer = [NSTimer scheduledTimerWithTimeInterval:0.1 target:self selector:@selector(updateExportProgressBar) userInfo:nil repeats:YES];
    [videoCaptureProgressIndicator setDoubleValue:0.0];
    [videoCaptureProgressIndicator setHidden:NO];
	[videoCaptureProgressIndicator displayIfNeeded];
    [videoCaptureProgressDescription setStringValue:[NSString stringWithFormat:@"Capturing '%@.'",videoClip.clipName]];
    [videoCaptureProgressDescription displayIfNeeded];

    void (^myCompletionHandler)(void) = ^(void)
    {
        if (exportSession.status == AVAssetExportSessionStatusCompleted) {
            [shutterClick play];
            [videoCaptureProgressDescription setStringValue:@"Completed."];
        } else if (exportSession.status == AVAssetExportSessionStatusFailed && exportSession.error != nil) {
            if (usePassthrough == YES) {
                [videoCaptureProgressDescription setStringValue:@"Retrying..."];
                if ([activeExportSessions containsObject:exportSession]) [activeExportSessions removeObject:exportSession];
                [self captureWithoutOverlayFromVideoClip:videoClip usingPassthrough:NO];
            } else {
                [videoCaptureProgressDescription setStringValue:@"Error."];
            }
        } else {
            [shutterClick play];
            [videoCaptureProgressDescription setStringValue:@"Completed."];
        }
        if ([activeExportSessions containsObject:exportSession]) [activeExportSessions removeObject:exportSession];
        if ([activeExportSessions count] == 0) {
            [videoCaptureProgressIndicator setHidden:YES];
            [videoCaptureProgressDescription displayIfNeeded];
            [exportProgressBarTimer invalidate];
        }
        exportSession = nil;
    };
    [activeExportSessions addObject:exportSession];
    [exportSession exportAsynchronouslyWithCompletionHandler:myCompletionHandler];
}

- (void) updateExportProgressBar    // the progress bar for no-overlay exports reflects the minimum progress of any of the files
{
    if ([activeExportSessions count] > 0) {
        double lowestExportProgress = 1.0;
        NSSet *currentActiveExportSessions = (NSSet *)activeExportSessions;
        for (AVAssetExportSession *session in currentActiveExportSessions) {
            if (session != nil && [session progress] < lowestExportProgress) lowestExportProgress = [session progress];
        }
        [videoCaptureProgressIndicator setDoubleValue:lowestExportProgress];
    }
}

- (void) captureWithOverlayFromVideoClip:(VSVideoClip *)videoClip toFile:(NSString *)destination
{
    float movieWidth = videoClip.windowController.movieSize.width;
    float movieHeight = videoClip.windowController.movieSize.height;
    
    CMTime clipStartTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureStartTime];
	CMTime clipEndTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureEndTime];
    CMTimeRange clipTimeRange = CMTimeRangeFromTimeToTime(clipStartTime,clipEndTime);
    
    NSError *error;
    AVAssetWriter *videoWriter = [[AVAssetWriter alloc] initWithURL: [NSURL fileURLWithPath:destination] fileType:AVFileTypeMPEG4 error:&error];
    NSDictionary *videoSettings = [NSDictionary dictionaryWithObjectsAndKeys:AVVideoCodecH264, AVVideoCodecKey,
                                   [NSNumber numberWithFloat:round(movieWidth)], AVVideoWidthKey,
                                   [NSNumber numberWithFloat:round(movieHeight)], AVVideoHeightKey,nil];
    AVAssetWriterInput* videoWriterInput = [AVAssetWriterInput assetWriterInputWithMediaType:AVMediaTypeVideo outputSettings:videoSettings];
    AVAssetWriterInputPixelBufferAdaptor *adaptor = [AVAssetWriterInputPixelBufferAdaptor assetWriterInputPixelBufferAdaptorWithAssetWriterInput:videoWriterInput sourcePixelBufferAttributes:nil];
    videoWriterInput.expectsMediaDataInRealTime = YES;  // It seems like NO would make more sense here, but keeping at YES to follow example for now
    [videoWriter addInput:videoWriterInput];
    
    // Calculate the expected number of frames (used only for updating the progress indicator)
    
    CMTime frameIncrement = CMTimeMake(1000000,(long) round([videoClip frameRate]*1000000.0f));
    double clipDuration = (double) clipTimeRange.duration.value / (double) clipTimeRange.duration.timescale;
    double frameDuration = (double)frameIncrement.value/(double)frameIncrement.timescale;
    NSUInteger numFrames = (NSUInteger) round(clipDuration/frameDuration);
    
    // Initialize the AVAssetWriter writing session
    
    [videoWriter startWriting];
    [videoWriter startSessionAtSourceTime:kCMTimeZero];
    
    // Initialize progress indicators

    [videoCaptureProgressIndicator setDoubleValue:0.0];
    [videoCaptureProgressIndicator setHidden:NO];
	[videoCaptureProgressIndicator displayIfNeeded];
    [videoCaptureProgressDescription setStringValue:[NSString stringWithFormat:@"Capturing '%@.'",videoClip.clipName]];
    [videoCaptureProgressDescription displayIfNeeded];
    
    // Loop through the range of video times frame-by-frame, grabbing the images and writing them to video
    
    [self goToMasterTime:clipStartTime];
    NSUInteger currentFrame = 1;
    BOOL append_succeeded;
    CGImageRef im = NULL;
    CVPixelBufferRef buffer = NULL;
    
    while (CMTimeCompare([self currentMasterTime],clipEndTime) <= 0) {
        @autoreleasepool {  // this makes the CGImageRef returned from stillCGImagefromVSVideoClip be released after each iteration of the loop, not all of them stored until the whole function ends
            im = [self stillCGImageFromVSVideoClip:videoClip atMasterTime:[self currentMasterTime] showOverlay:YES];
            append_succeeded = FALSE;
            while (!append_succeeded && videoWriter.error == nil) {
                if (adaptor.assetWriterInput.readyForMoreMediaData) {
                    buffer = [self pixelBufferFromCGImage:im size:videoClip.windowController.movieSize];
                    append_succeeded = [adaptor appendPixelBuffer:buffer withPresentationTime:CMTimeSubtract([self currentMasterTime],clipStartTime)];
                    CVPixelBufferRelease(buffer);   // VidSync must release the buffer returned by the previous function. Otherwise, it leaks 7.91mb of memory (for 1920x1080) with every loop iteration
                    if(!append_succeeded && videoWriter.error != nil){
                        NSLog(@"Error in videoWriter's appendPixelBuffer:withPresentationTime: function: %@.", videoWriter.error);
                    }
                } else {
                    [NSThread sleepForTimeInterval:0.05];   // try again if the buffer's busy (in practice this doesn't seem to happen)
                }
            }
            currentFrame++;
            [videoCaptureProgressIndicator setDoubleValue:(double)currentFrame/(double)numFrames];
            [videoCaptureProgressIndicator displayIfNeeded];
            [self stepForwardAll:self];
            [self reSync];
        }
    }
    [videoWriterInput markAsFinished];
    [videoWriter finishWritingWithCompletionHandler:^(void){
        if (videoWriter.status == AVAssetWriterStatusFailed) {
            NSLog(@"Video writing failed.");
            if(videoWriter.error != nil) NSLog(@"Video writer error at completely %@.",videoWriter.error);
        } else if (videoWriter.status == AVAssetWriterStatusCompleted) {
            [videoCaptureProgressDescription setStringValue:@"Finished."];
            [shutterClick play];
            [videoCaptureProgressIndicator setHidden:YES];
        } else {
            NSLog(@"Finished video writing with unexpected status code %ld (neither failed nor completed).",(long)videoWriter.status);
        }
    }];
    
}

/*  Commented-out asynchronous version of captures-with-overlays
 
    FLAW WITH THIS WHOLE VERSION OF THE FUNCTION: It runs asynchronously in another thread, which is great for exporting WITHOUT overlays, but the only way to get the overlays is to jump the video
    to the relevant timecode. So that really defeats the point of doing a speedy asynchronous process, and I'm not sure it would even work inside the completion handlers here. I'm rewriting the function
    to use a much more traditional loop. Making it work asynchronously would require rewriting all the overlay rendering code to draw the overlay for a frame without actually being AT that frame and drawing
    directly into the view. That's completely doable, but would take a while and it's not a high priority.
 
- (void) captureWithOverlayFromVideoClip:(VSVideoClip *)videoClip toFile:(NSString *)destination
{
    float movieWidth = videoClip.windowController.movieSize.width;
    float movieHeight = videoClip.windowController.movieSize.height;
    NSRect imageRect = NSMakeRect(0,0,movieWidth,movieHeight);
    
    CMTime clipStartTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureStartTime];
	CMTime clipEndTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureEndTime];
    CMTimeRange clipTimeRange = CMTimeRangeFromTimeToTime(clipStartTime,clipEndTime);

    NSError *error;
    AVAssetWriter *videoWriter = [[AVAssetWriter alloc] initWithURL: [NSURL fileURLWithPath:destination] fileType:AVFileTypeQuickTimeMovie error:&error];
    NSDictionary *videoSettings = [NSDictionary dictionaryWithObjectsAndKeys:AVVideoCodecH264, AVVideoCodecKey,
                                   [NSNumber numberWithFloat:round(movieWidth)], AVVideoWidthKey,
                                   [NSNumber numberWithFloat:round(movieHeight)], AVVideoHeightKey,nil];
    AVAssetWriterInput* videoWriterInput = [AVAssetWriterInput assetWriterInputWithMediaType:AVMediaTypeVideo outputSettings:videoSettings];
    AVAssetWriterInputPixelBufferAdaptor *adaptor = [AVAssetWriterInputPixelBufferAdaptor assetWriterInputPixelBufferAdaptorWithAssetWriterInput:videoWriterInput sourcePixelBufferAttributes:nil];
    videoWriterInput.expectsMediaDataInRealTime = YES;  // It seems like NO would make more sense here, but keeping at YES to follow example for now
    [videoWriter addInput:videoWriterInput];
    
    // Create the array with the times for all the desired frames
    
    CMTime frameIncrement = CMTimeMake(1000000,(long) round([videoClip frameRate]*1000000.0f));
    double clipDuration = clipTimeRange.duration.value / clipTimeRange.duration.timescale;
    double frameDuration = (double)frameIncrement.value/(double)frameIncrement.timescale;
    __block NSUInteger numFrames = (NSUInteger) round(clipDuration/frameDuration);
    NSLog(@"Requesting %lu frames for clip of duration %1.8f with frame durations of %1.8f",(unsigned long)numFrames,clipDuration,frameDuration);

    CMTime offsetClipStartTime = CMTimeSubtract(clipStartTime,[UtilityFunctions CMTimeFromString:videoClip.syncOffset]);
    NSMutableArray *frameTimes = [NSMutableArray array];
    for (int i=0; i < numFrames; i++) {
        [frameTimes addObject:[NSValue valueWithCMTime:CMTimeAdd(offsetClipStartTime,CMTimeMultiply(frameIncrement,i))]];
    }
    
    // Initialize the AVAssetWriter writing session
    
    [videoWriter startWriting];
    [videoWriter startSessionAtSourceTime:kCMTimeZero];
    
    // Grab the CGImage the video
    
    __block NSUInteger currentFrame = 1;
    __block BOOL append_succeeded;
    
    AVAssetImageGeneratorCompletionHandler handler = ^(CMTime requestedTime,
                                                       CGImageRef im,
                                                       CMTime actualTime,
                                                       AVAssetImageGeneratorResult result,
                                                       NSError *error){
        if (result == AVAssetImageGeneratorSucceeded) {
            append_succeeded = FALSE;
            while (!append_succeeded && videoWriter.error == nil) {
                if (adaptor.assetWriterInput.readyForMoreMediaData) {
                    
                    
                    
                    
                    NSImage *__strong overlayImage = [self currentOverlayImageFromVSVideoClip:videoClip];
                    NSImage *__strong resizedOverlayImage = [NSImage alloc];
                    //[resizedOverlayImage setCacheMode:NSImageCacheNever];
                    
                    float overlayWidth = videoClip.windowController.overlayWidth;
                    float overlayHeight = videoClip.windowController.overlayHeight;
                    if (movieWidth == overlayWidth && movieHeight == overlayHeight) {		// if the overlay is already at the video size, just use it
                        resizedOverlayImage = overlayImage;
                    } else {																// if it needs to be scaled to the video size, draw overlayImage into the resizedOverlayImage
                        resizedOverlayImage = [resizedOverlayImage initWithSize:videoClip.windowController.movieSize];
                        [resizedOverlayImage lockFocus];
                        [overlayImage drawInRect: NSMakeRect(0,0,movieWidth,movieHeight) fromRect: NSMakeRect(0, 0, overlayWidth, overlayHeight) operation: NSCompositeSourceOver fraction: 1.0];
                        [resizedOverlayImage unlockFocus];
                    }
                    returnImage = [returnImage initWithCGImage:rawMovieImage size:NSZeroSize];
                    [returnImage lockFocus];
                    [resizedOverlayImage drawAtPoint:NSMakePoint(0,0) fromRect:imageRect operation:NSCompositeSourceOver fraction:1.0];
                    [returnImage unlockFocus];
                    [returnImage CGImageForProposedRect:&imageRect context:NULL hints:NULL];
                    
                    
                    
                    
                    
                    
                    
                    append_succeeded = [adaptor appendPixelBuffer:[self pixelBufferFromCGImage:im] withPresentationTime:CMTimeSubtract(requestedTime,clipStartTime)];
                    
                    if(append_succeeded){
                        NSLog(@"Successfully appended image to buffer for time %@",[UtilityFunctions CMStringFromTime:CMTimeSubtract(requestedTime,clipStartTime)]);
                    } else {
                        if(videoWriter.error != nil) {
                            NSLog(@"Unresolved videoWriter error %@.", videoWriter.error);
                        }
                    }
                } else {
                    NSLog(@"Sleeping thread for 0.05 seconds because adapter was not ready for more media data.");
                    [NSThread sleepForTimeInterval:0.05];
                }
            }
            NSLog(@"A frame was successfully generated for frame %lu of %lu at requested clip time (not master time) %@.",(unsigned long)currentFrame,(unsigned long)numFrames,[UtilityFunctions CMStringFromTime:requestedTime]);
        } else if (result == AVAssetImageGeneratorFailed && error != nil) {
            NSLog(@"Frame image generation for requested clip time (not master time) %@ failed with error: %@.",[UtilityFunctions CMStringFromTime:requestedTime],exportSession.error);
        }
        if (currentFrame == numFrames) {
            [videoWriterInput markAsFinished];
            [videoWriter finishWritingWithCompletionHandler:^(void){
                if (videoWriter.status == AVAssetWriterStatusFailed) {
                    NSLog(@"Video writing failed.");
                    if(videoWriter.error != nil) NSLog(@"Video writer error at completely %@.",videoWriter.error);
                } else if (videoWriter.status == AVAssetWriterStatusCompleted) {
                    NSLog(@"Finished writing, status: completed.");
                } else {
                    NSLog(@"Finished writing with status code %ld.",(long)videoWriter.status);
                }
            }];
        }
        currentFrame++;
    };
    
    [videoClip.windowController.assetImageGenerator generateCGImagesAsynchronouslyForTimes:frameTimes completionHandler:handler];

}
*/

/*-----------------------------------------------------Source--------------------------------------------------------------------
 
 The pixelBufferFromCGImage function is based on the img-to-video.xcodeproj
 example project by Carmen Ferrara, downloaded from: https://github.com/caferrara/img-to-video
 
 --------------------------------------------------------------------------------------------------------------------------------*/

- (CVPixelBufferRef) pixelBufferFromCGImage:(CGImageRef)image size:(NSSize)inSize {
    
    CGSize size = CGSizeMake(inSize.width, inSize.height);
    
    NSDictionary *options = [NSDictionary dictionaryWithObjectsAndKeys:
                             [NSNumber numberWithBool:YES], kCVPixelBufferCGImageCompatibilityKey,
                             [NSNumber numberWithBool:YES], kCVPixelBufferCGBitmapContextCompatibilityKey,
                             nil];
    CVPixelBufferRef pxbuffer = NULL;
    
    CVReturn status = CVPixelBufferCreate(kCFAllocatorDefault,
                                          size.width,
                                          size.height,
                                          kCVPixelFormatType_32ARGB,
                                          (__bridge CFDictionaryRef) options,
                                          &pxbuffer);
    if (status != kCVReturnSuccess){
        NSLog(@"Failed to create pixel buffer");
    }
    
    CVPixelBufferLockBaseAddress(pxbuffer, 0);
    void *pxdata = CVPixelBufferGetBaseAddress(pxbuffer);
    
    CGColorSpaceRef rgbColorSpace = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(pxdata, size.width, size.height, 8, 4*size.width, rgbColorSpace, kCGImageAlphaPremultipliedFirst);
    CGContextConcatCTM(context, CGAffineTransformMakeRotation(0));
    CGContextDrawImage(context, CGRectMake(0, 0, CGImageGetWidth(image), CGImageGetHeight(image)), image);
    CGColorSpaceRelease(rgbColorSpace);
    CGContextRelease(context);
    
    CVPixelBufferUnlockBaseAddress(pxbuffer, 0);
    
    return pxbuffer;
}

#pragma mark
#pragma mark Fuctions for Still and Movies

- (CGImageRef) stillCGImageFromVSVideoClip:(VSVideoClip *)videoClip atMasterTime:(CMTime)masterTime showOverlay:(BOOL)showOverlay
{
	NSImage *__strong returnImage = [NSImage alloc];
    //[returnImage setCacheMode:NSImageCacheNever];
    float movieWidth = videoClip.windowController.movieSize.width;
    float movieHeight = videoClip.windowController.movieSize.height;
    NSRect imageRect = NSMakeRect(0,0,movieWidth,movieHeight);
    
    // Grab the CGImage the video
    
    CMTime offset = [UtilityFunctions CMTimeFromString:videoClip.syncOffset];
	CMTime movieTime = CMTimeSubtract(masterTime,offset);
    CMTime actualCopiedTime;
    NSError *err;
    // Note: I'm not responsible for CGImageReleasing CGImageRefs unless I manully created them using some function like CGImageMaskCreate etc. If they come from some AVFoundation function or something they're autoreleased.

    NSImage *__strong overlayImage = [self currentOverlayImageFromVSVideoClip:videoClip];
    NSImage *__strong resizedOverlayImage = [NSImage alloc];
    
    CGImageRef rawMovieImage = [videoClip.windowController.assetImageGenerator copyCGImageAtTime:movieTime actualTime:&actualCopiedTime error:&err];
    if (err != nil) [NSApp presentError:err];
    returnImage = [returnImage initWithCGImage:rawMovieImage size:NSZeroSize];

    // Add the overlay if necessary

    if (showOverlay) {
		float overlayWidth = videoClip.windowController.overlayWidth;
		float overlayHeight = videoClip.windowController.overlayHeight;
		if (movieWidth == overlayWidth && movieHeight == overlayHeight) {		// if the overlay is already at the video size, just use it
			resizedOverlayImage = overlayImage;
		} else {																// if it needs to be scaled to the video size, draw overlayImage into the resizedOverlayImage
			resizedOverlayImage = [resizedOverlayImage initWithSize:videoClip.windowController.movieSize];
			[resizedOverlayImage lockFocus];
			[overlayImage drawInRect: NSMakeRect(0,0,movieWidth,movieHeight) fromRect: NSMakeRect(0, 0, overlayWidth, overlayHeight) operation: NSCompositeSourceOver fraction: 1.0];
			[resizedOverlayImage unlockFocus];
		}
		[returnImage lockFocus];
        [resizedOverlayImage drawAtPoint:NSMakePoint(0,0) fromRect:imageRect operation:NSCompositeSourceOver fraction:1.0];
		[returnImage unlockFocus];
    } else {
        return [returnImage CGImageForProposedRect:&imageRect context:NULL hints:NULL];
    }
	return [returnImage CGImageForProposedRect:&imageRect context:NULL hints:NULL];
}

- (NSImage*)currentOverlayImageFromVSVideoClip:(VSVideoClip *)videoClip
{
	VideoOverlayView *overlayView = videoClip.windowController.overlayView;
	[overlayView lockFocus];
	NSBitmapImageRep *imageRep = [[NSBitmapImageRep alloc] initWithFocusedViewRect:[overlayView bounds]];
	NSDictionary *imageProperties = [NSDictionary dictionaryWithObject:[NSNumber numberWithFloat:1.0] forKey:NSImageGamma];
	NSImage *overlayImage = [NSImage alloc];
    overlayImage = [overlayImage initWithData:[imageRep representationUsingType:NSPNGFileType properties:imageProperties]];
	[overlayView unlockFocus];
	return overlayImage;
}


- (CGImageRef) highQualityStillFromVSVideoClip:(VSVideoClip *)videoClip atMasterTime:(CMTime)masterTime
{
    CMTime offset = [UtilityFunctions CMTimeFromString:videoClip.syncOffset];
	CMTime movieTime = CMTimeSubtract(masterTime,offset);
    CMTime actualCopiedTime;
    NSError *err;
    CGImageRef image = [videoClip.windowController.assetImageGenerator copyCGImageAtTime:movieTime actualTime:&actualCopiedTime error:&err];
    if (err != nil) [NSApp presentError:err];
    return image;
}

- (void)saveNSImageAsJpeg:(NSImage*)img destination:(NSString*)destination overwriteWarnings:(BOOL)overwriteWarnings
{
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create image directory if it doesn't exist yet
	bool doWrite = TRUE;
	if (overwriteWarnings && [fm fileExistsAtPath:destination]) {
		NSInteger alertResult = NSRunAlertPanel(@"Overwrite file?",@"The file you would be writing already exists.  Overwrite it?",@"No",@"Yes",nil);
		if (alertResult == 1) doWrite = FALSE;		
	} 
	if (doWrite) {
		NSData *imageData = [img TIFFRepresentation];
		NSBitmapImageRep *imageRep = [NSBitmapImageRep imageRepWithData:imageData];
		NSDictionary *imageProps = [NSDictionary dictionaryWithObject:[NSNumber numberWithFloat:1.0] forKey:NSImageCompressionFactor];
		imageData = [imageRep representationUsingType:NSJPEGFileType properties:imageProps];
		BOOL result = [imageData writeToFile:destination atomically:YES];
        if (!result) NSLog(@"File write failed for destination %@",destination);
	}
}

- (NSString *)fileNameForExportedFileFromClip:(VSVideoClip *)videoClip withExtension:(NSString *)extension
{
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create capture directory if it doesn't exist yet
	BOOL includeProjectName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeProjectNameInCapturedFileName"] boolValue];
	BOOL includeMasterTimecode = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeMasterTimecodeInCapturedFileName"] boolValue];
	BOOL includeClipName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeClipNameInCapturedFileName"] boolValue];
	BOOL separateClipsByFolder = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"separateClipsByFolder"] boolValue];
	BOOL createFolderForProject = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"createFolderForProjectCaptures"] boolValue];
	NSString *customText = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"capturedFileNameCustomText"];
	NSMutableString *filePath = [NSMutableString new];
	NSString *timeString1 = nil;
	if ([extension isEqualToString:@"jpg"]) {
		[filePath appendString:self.project.capturePathForStills];
		timeString1 = [self currentMasterTimeString];
	} else if ([extension isEqualToString:@"mov"] || [extension isEqualToString:@"mp4"] || [extension isEqualToString:@"m4v"]) {
		[filePath appendString:self.project.capturePathForMovies];
		timeString1 = [NSString stringWithFormat:@"%@ to %@", self.project.movieCaptureStartTime, self.project.movieCaptureEndTime];
	}
	if (createFolderForProject) [filePath appendString:[NSString stringWithFormat:@"/%@",self.project.name]];
	if (separateClipsByFolder) [filePath appendString:[NSString stringWithFormat:@"/%@",videoClip.clipName]];
	if (![fm fileExistsAtPath:filePath]) [fm createDirectoryAtPath:filePath withIntermediateDirectories:YES attributes:nil error:NULL];
	[filePath appendString:@"/"];
	if (includeProjectName) [filePath appendString:[NSString stringWithFormat:@"%@ - ",self.project.name]];
	if (includeMasterTimecode) {
		NSString *timeString2 = [timeString1 stringByReplacingOccurrencesOfString:@":" withString:@"-"];
		NSString *timeString3 = [timeString2 stringByReplacingOccurrencesOfString:@"/" withString:@"+"]; // : gets replaced by / in filenames
		[filePath appendString:[NSString stringWithFormat:@"(%@) - ",timeString3]];
	}
	if (![customText isEqualToString:@""]) [filePath appendString:[NSString stringWithFormat:@"%@ - ",customText]];
	if (includeClipName) [filePath appendString:videoClip.clipName];
	if ([filePath isEqualToString:@""]) [filePath appendString:@"Untitled"];	// give it a default if all naming values are turned off
	[filePath appendString:[NSString stringWithFormat:@".%@",extension]];
	return filePath;
}

@end
