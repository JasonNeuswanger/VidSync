/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
 * 
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * 
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 ***********************************************************************************/


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
    
    [maximizeButton setCustomTitle:@"\uf055" withColor:videoButtonColor fontSize:10.0f];
    
    [stepForwardButton setCustomTitle:@"\uf051" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [stepBackwardButton setCustomTitle:@"\uf048" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [playOrPauseButton setCustomTitle:@"\uf04b" withColor:videoButtonColor fontSize:35.0f];
    [playBackwardButton setCustomTitle:@"\uf04b" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [mainPlayForwardWhilePressedButton setCustomTitle:@"\uf0a4" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [mainPlayBackwardWhilePressedButton setCustomTitle:@"\uf0a5" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [instantReplayButton setCustomTitle:@"\uf0e2" withColor:videoButtonColor fontSize:videoButtonFontSize];
    
    NSColor *unpressedBookmarkGoColor = [NSColor colorWithWhite:1.0 alpha:0.15];
    [bookmarkSetButton1 setCustomTitle:@"\uf02e" withColor:videoButtonColor fontSize:bookmarkButtonFontSize];
    [bookmarkSetButton2 setCustomTitle:@"\uf02e" withColor:videoButtonColor fontSize:bookmarkButtonFontSize];
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
        if ([(VidSyncDocument *) object bookmarkIsSet1]) {
            [bookmarkGoButton1 setCustomTitle:@"\uf18e" withColor:[NSColor colorWithWhite:1.0 alpha:1.0] fontSize:bookmarkButtonFontSize];
            bookmarkGoButton1.unpressedColor = [NSColor whiteColor];
            bookmarkGoButton1.enabled = YES;
        }
        if ([(VidSyncDocument *) object bookmarkIsSet2]) {
            [bookmarkGoButton2 setCustomTitle:@"\uf18e" withColor:[NSColor colorWithWhite:1.0 alpha:1.0] fontSize:bookmarkButtonFontSize];
            bookmarkGoButton2.unpressedColor = [NSColor whiteColor];
            bookmarkGoButton2.enabled = YES;
        }
    }
}

- (void) dealloc
{
    [document carefullyRemoveObserver:self forKeyPath:@"bookmarkIsSet1"];
    [document carefullyRemoveObserver:self forKeyPath:@"bookmarkIsSet2"];
}

@end
