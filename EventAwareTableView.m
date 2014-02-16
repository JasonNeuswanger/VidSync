//
//  EventAwareTableView.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/30/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "EventAwareTableView.h"


@implementation EventAwareTableView

- (void)keyDown:(NSEvent *)theEvent
{		
	unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
	if (key == NSDeleteCharacter) {
		if (deleteButton != nil) [deleteButton performClick:self];
	} else {
		if (key == NSUpArrowFunctionKey) {
			if ([self selectedRow] != 0) {	// if the top row isn't already selected
				[[NSNotificationCenter defaultCenter] postNotificationName:NSTableViewSelectionIsChangingNotification object:self];					
			}
		} else if (key == NSDownArrowFunctionKey) {
			if ([self selectedRow] != ([self numberOfRows] - 1)) {	// if the bottom row isn't already selected
				[[NSNotificationCenter defaultCenter] postNotificationName:NSTableViewSelectionIsChangingNotification object:self];									
			}
		}
		[super keyDown:theEvent];
	}
}

@end
