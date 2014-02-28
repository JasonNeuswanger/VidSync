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
    VSTrackedEvent *eventToDelete = (VSTrackedEvent *) [[self selectedObjects] firstObject];
    if ([eventToDelete.points count] > 0) {
        NSInteger alertResult = NSRunAlertPanel(@"Are you sure?",[NSString stringWithFormat:@"Are you sure you want to delete event %@?",eventToDelete.index],@"Yes",@"No",nil);
        if (alertResult == 1) {
            [super remove:sender];
            [document refreshOverlaysOfAllClips:sender];
        }
    } else {
        [super remove:sender];
        [document refreshOverlaysOfAllClips:sender];
    }
}

@end
