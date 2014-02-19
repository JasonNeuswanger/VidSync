//
//  SyncedPlaybackView.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "SyncedPlaybackView.h"

@implementation SyncedPlaybackView

- (void)awakeFromNib {
    [self setWantsLayer:YES];
    NSImage *backgroundImage = [NSImage imageNamed:@"VideoScrubberBackground.png"];
    self.layer.backgroundColor = [[NSColor colorWithPatternImage:backgroundImage] CGColor];
    [self.layer setCornerRadius:5.0f];
    
    NSColor *videoButtonColor = [NSColor whiteColor];
    [stepForwardButton setCustomTitle:@"\uf051" withColor:videoButtonColor];
    [stepBackwardButton setCustomTitle:@"\uf048" withColor:videoButtonColor];
    [fastForwardButton setCustomTitle:@"\uf04e" withColor:videoButtonColor];
    [fastBackwardButton setCustomTitle:@"\uf04a" withColor:videoButtonColor];
    [playOrPauseButton setCustomTitle:@"\uf04b" withColor:videoButtonColor];
    [playBackwardButton setCustomTitle:@"\uf053" withColor:videoButtonColor];
}

- (void)drawRect:(NSRect)rect {
    [[NSColor clearColor] set];
    NSRectFill([self frame]);
}

@end
