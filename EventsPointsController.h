//
//  EventsPointsController.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/20/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@class EventAwareTableView;

@interface EventsPointsController : VSVisibleItemArrayController {

	IBOutlet NSPopUpButton *__weak framesSelectButton;
	IBOutlet NSButton *__weak goToPointButton;
	IBOutlet VidSyncDocument *__weak document;
}

- (NSArray *)arrangeObjects:(NSArray *)objects;
- (IBAction)changePointFiltering:(id)sender;
- (IBAction) goToPoint:(id)sender;

@end
