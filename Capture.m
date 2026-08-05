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


#import "VidSyncDocument.h"
#import "VSClipExportTask.h"
#import "VSExportQueue.h"

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
			NSAlert *alert = [[NSAlert alloc] init];
			[alert setMessageText:@"Error saving frames."];
			[alert setInformativeText:@"The frame image generated was not valid."];
			[alert addButtonWithTitle:@"Ok"];
			[alert setAlertStyle:NSAlertStyleWarning];
			[alert runModal];
		}
	}
	if (success) [shutterClick play];
}

- (IBAction)capturePortraits:(id)sender
{
    if ([[allPortraitsArrayController arrangedObjects] count] > 0) {
        NSFileManager *fm = [NSFileManager defaultManager];
        NSString *fileSafeProjectName = [[self.project.name stringByReplacingOccurrencesOfString:@":" withString:@"-"] stringByReplacingOccurrencesOfString:@"/" withString:@"+"];
        NSString *portraitsFolder = [NSString stringWithFormat:@"%@/%@ Portraits",self.project.capturePathForStills,fileSafeProjectName];
        if (![fm fileExistsAtPath:portraitsFolder]) [fm createDirectoryAtPath:portraitsFolder withIntermediateDirectories:YES attributes:nil error:NULL];
        for (VSTrackedObjectPortrait *portrait in [allPortraitsArrayController arrangedObjects]) {
            NSImage *portraitImage = [portrait image];
            if ([portraitImage isValid]) {
                NSMutableString *filePath = [NSMutableString new];
                [filePath appendString:self.project.capturePathForStills];
                // Length check rather than isEqualToString: a nil name passed the old test and wrote "((null))" into the
                // filename. The source clip can also be gone (deleted clip nullifies the relationship), so its name gets
                // the same guard, plus the filename-safe substitutions the other parts already receive.
                NSString *nameString = ([portrait.trackedObject.name length] == 0) ? @"" : [NSString stringWithFormat:@" (%@)",portrait.trackedObject.name];
                NSString *fileSafeTimecode = [[(portrait.timecode ?: @"") stringByReplacingOccurrencesOfString:@":" withString:@"-"] stringByReplacingOccurrencesOfString:@"/" withString:@"+"];
                NSString *fileSafeClipName = [[(portrait.sourceVideoClip.clipName ?: @"unknown clip") stringByReplacingOccurrencesOfString:@":" withString:@"-"] stringByReplacingOccurrencesOfString:@"/" withString:@"+"];
                [filePath appendFormat:@"/%@ Portraits/%@ %@%@ from %@ (%@) at %@.jpg",fileSafeProjectName,portrait.trackedObject.type.name,portrait.trackedObject.index,nameString,fileSafeProjectName,fileSafeClipName,fileSafeTimecode];
                [self saveNSImageAsJpeg:portraitImage destination:filePath overwriteWarnings:NO];
            }
        }
        [shutterClick play];
    } else {
        NSAlert *alert = [NSAlert new];
        alert.messageText = @"There are no portraits yet";
        alert.informativeText = @"You have to create portraits of objects before you can export them.";
        [alert runModal];
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

- (NSString *)fileSafeProjectName
{
	// Returns an empty string, not "(null)", for a project that has never been named: name is never initialized,
	// and the old inline version of this substitution formatted that nil straight into a path.
	return [[(self.project.name ?: @"") stringByReplacingOccurrencesOfString:@":" withString:@"-"] stringByReplacingOccurrencesOfString:@"/" withString:@"+"];
}

- (NSString *)folderForCapturedFilesInPath:(NSString *)basePath
{
	// Shared with the capture file naming, so the "Open in Finder" buttons can't reveal a folder the captures
	// don't go into. Only the folder is decided here; the captured file names do their own naming.
	BOOL createFolderForProject = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"createFolderForProjectCaptures"] boolValue];
	NSString *folder = basePath ?: @"";
	NSString *projectFolderName = [self fileSafeProjectName];
	if (createFolderForProject && [projectFolderName length] > 0) folder = [folder stringByAppendingPathComponent:projectFolderName];
	return [folder stringByStandardizingPath];
}

- (IBAction)openCapturePathInFinder:(id)sender
{
	NSString *folderToShow = nil;
	if ([sender tag] == 1) {
		folderToShow = [self folderForCapturedFilesInPath:self.project.capturePathForStills];
	} else if ([sender tag] == 2) {
		folderToShow = [self folderForCapturedFilesInPath:self.project.capturePathForMovies];
	} else if ([sender tag] == 3) {
		folderToShow = [self folderForExportedFiles];	// asked of the exporter itself, so the button always shows the folder the exports actually land in
	}
	if ([folderToShow length] == 0) {
		[UtilityFunctions InformUser:@"No folder has been chosen for these files yet, so there's nothing to show in the Finder." withTitle:@"No folder chosen"];
		return;
	}

	NSFileManager *fm = [NSFileManager defaultManager];	// the folder won't exist yet if nothing has been written into it
	NSError *error = nil;
	if (![fm fileExistsAtPath:folderToShow] && ![fm createDirectoryAtPath:folderToShow withIntermediateDirectories:YES attributes:nil error:&error]) {
		// Previously this failure, and the failed reveal that followed it, were both silent, so an unavailable
		// folder (one on a disconnected drive, most often) made the button look broken.
		[UtilityFunctions InformUser:[NSString stringWithFormat:@"The folder %@ doesn't exist and couldn't be created, so it can't be shown in the Finder. %@",folderToShow,[error localizedDescription] ?: @""] withTitle:@"Folder unavailable"];
		return;
	}

	if (![[NSWorkspace sharedWorkspace] selectFile:folderToShow inFileViewerRootedAtPath:@""]) {
		[UtilityFunctions InformUser:[NSString stringWithFormat:@"The Finder couldn't show the folder %@.",folderToShow] withTitle:@"Couldn't open folder"];
	}
}

- (IBAction)captureVideoClips:(id)sender
{
	// Builds one export task per selected clip and hands them to the document's export queue, which
	// runs them in the background (one at a time) with a per-clip progress bar in its own window.
	// More clips can be queued at any time, including while earlier ones are still exporting.
	NSFileManager *fm = [NSFileManager defaultManager];
	BOOL showOverlaysInExportedFiles = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeOverlaysInExportedFiles"] boolValue];
	BOOL useHEVC = ([[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"captureVideoCodec"] integerValue] == 1);
	BOOL includeSound = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeSoundInCapturedVideos"] boolValue];
	NSMutableSet *clipsToExportFrom = [NSMutableSet set];
	if ([[exportClipSelectionPopUpButton selectedItem] representedObject] == nil) {								// if the null placeholder "All Clips" is selected, select all clips
		for  (VSVideoClip *videoClip in self.project.videoClips) [clipsToExportFrom addObject:videoClip];
	} else {																									// otherwise, select only the clip(s) with the selected name
		NSString *exportClipName = [[exportClipSelectionPopUpButton selectedItem] representedObject];
		for  (VSVideoClip *videoClip in self.project.videoClips) if ([videoClip.clipName isEqualToString:exportClipName]) [clipsToExportFrom addObject:videoClip];
	}
	CMTime clipStartTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureStartTime];
	CMTime clipEndTime = [UtilityFunctions CMTimeFromString:self.project.movieCaptureEndTime];
	if (CMTimeCompare(clipStartTime,clipEndTime) >= 0) {
		[UtilityFunctions InformUser:@"The video capture start time must be before the end time. Set both on the Capture tab before capturing." withTitle:@"Invalid capture time range"];
		return;
	}
	for (VSVideoClip *videoClip in clipsToExportFrom) {
		BOOL doWrite = YES;
		// Every video export is a clean .mp4 (H.264 or H.265); VidSync no longer writes .mov files.
		NSString *destination = [self fileNameForExportedFileFromClip:videoClip withExtension:@"mp4"];
		if ([fm fileExistsAtPath:destination]) {
			NSAlert *alert = [[NSAlert alloc] init];
			[alert setMessageText:@"Overwrite file?"];
			[alert setInformativeText:@"The file you would be writing already exists. Overwrite it?"];
			[alert addButtonWithTitle:@"Yes"];
			[alert addButtonWithTitle:@"No"];
			[alert setAlertStyle:NSAlertStyleWarning];
			NSModalResponse nudgeWarningResult = [alert runModal];
			if (nudgeWarningResult == NSAlertFirstButtonReturn) {
				NSError *fileRemovalError;
				[fm removeItemAtPath:destination error:&fileRemovalError];
			} else {
				doWrite = NO;
			}
		}
		if ([destination length] == 0) doWrite = NO;
		if (doWrite) {
			VSClipExportTaskType type = (showOverlaysInExportedFiles) ? VSClipExportTaskTypeOverlayClip : VSClipExportTaskTypePlainClip;
			VSClipExportTask *task = [VSClipExportTask taskWithType:type
													  videoClip:videoClip
													 outputPath:destination
												startMasterTime:clipStartTime
												  endMasterTime:clipEndTime];
			task.useHEVC = useHEVC;
			task.includeSound = includeSound;
			[[self exportQueueCreatingIfNeeded] enqueueTask:task];
		}
	}
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
	
	NSError *err = nil;
	CGImageRef rawMovieImage = [videoClip.windowController.assetImageGenerator copyCGImageAtTime:movieTime actualTime:&actualCopiedTime error:&err];
	if (err != nil || rawMovieImage == NULL) {
		// Without this return, the NULL image built a zero-size NSImage whose lockFocus threw an
		// exception out of the capture button's mouse-tracking loop. The caller's invalid-image
		// alert handles the NULL result.
		if (err != nil) [NSApp presentError:err];
		return NULL;
	}

	// Add the overlay if necessary

	if (showOverlay) {
		// The overlay is rendered offscreen at the video's native resolution for the requested master
		// time (the same renderer the export queue uses), so stills no longer depend on the on-screen
		// window's size or on the video actually sitting at that timecode.
		CGImageRef overlayCGImage = [videoClip.windowController.overlayView newOverlayImageForExportAtMasterTime:masterTime pixelSize:videoClip.windowController.movieSize];
		returnImage = [returnImage initWithCGImage:rawMovieImage size:NSZeroSize];
		CGImageRelease(rawMovieImage);  // NSImage now retains it; release the Create reference from copyCGImageAtTime
		if (overlayCGImage != NULL) {
			NSImage *overlayImage = [[NSImage alloc] initWithCGImage:overlayCGImage size:NSZeroSize];
			CGImageRelease(overlayCGImage);
			[returnImage lockFocus];
			[overlayImage drawInRect:imageRect fromRect:NSZeroRect operation:NSCompositingOperationSourceOver fraction:1.0];
			[returnImage unlockFocus];
		}
		return [returnImage CGImageForProposedRect:&imageRect context:NULL hints:NULL];
	} else {
		returnImage = [[NSImage alloc] initWithCGImage:rawMovieImage size:NSZeroSize];
		CGImageRelease(rawMovieImage);  // NSImage now retains it; release the Create reference from copyCGImageAtTime
		return [returnImage CGImageForProposedRect:&imageRect context:NULL hints:NULL];
	}
}

- (void)saveNSImageAsJpeg:(NSImage*)img destination:(NSString*)destination overwriteWarnings:(BOOL)overwriteWarnings
{
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create image directory if it doesn't exist yet
	bool doWrite = TRUE;
	if (overwriteWarnings && [fm fileExistsAtPath:destination]) {
		doWrite = [UtilityFunctions ConfirmAction:@"The file you would be writing already exists.  Overwrite it?" withTitle:@"Overwrite file?"];
	}
	if (doWrite) {
		NSData *imageData = [img TIFFRepresentation];
		NSBitmapImageRep *imageRep = [NSBitmapImageRep imageRepWithData:imageData];
		NSDictionary *imageProps = [NSDictionary dictionaryWithObject:[NSNumber numberWithFloat:1.0] forKey:NSImageCompressionFactor];
		imageData = [imageRep representationUsingType:NSBitmapImageFileTypeJPEG properties:imageProps];
		BOOL result = [imageData writeToFile:destination atomically:YES];
		if (!result) [UtilityFunctions InformUser:[NSString stringWithFormat:@"File write failed for destination %@",destination] withTitle:@"Write failed"];
	}
}

- (NSString *)fileNameForExportedFileFromClip:(VSVideoClip *)videoClip withExtension:(NSString *)extension
{
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create capture directory if it doesn't exist yet
	BOOL includeProjectName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeProjectNameInCapturedFileName"] boolValue];
	BOOL includeMasterTimecode = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeMasterTimecodeInCapturedFileName"] boolValue];
	BOOL includeClipName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeClipNameInCapturedFileName"] boolValue];
	BOOL separateClipsByFolder = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"separateClipsByFolder"] boolValue];
	NSString *customText = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"capturedFileNameCustomText"];
	NSString *fileSafeProjectName = [self fileSafeProjectName];
	NSMutableString *filePath = [NSMutableString new];
	NSString *timeString1 = nil;
	// Compared case-insensitively, with movies as the catch-all: the old exact-match list ("mov", "mp4",
	// "m4v") missed uppercase extensions from cameras, fell through both branches, and built a garbage
	// path with "((null))" in the name rooted at /.
	if ([[extension lowercaseString] isEqualToString:@"jpg"]) {
		[filePath appendString:[self folderForCapturedFilesInPath:self.project.capturePathForStills]];
		timeString1 = [self currentMasterTimeString];
	} else {
		[filePath appendString:[self folderForCapturedFilesInPath:self.project.capturePathForMovies]];
		timeString1 = [NSString stringWithFormat:@"%@ to %@", self.project.movieCaptureStartTime ?: @"", self.project.movieCaptureEndTime ?: @""];
	}
	if (separateClipsByFolder) [filePath appendString:[NSString stringWithFormat:@"/%@",videoClip.clipName]];
	if (![fm fileExistsAtPath:filePath]) [fm createDirectoryAtPath:filePath withIntermediateDirectories:YES attributes:nil error:NULL];
	[filePath appendString:@"/"];
	if (includeProjectName) [filePath appendString:[NSString stringWithFormat:@"%@ - ", fileSafeProjectName]];
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
