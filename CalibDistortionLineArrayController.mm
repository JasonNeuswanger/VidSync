/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
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
