//
//  VideoControlButton.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "VideoControlButton.h"

@implementation VideoControlButton

@synthesize fontSize;

- (void) awakeFromNib
{
    [self setBordered:NO];
    self.fontSize = 25;
    [self setNeedsDisplay];
}


- (void) mouseDown:(NSEvent *)theEvent
{
    [self setCustomTitle:[self title] withColor:[NSColor grayColor]];
	[super mouseDown:theEvent];
	[self mouseUp:theEvent];		// the [super mouseDown] kills the normal mouseUp; it also waits until the mouse is actually up to execute this call to mouseUp.
}

- (void) mouseUp:(NSEvent *)theEvent
{
    [self setCustomTitle:[self title] withColor:[NSColor whiteColor]];
	[super mouseUp:theEvent];
}

- (void) setCustomTitle:(NSString *)title withColor:(NSColor *)color {
    NSMutableAttributedString *colorTitle =[[NSMutableAttributedString alloc] initWithAttributedString:[[NSMutableAttributedString alloc] initWithString:title]];
    NSRange titleRange = NSMakeRange(0, [colorTitle length]);
    [colorTitle addAttribute:NSForegroundColorAttributeName value:color range:titleRange];
    [colorTitle addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:25.0f] range:titleRange];
    [self setAttributedTitle:colorTitle];
}

@end
