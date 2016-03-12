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


#import "VideoControlButton.h"

@implementation VideoControlButton

@synthesize enabled;
@synthesize unpressedColor;
@synthesize pressedHighlightColor;

- (void) awakeFromNib
{
    [self setBordered:NO];
    [self setNeedsDisplay];
    if (pressedHighlightColor == nil) pressedHighlightColor = [NSColor grayColor];
    if (unpressedColor == nil) unpressedColor = [NSColor whiteColor];
    enabled = YES;    
}

- (void) mouseDown:(NSEvent *)theEvent
{
    if (enabled) {
        [self setCustomTitle:[self title] withColor:pressedHighlightColor fontSize:fontSizeSet];
        [super mouseDown:theEvent];
        [self mouseUp:theEvent];		// the [super mouseDown] kills the normal mouseUp; it also waits until the mouse is actually up to execute this call to mouseUp.
    }
}

- (void) mouseUp:(NSEvent *)theEvent
{
    if (enabled) {
        [self setCustomTitle:[self title] withColor:unpressedColor fontSize:fontSizeSet];
        [super mouseUp:theEvent];
    }
}

- (void) setCustomTitle:(NSString *)title withColor:(NSColor *)color fontSize:(float)fontSize {
    fontSizeSet = fontSize;
    currentColor = color;
    if (unpressedColor == nil) unpressedColor = color;
    NSMutableAttributedString *colorTitle =[[NSMutableAttributedString alloc] initWithAttributedString:[[NSMutableAttributedString alloc] initWithString:title]];
    NSRange titleRange = NSMakeRange(0, [colorTitle length]);
    [colorTitle addAttribute:NSForegroundColorAttributeName value:color range:titleRange];
    [colorTitle addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:fontSize] range:titleRange];
    [self setAttributedTitle:colorTitle];
}

- (void) setCustomTitle:(NSString *)title   // use same color / fontsize as original; only used for main play/pause button
{
    NSMutableAttributedString *colorTitle =[[NSMutableAttributedString alloc] initWithAttributedString:[[NSMutableAttributedString alloc] initWithString:title]];
    NSRange titleRange = NSMakeRange(0, [colorTitle length]);
    [colorTitle addAttribute:NSForegroundColorAttributeName value:currentColor range:titleRange];
    [colorTitle addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:fontSizeSet] range:titleRange];
    [self setAttributedTitle:colorTitle];
}

@end
