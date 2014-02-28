//
//  VideoControlButton.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

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
