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
    [replayButton setCustomTitle:@"\uf0e2" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [stepForwardButton setCustomTitle:@"\uf051" withColor:videoButtonColor fontSize:videoButtonFontSize];
    [stepBackwardButton setCustomTitle:@"\uf048" withColor:videoButtonColor fontSize:videoButtonFontSize];
    
}

- (void) keyDown:(NSEvent *)theEvent
{
    [super keyDown:theEvent];
}

- (void)drawRect:(NSRect)dirtyRect
{
	[super drawRect:dirtyRect];
}

@end
