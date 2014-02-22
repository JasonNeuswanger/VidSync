//
//  MainProjectWindow.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/22/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "MainProjectWindow.h"

@implementation MainProjectWindow

- (void) awakeFromNib
{
    NSTrackingArea *mouseTrackingArea = [[NSTrackingArea alloc] initWithRect:[[self contentView] frame] options:NSTrackingMouseEnteredAndExited|NSTrackingActiveInActiveApp owner:self userInfo:nil];
    [[self contentView] addTrackingArea:mouseTrackingArea];
}

- (void) mouseEntered:(NSEvent *)theEvent
{
    [self makeKeyAndOrderFront:self];
}

@end
