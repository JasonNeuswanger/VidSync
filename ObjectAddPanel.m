//
//  ObjectAddPanel.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/1/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "ObjectAddPanel.h"


@implementation ObjectAddPanel

- (void)makeKeyAndOrderFront:(id)sender		// causes the color well to take the correct setting when the window is first opened
{
	[self updateColor:self];
	[super makeKeyAndOrderFront:sender];
}

- (IBAction) updateColor:(id)sender
{
	VSTrackedObjectType *selectedObjectType = [[typeButton selectedItem] representedObject];
	NSColor *newColor = selectedObjectType.color;
	if (newColor != nil) [colorWell setColor:newColor];
}

@end
