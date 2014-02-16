//
//  VideoOverlayWindow.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/30/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>

// It's necessary to subclass NSWindow to override canBecomeKeyWindow to return YES so it receives keypress events.
// The default value is NO for windows created with NSBorderlessWindowMask.

@interface VideoOverlayWindow : NSWindow {
}

- (BOOL)canBecomeKeyWindow;

@end
