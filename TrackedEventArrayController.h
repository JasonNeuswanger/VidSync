//
//  TrackedEventArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/11/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface TrackedEventArrayController : TypeIndexNameSortedArrayController {

	IBOutlet NSTextField *newEventName;
	IBOutlet NSPopUpButton *newEventType;
	IBOutlet NSPanel *eventAddPanel;
	IBOutlet VidSyncDocument *document;
	
}

- (IBAction) add:(id)sender;
- (void)remove:(id)sender;

@end
