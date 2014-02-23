//
//  CalibDistortionPtArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/22/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "CalibDistortionPtArrayController.h"

@implementation CalibDistortionPtArrayController

- (void)remove:(id)sender
{
	if ([[self selectedObjects] count] > 0) {
		VSDistortionPoint *pointToRemove = [[self selectedObjects] objectAtIndex:0];
        VideoWindowController *vwc = pointToRemove.distortionLine.calibration.videoClip.windowController;
		[super remove:sender];
		[vwc refreshOverlay];
        
        [distortionLinesController.mainTableView display];
        
	}
}

@end
