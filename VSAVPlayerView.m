//
//  VSAVPlayerView.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/24/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "VSAVPlayerView.h"

@implementation VSAVPlayerView

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

// The normal scrolling behavior of AVPlayerView wasn't desirable. It wasn't stepping one frame per click of the mouse wheel, and it was stepping in the opposite direction
// from when the videos are synced. So I'm subclassing it just for the scroll wheel behavior.

- (void)scrollWheel:(NSEvent *)theEvent {
    if ([theEvent deltaY] > 0.0) {
        [self.player.currentItem stepByCount:-1];
    } else if ([theEvent deltaY] < 0.0) {
        [self.player.currentItem stepByCount:1];
    }
}


// Arrow keys step the video when not synced

- (void)keyDown:(NSEvent *)theEvent {
    unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
    if (key == NSRightArrowFunctionKey) {
        [videoWindowController.playerView.player.currentItem stepByCount:1];
    } else if (key == NSLeftArrowFunctionKey) {
        [videoWindowController.playerView.player.currentItem stepByCount:-1];
    }
    
}

- (void) dealloc
{
    NSLog(@"deallocing VSAVPlayerView");
}

@end
