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
    NSImage *backgroundImage = [NSImage imageNamed:@"TallVideoScrubberBackground.png"];
    self.layer.backgroundColor = [[NSColor colorWithPatternImage:backgroundImage] CGColor];
    [self.layer setCornerRadius:5.0f];
    
    NSColor *videoButtonColor = [NSColor whiteColor];
    float videoButtonFontSize = 25.0f;
    float bookmarkButtonFontSize = 20.0f;
    
    [stepForwardButton setCustomTitle:@"\uf051" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [stepBackwardButton setCustomTitle:@"\uf048" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [fastForwardButton setCustomTitle:@"\uf04e" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [fastBackwardButton setCustomTitle:@"\uf04a" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [playOrPauseButton setCustomTitle:@"\uf04b" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [playBackwardButton setCustomTitle:@"\uf04b" withColor:videoButtonColor fontSize:videoButtonFontSize];

    [bookmarkSetButton1 setCustomTitle:@"\uf02e" withColor:videoButtonColor fontSize:bookmarkButtonFontSize];
    [bookmarkSetButton2 setCustomTitle:@"\uf02e" withColor:videoButtonColor fontSize:bookmarkButtonFontSize];
    
    NSColor *unpressedBookmarkGoColor = [NSColor colorWithWhite:1.0 alpha:0.15];
    
    [bookmarkGoButton1 setCustomTitle:@"\uf18e" withColor:unpressedBookmarkGoColor fontSize:bookmarkButtonFontSize];
    [bookmarkGoButton2 setCustomTitle:@"\uf18e" withColor:unpressedBookmarkGoColor fontSize:bookmarkButtonFontSize];
    bookmarkGoButton1.enabled = NO;
    bookmarkGoButton2.enabled = NO;
    bookmarkGoButton1.unpressedColor = unpressedBookmarkGoColor;
    bookmarkGoButton2.unpressedColor = unpressedBookmarkGoColor;
}

- (void)drawRect:(NSRect)rect {
    [[NSColor clearColor] set];
    NSRectFill([self frame]);
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
    if ([keyPath isEqual:@"bookmarkIsSet1"] || [keyPath isEqual:@"bookmarkIsSet2"]) {
        float bookmarkButtonFontSize = 20.0f;
        VidSyncDocument *document = (VidSyncDocument *) object;
        if (document.bookmarkIsSet1) {
            [bookmarkGoButton1 setCustomTitle:@"\uf18e" withColor:[NSColor colorWithWhite:1.0 alpha:1.0] fontSize:bookmarkButtonFontSize];
            bookmarkGoButton1.unpressedColor = [NSColor whiteColor];
            bookmarkGoButton1.enabled = YES;
        }
        if (document.bookmarkIsSet2) {
            [bookmarkGoButton2 setCustomTitle:@"\uf18e" withColor:[NSColor colorWithWhite:1.0 alpha:1.0] fontSize:bookmarkButtonFontSize];
            bookmarkGoButton2.unpressedColor = [NSColor whiteColor];
            bookmarkGoButton2.enabled = YES;
        }
    }
}

@end
