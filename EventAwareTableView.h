//
//  EventAwareTableView.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/30/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface EventAwareTableView : NSTableView {

	IBOutlet NSButton *__weak deleteButton;
	
}

- (void)keyDown:(NSEvent *)theEvent;

@end
