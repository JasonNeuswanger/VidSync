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


#import "VideoClipArrayController.h"

@implementation VideoClipArrayController

@synthesize mainTableView;
@synthesize nameOfNewClip;

- (IBAction) add:(id)sender  // need to make a comparable custom method for fetch, and for just listing, or for when the whole thing is opened...
{
	if (![nameOfNewClip isEqualToString:@""]) {	// if there's a name for the new clip, process it
		NSOpenPanel *movieOpenPanel = [NSOpenPanel openPanel];
		[movieOpenPanel setCanChooseFiles:YES];
		[movieOpenPanel setCanChooseDirectories:NO];
		[movieOpenPanel setAllowsMultipleSelection:NO];
		// Set the previously used movie directory to be the default location
		NSString *previousDirectory = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"movieOpenDirectory"];
		BOOL directoryExists;
		if ([[NSFileManager defaultManager] fileExistsAtPath:previousDirectory isDirectory:&directoryExists] && directoryExists) {
			[movieOpenPanel setDirectoryURL:[NSURL fileURLWithPath:previousDirectory]];
		}
		// Run the panel
		if ([movieOpenPanel runModal]) {
			VSVideoClip *newClip = [NSEntityDescription insertNewObjectForEntityForName:@"VSVideoClip" inManagedObjectContext:[self managedObjectContext]];
			NSEntityDescription *newCalibrationEntity = [NSEntityDescription entityForName:@"VSCalibration" inManagedObjectContext:[self managedObjectContext]];
			newClip.calibration = [[VSCalibration alloc] initWithEntity:newCalibrationEntity insertIntoManagedObjectContext:[self managedObjectContext]];
			newClip.clipName = nameOfNewClip;
			newClip.fileName = [[[movieOpenPanel URLs] objectAtIndex:0] path];
			[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[[[[movieOpenPanel URLs] objectAtIndex:0] path] stringByDeletingLastPathComponent] forKey:@"movieOpenDirectory"];
			[self addObject:newClip];
			VideoWindowController *newVideoWindowController = [[VideoWindowController alloc] initWithVideoClip:newClip inManagedObjectContext:[self managedObjectContext]];
			if (newVideoWindowController != nil) {
				[document observeWindowControllerVideoRate:newVideoWindowController];
				[document addWindowController:newVideoWindowController];
			}
			if (!newClip.project.masterClip) newClip.project.masterClip = newClip;
			self.nameOfNewClip = nil;
			[newClipNamePanel performClose:self];
		}
	} else {	// if the clip doesn't have a name, tell the user to add one
		[UtilityFunctions InformUser:@"You can't add the clip without first giving it a name." withTitle:@"New Clip Needs a Name"];
	}
}

- (void) keyWindowDidChange:(NSNotification *)notification
{
	if ([[notification object] windowController] != nil) {
		if ([[[notification object] windowController] isKindOfClass:[VideoWindowController class]]) {	// ignore the main document window
			VideoWindowController *__weak vwc = [[notification object] windowController];
			[self setSelectedObjects:[NSArray arrayWithObjects:vwc.videoClip,nil]];
		}
	}
}

- (void)remove:(id)sender
{
	if ([[self selectedObjects] count] == 0) return;
	VSVideoClip *clipToDelete = [[self selectedObjects] objectAtIndex:0];
	NSString *confirmQuestion = [NSString stringWithFormat:@"Are you sure you want to delete clip %@?", clipToDelete.clipName];
	bool shouldDeleteClip = [UtilityFunctions ConfirmAction:confirmQuestion  withTitle:@"Are you sure?"];
	if (shouldDeleteClip) {
		// Close the window before deleting it
		@try {
			[clipToDelete.windowController removeObserver:document forKeyPath:@"playerView.player.rate"];
		} @catch (id exception) {
		}
		[clipToDelete.windowController close];
		[document removeWindowController:clipToDelete.windowController];
		[super remove:sender];
		if ([document.project.videoClips count] > 0) {
			if ([document.project.videoClips count] == 1) {
				[document.project setMasterClip:[document.project.videoClips anyObject]];   // If only one video is left, set it as the master clip
			}
			for (VSVideoClip *clip in document.project.videoClips) [clip.windowController processSynchronizationStatus];
		}
		[document.project updateFrameRateWarning];   // the clip that disagreed may have been the one just deleted
		[document refreshOverlaysOfAllClips:self];
	}
}

- (void) dealloc
{
	[[NSNotificationCenter defaultCenter] removeObserver:self];
}

#pragma mark
#pragma mark Delegate method for the name box

- (void) controlTextDidChange:(NSNotification *)note    // Updating the name makes the binding on the "Choose file" button enable it as soon as the user has typed something in the name
{
	NSTextField *changedField = [note object];
	self.nameOfNewClip = [changedField stringValue];
}

@end
