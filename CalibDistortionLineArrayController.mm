//
//  CalibDistortionLineArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/18/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import "opencv2/opencv.hpp"

#import "CalibDistortionLineArrayController.h"


@implementation CalibDistortionLineArrayController

- (IBAction) add:(id)sender
{	
	VSDistortionLine *newLine = [NSEntityDescription insertNewObjectForEntityForName:@"VSDistortionLine" inManagedObjectContext:[self managedObjectContext]];
	newLine.timecode = [document currentMasterTimeString];
	[self addObject:newLine];
}

- (void) remove:(id)sender
{
    VSDistortionLine *lineToRemove = [[self selectedObjects] objectAtIndex:0];
    VideoWindowController *__weak vwc = lineToRemove.calibration.videoClip.windowController;
    [super remove:lineToRemove];
    [vwc refreshOverlay];
}

- (IBAction) goToLine:(id)sender
{
	NSString *timecodeString = [[[self selectedObjects] objectAtIndex:0] timecode];
	[document goToMasterTime:[UtilityFunctions CMTimeFromString:timecodeString]];
}

- (void) addNewAutodetectedLineWithNumber:(int)number ofPoints:(void *)points
{
    CvPoint2D32f *cvpoints = (CvPoint2D32f *) points;  // type casting because the input array must be void, because the OpenCV types aren't accessible from the c headers

	VSDistortionLine *newLine = [NSEntityDescription insertNewObjectForEntityForName:@"VSDistortionLine" inManagedObjectContext:[self managedObjectContext]];
	newLine.timecode = [document currentMasterTimeString];
    [self addObject:newLine];
    VSDistortionPoint *newDistortionPoint;
    for (int i=0; i<number; i++) {
		newDistortionPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSDistortionPoint" inManagedObjectContext:[self managedObjectContext]]; 
        newDistortionPoint.screenX = [NSNumber numberWithDouble:cvpoints[i].x];
		newDistortionPoint.screenY = [NSNumber numberWithFloat:cvpoints[i].y];
		newDistortionPoint.index = [NSNumber numberWithInt:i];
		newDistortionPoint.distortionLine = newLine;
    }
//    [newLine.calibration.videoClip.windowController refreshOverlay];
}

- (void) appendPointToSelectedLineAt:(NSPoint)coords
{
	if ([[self selectedObjects] count] > 0) {
        VSDistortionLine *selectedLine = [[self selectedObjects] objectAtIndex:0];
		int highestIndex = 0;
		for (VSDistortionPoint *existingPoint in selectedLine.distortionPoints) if ([existingPoint.index intValue] > highestIndex) highestIndex = [existingPoint.index intValue];
		VSDistortionPoint *newDistortionPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSDistortionPoint" inManagedObjectContext:[self managedObjectContext]]; 
		newDistortionPoint.screenX = [NSNumber numberWithFloat:coords.x];
		newDistortionPoint.screenY = [NSNumber numberWithFloat:coords.y];
		newDistortionPoint.index = [NSNumber numberWithInt:highestIndex+1];
		newDistortionPoint.distortionLine = selectedLine;
		[document.distortionPointsController setSelectedObjects:[NSArray arrayWithObject:newDistortionPoint]];
		[document.distortionLinesController.mainTableView display];	// refresh the line table's # Points column
        selectedLine.calibration.videoClip.project.distortionDisplayMode = @"Uncorrected";
	} else {
		NSRunAlertPanel(@"No line selected.",@"You must create a distortion line before you can add points to it by clicking the video.",@"Ok",nil,nil);
	}	
}

@end
