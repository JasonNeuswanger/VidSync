//
//  PortraitBrowserCell.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PortraitBrowserCell.h"

@implementation PortraitBrowserCell

- (NSRect) frame {
    NSRect superFrame = [super frame];
    /* Not doing anything for now in this subclass
    NSLog(@"Frame is %@",[NSValue valueWithRect:superFrame]);
    NSRect newFrame;
    newFrame.origin = superFrame.origin;
    newFrame.size = NSMakeSize(100,35); // floats w, h */
    return superFrame;
}

- (NSRect) selectionFrame {                         // Not doing anything for now in this subclass
    NSRect superFrame = [super selectionFrame];
    return superFrame;
}

@end
