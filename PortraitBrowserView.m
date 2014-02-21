//
//  PortraitBrowserView.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PortraitBrowserView.h"

@implementation PortraitBrowserView

- (void) awakeFromNib
{
    [self setIntercellSpacing:NSMakeSize(2.0f,2.0f)];
    [self setValue:[NSColor grayColor] forKey:IKImageBrowserBackgroundColorKey];
    // I could eventually use an NSColor colorWithPattern for the background, and IKImageBrowserGroupHeaderLayer, a custom CALayer, to stylize the group headings. Not worth the trouble for now.
}

- (void)drawRect:(NSRect)dirtyRect
{
	[super drawRect:dirtyRect];
}

- (IKImageBrowserCell*)	newCellForRepresentedItem:(id) anItem
{
	PortraitBrowserCell* cell = [[PortraitBrowserCell alloc] init];
	return cell;
}

@end
