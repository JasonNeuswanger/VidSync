//
//  VideoClipArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 10/26/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
#import "VidSyncDocument.h"

@class VidSyncDocument;


@interface VideoClipArrayController : NSArrayController {

	IBOutlet NSTextField *newClipName;
	IBOutlet VidSyncDocument *document;
	IBOutlet NSPanel *newClipNamePanel;

}

@property (strong) IBOutlet NSTableView *mainTableView;

- (IBAction) add:(id)sender;
- (void) keyWindowDidChange:(NSNotification *)notification;
- (void)remove:(id)sender;

@end
