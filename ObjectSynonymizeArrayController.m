//
//  ObjectSynonymizeArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/5/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "ObjectSynonymizeArrayController.h"


@implementation ObjectSynonymizeArrayController

- (NSArray *)arrangeObjects:(NSArray *)objects {
	if ([[mainObjectsController selectedObjects] count] > 0) {
		VSTrackedObject *mainObject = [[mainObjectsController selectedObjects] objectAtIndex:0];
		NSMutableArray *filteredObjects = [NSMutableArray arrayWithArray:objects];
		[filteredObjects removeObject:mainObject];
		if ([[[typeFilterButton selectedItem] title] isEqualToString:@"The Same Type"]) {
			NSMutableArray *objectsOfTheSameType = [NSMutableArray new];
			for (VSTrackedObject *object in filteredObjects) {
				if ([object.type isEqualTo:mainObject.type]) [objectsOfTheSameType addObject:object];
			}
			return [super arrangeObjects:objectsOfTheSameType];
			
			
		} else {	// show other objects of all types
			return [super arrangeObjects:filteredObjects];
		}
	} else {
		return [super arrangeObjects:objects];
	}
}

- (IBAction) doRearrangeObjects:(id)sender
{
	[self rearrangeObjects];
}

- (IBAction) synonymize:(id)sender;
{	
	VSTrackedObject *deadSynonym = [[self selectedObjects] objectAtIndex:0];
	VSTrackedObject *survivingSynonym = [[mainObjectsController selectedObjects] objectAtIndex:0];
	if (deadSynonym.notes != nil) survivingSynonym.notes = [survivingSynonym.notes stringByAppendingString:[NSString stringWithFormat:@"\n\n%@",deadSynonym.notes]];
	for (VSTrackedEvent *event in deadSynonym.trackedEvents) event.trackedObjects = [event.trackedObjects setByAddingObject:survivingSynonym];
	[self removeObject:deadSynonym];
	[self rearrangeObjects];						
	[mainObjectsController rearrangeObjects];
	[[survivingSynonym managedObjectContext] processPendingChanges];
	[document refreshOverlaysOfAllClips:sender];
}

@end
