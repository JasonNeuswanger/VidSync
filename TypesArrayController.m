//
//  TypesArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/9/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import "TypesArrayController.h"


@implementation TypesArrayController

- (IBAction) add:(id)sender
{
	if ([sender tag] == 1) {		// It's a new object type.
		VSTrackedObjectType *newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObjectType" inManagedObjectContext:[self managedObjectContext]];	
		newType.name = [newTypeName stringValue];
		newType.notes = [newTypeDescription stringValue];
		[self addObject:newType];	// Adds the object type to the project
		[newType addObserver:newType forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	} else {						// It's a new event type.
		VSTrackedEventType *newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedEventType" inManagedObjectContext:[self managedObjectContext]];	
		newType.name = [newTypeName stringValue];
		newType.notes = [newTypeDescription stringValue];
		[self addObject:newType];	// Adds the event type to the project
		[newType addObserver:newType forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	}
	[self rearrangeObjects];
	[inputPanel performClose:self];
	[newTypeName setStringValue:@""];
	[newTypeDescription setStringValue:@""];
}

- (void) rearrangeObjects
{
	[super rearrangeObjects];
}

@end
