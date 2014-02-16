//
//  TrackedObjectArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/6/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface TrackedObjectArrayController : TypeIndexNameSortedArrayController {

	IBOutlet NSTextField *newObjectName;
	IBOutlet NSPopUpButton *newObjectType;
	IBOutlet NSColorWell *newTypeColorWell;
	IBOutlet NSPanel *objectAddPanel;
	IBOutlet VidSyncDocument *document;
	
}

- (IBAction) add:(id)sender;
- (void)remove:(id)sender;

@end
