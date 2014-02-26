//
//  SyncedPlaybackPanelControlBox.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/20/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "SyncedPlaybackPanelControlBox.h"

@implementation SyncedPlaybackPanelControlBox

- (id)initWithFrame:(NSRect)frame
{
    self = [super initWithFrame:frame];
    if (self) {
        [self setWantsLayer:YES];
        self.layer.backgroundColor = [[NSColor colorWithCalibratedRed:1.0 green:1.0 blue:1.0 alpha:0.07] CGColor];
        self.layer.borderColor = [[NSColor colorWithCalibratedRed:1.0 green:1.0 blue:1.0 alpha:0.15] CGColor];
        self.layer.borderWidth = 1.0f;
        [self.layer setCornerRadius:5.0f];
    }
    return self;
}

- (void) awakeFromNib
{
    NSColor *videoButtonColor = [NSColor whiteColor];
    float videoButtonFontSize = 22.5f;
    
    // Note: These messages to outlets will just be ignored if they're not connected (each instance of this class only has some of the outlets connected)
    
    [playForwardWhilePressedButton setCustomTitle:@"\uf0a4" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [playBackwardWhilePressedButton setCustomTitle:@"\uf0a5" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [playForwardButton setCustomTitle:@"\uf04b" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [playBackwardButton setCustomTitle:@"\uf04b" withColor:videoButtonColor fontSize:videoButtonFontSize];
    
    [stepForwardButton setCustomTitle:@"\uf051" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [stepBackwardButton setCustomTitle:@"\uf048" withColor:videoButtonColor fontSize:videoButtonFontSize];
    
}

- (void)drawRect:(NSRect)dirtyRect
{
	[super drawRect:dirtyRect];
}

@end
