//
//  TrackedObjectArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/6/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface TrackedObjectArrayController : TypeIndexNameSortedArrayController {

	IBOutlet NSTextField *__weak newObjectName;
	IBOutlet NSPopUpButton *__weak newObjectType;
	IBOutlet NSColorWell *__weak newTypeColorWell;
	IBOutlet NSPanel *__weak objectAddPanel;
	IBOutlet VidSyncDocument *__weak document;
	
}

- (IBAction) add:(id)sender;
- (void)remove:(id)sender;

@end
