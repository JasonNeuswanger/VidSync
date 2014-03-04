//
//  VSAnnotationArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/1/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VSAnnotationArrayController.h"


@implementation VSAnnotationArrayController

- (void) awakeFromNib
{
	NSSortDescriptor *timecodeDescriptor = [[NSSortDescriptor alloc] initWithKey:@"startTimecode" ascending:YES];
	NSSortDescriptor *contentsDescriptor = [[NSSortDescriptor alloc] initWithKey:@"notes" ascending:YES];
	[self setSortDescriptors:[NSArray arrayWithObjects:timecodeDescriptor,contentsDescriptor,nil]];
	[super awakeFromNib];
}

- (IBAction) goToAnnotation:(id)sender
{
	if ([[self selectedObjects] count] > 0) {
		VSAnnotation *annotation = [[self selectedObjects] objectAtIndex:0];
		CMTime pointsMasterTime = [UtilityFunctions CMTimeFromString:annotation.startTimecode];
		[document goToMasterTime:pointsMasterTime];
	}	
}

- (IBAction) mirrorSelectedAnnotation:(id)sender
{
    if ([[self selectedObjects] count] > 0) {
        VSAnnotation *selectedAnnotation = [[self selectedObjects] objectAtIndex:0];
        for (VSVideoClip *clip in selectedAnnotation.videoClip.project.videoClips) {
            if (![clip isEqualTo:selectedAnnotation.videoClip]) {
                VSAnnotation *newAnnotation = (VSAnnotation *) [UtilityFunctions Clone:selectedAnnotation inContext:[self managedObjectContext] deep:NO];
                newAnnotation.videoClip = clip;
            }
        }
	}
    [[self managedObjectContext] processPendingChanges];
	[document refreshOverlaysOfAllClips:self];
}

@end
