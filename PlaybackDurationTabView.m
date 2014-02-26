//
//  PlaybackDurationTabView.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/26/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PlaybackDurationTabView.h"

@implementation PlaybackDurationTabView

- (id)initWithFrame:(NSRect)frame
{
    self = [super initWithFrame:frame];
    if (self) {
        // Initialization code here.
    }
    return self;
}

- (void)drawRect:(NSRect)dirtyRect
{
	[super drawRect:dirtyRect];
	
    // Drawing code here.
}

- (void) mouseDown:(NSEvent *)theEvent
{
    [syncedPlaybackPanel mouseDown:theEvent];   // Allows the drag tracker to register a mousedown here for starting location if the user drags the window, so it doesn't jump around
    [super mouseDown:theEvent];
}

@end
