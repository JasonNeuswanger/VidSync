//
//  TrackedEventArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/11/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface TrackedEventArrayController : TypeIndexNameSortedArrayController {

	IBOutlet NSTextField *__weak newEventName;
	IBOutlet NSPopUpButton *__weak newEventType;
	IBOutlet NSPanel *__weak eventAddPanel;
	IBOutlet VidSyncDocument *__weak document;
	
}

- (IBAction) add:(id)sender;
- (void)remove:(id)sender;

- (IBAction) sortByEarliestTimecode:(id)sender;

@end
