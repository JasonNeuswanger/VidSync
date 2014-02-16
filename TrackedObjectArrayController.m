//
//  TrackedObjectArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 1/6/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "TrackedObjectArrayController.h"


@implementation TrackedObjectArrayController

- (IBAction) add:(id)sender
{
	VSTrackedObject *newObj = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObject" inManagedObjectContext:[self managedObjectContext]];	
	newObj.name = [newObjectName stringValue];
	newObj.type = [[newObjectType selectedItem] representedObject];
	[self addObject:newObj];	// Adding the object to the project before setting its index.  Convenient -- but is it harmless?  We'll see.
	newObj.index = [NSNumber numberWithInt:[VSTrackedObject highestObjectIndexInProject:newObj.project]+1];
	newObj.color = [newTypeColorWell color];
	[newObjectName setStringValue:@""];
	[objectAddPanel performClose:nil];
}

- (void)remove:(id)sender
{
	[super remove:sender];
	[document refreshOverlaysOfAllClips:sender];
	
}

@end
