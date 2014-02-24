//
//  VideoClipArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/26/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VideoClipArrayController.h"

@implementation VideoClipArrayController

- (IBAction) add:(id)sender  // need to make a comparable custom method for fetch, and for just listing, or for when the whole thing is opened...
{
	if (![[newClipName stringValue] isEqualToString:@""]) {	// if there's a name for the new clip, process it
		NSOpenPanel *movieOpenPanel = [NSOpenPanel openPanel];
		[movieOpenPanel setCanChooseFiles:YES];
		[movieOpenPanel setCanChooseDirectories:NO];
		[movieOpenPanel setAllowsMultipleSelection:NO];
		if ([movieOpenPanel runModal]) {
			VSVideoClip *newClip = [NSEntityDescription insertNewObjectForEntityForName:@"VSVideoClip" inManagedObjectContext:[self managedObjectContext]];	
			NSEntityDescription *newCalibrationEntity = [NSEntityDescription entityForName:@"VSCalibration" inManagedObjectContext:[self managedObjectContext]];
			newClip.calibration = [[VSCalibration alloc] initWithEntity:newCalibrationEntity insertIntoManagedObjectContext:[self managedObjectContext]];
			newClip.clipName = [newClipName stringValue];
			newClip.fileName = [[[movieOpenPanel URLs] objectAtIndex:0] path];
			[self addObject:newClip];
			VideoWindowController *newVideoWindowController = [[VideoWindowController alloc] initWithVideoClip:newClip inManagedObjectContext:[self managedObjectContext]];
			if (newVideoWindowController != nil) {
                [document addWindowController:newVideoWindowController];
                [newVideoWindowController resizeVideoToFactor:1.0];
            }
            if (!newClip.project.masterClip) [newClip setAsMaster];
			[newClip setMasterControls];
			[newClipName setStringValue:@""];
			[newClipNamePanel performClose:self];
		}
	} else {	// if the clip doesn't have a name, tell the user to add one
		NSRunAlertPanel(@"New Clip Needs a Name",@"You can't add the clip without first giving it a name.",@"Ok",nil,nil);
	}
}

- (void) keyWindowDidChange:(NSNotification *)notification
{
	if ([[[notification object] windowController] isKindOfClass:[VideoWindowController class]]) {	// ignore the main document window
		VideoWindowController *__weak vwc = [[notification object] windowController];
		[self setSelectedObjects:[NSArray arrayWithObjects:vwc.videoClip,nil]];
	}
}

- (void)remove:(id)sender
{
	// Close the window before deleting it
	VideoWindowController *__weak vwc = [[[self selectedObjects] objectAtIndex:0] windowController];
	[vwc close];
	[super remove:sender];
	
}

@end
