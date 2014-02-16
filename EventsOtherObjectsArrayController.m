//
//  EventsOtherObjectsArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 1/12/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "EventsOtherObjectsArrayController.h"


@implementation EventsOtherObjectsArrayController

- (NSArray *)arrangeObjects:(NSArray *)objects {
	if ([[eventController selectedObjects] count] > 0) {
		NSMutableArray *filteredObjects = [NSMutableArray arrayWithCapacity:[objects count]];
		NSSet *eventsObjects = [[[eventController selectedObjects] objectAtIndex:0] trackedObjects];
		NSEnumerator *objectsEnumerator = [objects objectEnumerator];
		id item;
		while (item = [objectsEnumerator nextObject]) {
			if (![eventsObjects containsObject:item]) [filteredObjects addObject:item];
		}
		return [super arrangeObjects:filteredObjects];
	} else {
		return [super arrangeObjects:objects];
	}
}

- (IBAction) addSelectedObjectToEvent:(id)sender
{
	if ([[eventController selectedObjects] count] > 0 && [[self selectedObjects] count] > 0) {
		VSTrackedEvent *theEvent = [[eventController selectedObjects] objectAtIndex:0];
		VSTrackedObject *theObject = [[self selectedObjects] objectAtIndex:0];
		theEvent.trackedObjects = [theEvent.trackedObjects setByAddingObject:theObject];
		[self rearrangeObjects];
	}
}

- (IBAction) removeSelectedObjectFromEvent:(id)sender
{
	if ([[eventController selectedObjects] count] > 0 && [[eventsObjectsController selectedObjects] count] > 0) {
		VSTrackedObject *objectToRemove = [[eventsObjectsController selectedObjects] objectAtIndex:0];
		VSTrackedEvent *theEvent = [[eventController selectedObjects] objectAtIndex:0];
		NSMutableSet *trackedObjects = [NSMutableSet setWithSet:theEvent.trackedObjects];
		[trackedObjects removeObject:objectToRemove];
		theEvent.trackedObjects = trackedObjects;
		[self rearrangeObjects];
	}
}

-(void)tableViewSelectionDidChange:(NSNotification *)notification
{
	[self rearrangeObjects];
}

@end
