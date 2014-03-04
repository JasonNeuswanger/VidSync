//
//  VideoClipArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/26/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

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
		NSRunAlertPanel(@"New Clip Needs a Name",@"You can't add the clip without first giving it a name.",@"Ok",nil,nil);
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
	// Close the window before deleting it
	VideoWindowController *__weak vwc = [[[self selectedObjects] objectAtIndex:0] windowController];
    [vwc removeObserver:document forKeyPath:@"playerView.player.rate"];
	[vwc close];
    [document removeWindowController:vwc];
	[super remove:sender];
    if ([document.project.videoClips count] > 0) {
        if ([document.project.videoClips count] == 1) {
            [document.project setMasterClip:[document.project.videoClips anyObject]];   // If only one video is left, set it as the master clip
        }
        for (VSVideoClip *clip in document.project.videoClips) [clip.windowController processSynchronizationStatus];
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
