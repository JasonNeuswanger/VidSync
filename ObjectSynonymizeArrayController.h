//
//  ObjectSynonymizeArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/5/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface ObjectSynonymizeArrayController : TypeIndexNameSortedArrayController {
	
	IBOutlet TrackedObjectArrayController *__weak mainObjectsController;
	IBOutlet NSPopUpButton *__weak typeFilterButton;
	IBOutlet VidSyncDocument *__weak document;
	
}

- (NSArray *)arrangeObjects:(NSArray *)objects;

- (IBAction) doRearrangeObjects:(id)sender;

- (IBAction) synonymize:(id)sender;

@end
