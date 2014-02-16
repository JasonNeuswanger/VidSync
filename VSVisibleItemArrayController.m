//
//  VSVisibleItemArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 1/13/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VSVisibleItemArrayController.h"


@implementation VSVisibleItemArrayController

@synthesize mainTableView;

- (void) scrollTableToSelectedObject
{
	if ([[self selectedObjects] count] > 0) [mainTableView scrollRowToVisible:[self selectionIndex]];
}

- (void)remove:(id)sender
{
	int newSelectionIndex;
	if ([self canSelectNext]) {							// If there's another object below the one being deleted, prepare to select it
		newSelectionIndex = [self selectionIndex];
	} else {											// If this was the bottom object, then select the next one up
		newSelectionIndex = [self selectionIndex] - 1; 
	}
	[super remove:sender];
	[[self managedObjectContext] processPendingChanges];
	[self setSelectionIndex:newSelectionIndex];			
}


@end
