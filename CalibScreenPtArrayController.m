//
//  CalibScreenPtArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/30/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "CalibScreenPtArrayController.h"


@implementation CalibScreenPtArrayController

- (void)remove:(id)sender
{
	if ([[self selectedObjects] count] > 0) {
		VSCalibrationPoint *pointToRemove = [[self selectedObjects] objectAtIndex:0];
		VSVideoClip *clipToUpdate = pointToRemove.calibration.videoClip;
		[super remove:sender];
		[clipToUpdate.windowController refreshOverlay];
	}
}

@end
