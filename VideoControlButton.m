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

- (void) awakeFromNib
{
    [self setBordered:NO];
    [self setNeedsDisplay];
    pressedHighlightColor = [NSColor grayColor];
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
        [self setCustomTitle:[self title] withColor:[NSColor whiteColor] fontSize:fontSizeSet];
        [super mouseUp:theEvent];
    }
}

- (void) setCustomTitle:(NSString *)title withColor:(NSColor *)color fontSize:(float)fontSize {
    fontSizeSet = fontSize;
    NSMutableAttributedString *colorTitle =[[NSMutableAttributedString alloc] initWithAttributedString:[[NSMutableAttributedString alloc] initWithString:title]];
    NSRange titleRange = NSMakeRange(0, [colorTitle length]);
    [colorTitle addAttribute:NSForegroundColorAttributeName value:color range:titleRange];
    [colorTitle addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:fontSize] range:titleRange];
    [self setAttributedTitle:colorTitle];
//    NSLog(@"Set an attributed title for %@ of length %@ to %@",title,[NSNumber numberWithInt:[colorTitle length]],colorTitle);
}

@end
