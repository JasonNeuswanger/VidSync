//
//  EventsOtherObjectsArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/12/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//
//  The purpose of this NSArrayController subclass is to filter out the objects associated with an event from the "event's other objects" list in the 
//  event edit view, which is used to help manage the many-to-many relationship.


#import <Cocoa/Cocoa.h>


@interface EventsOtherObjectsArrayController : TypeIndexNameSortedArrayController {

    IBOutlet TrackedObjectArrayController *__weak objectController;
	IBOutlet TrackedEventArrayController *__weak eventController;
	IBOutlet VSVisibleItemArrayController *__weak eventsObjectsController;
	
}

- (NSArray *)arrangeObjects:(NSArray *)objects;

- (IBAction) addSelectedObjectToEvent:(id)sender;
- (IBAction) removeSelectedObjectFromEvent:(id)sender;

-(void)tableViewSelectionDidChange:(NSNotification *)notification;	// Delegate method for main object controller, to receive selection changes

@end
