//
//  VSVisibleItemArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/13/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class EventAwareTableView;

@interface VSVisibleItemArrayController : NSArrayController {

	IBOutlet EventAwareTableView *__weak mainTableView;
	
}

@property (weak,readonly) IBOutlet EventAwareTableView *mainTableView;

- (void) scrollTableToSelectedObject;
- (void) remove:(id)sender;

@end
