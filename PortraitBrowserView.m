//
//  PortraitBrowserView.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PortraitBrowserView.h"

@implementation PortraitBrowserView

- (id)initWithFrame:(NSRect)frame
{
    self = [super initWithFrame:frame];
    if (self) {
        NSLog(@"Initiated a custom view");
        [self setIntercellSpacing:NSMakeSize(2.0f,2.0f)];
        [self setDelegate:self];
    }
    return self;
}

- (void)drawRect:(NSRect)dirtyRect
{
	[super drawRect:dirtyRect];
	
    // Drawing code here.
}

- (IKImageBrowserCell*)	newCellForRepresentedItem:(id) anItem
{
	PortraitBrowserCell* cell = [[PortraitBrowserCell alloc] init];
	return cell;
}

@end
