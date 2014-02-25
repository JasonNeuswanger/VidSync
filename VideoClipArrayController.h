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

	NSString *__strong nameOfNewClip;
	IBOutlet VidSyncDocument *__weak document;
	IBOutlet NSPanel *__weak newClipNamePanel;
    IBOutlet NSTableView *__weak mainTableView;

}

@property (weak) IBOutlet NSTableView *mainTableView;
@property (strong) NSString *nameOfNewClip;

- (IBAction) add:(id)sender;
- (void) keyWindowDidChange:(NSNotification *)notification;
- (void)remove:(id)sender;

@end
