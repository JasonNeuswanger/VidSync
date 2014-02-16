//
//  TrackedEventArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 1/11/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "TrackedEventArrayController.h"

@implementation TrackedEventArrayController

- (IBAction) add:(id)sender
{
	VSTrackedEvent *newEvent = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedEvent" inManagedObjectContext:[self managedObjectContext]];	
	newEvent.name = [newEventName stringValue];
	newEvent.type = [[newEventType selectedItem] representedObject];
	[self addObject:newEvent];
	newEvent.index = [NSNumber numberWithInt:[VSTrackedEvent highestEventIndexInProject:document.project]+1];
	[newEventName setStringValue:@""];
	[eventAddPanel performClose:nil];
}

- (void)remove:(id)sender
{
	[super remove:sender];
	[document refreshOverlaysOfAllClips:sender];	
}

@end
