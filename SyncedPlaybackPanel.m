//
//  SyncedPlaybackPanel.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//
//  This class is a modified version of Apple's "RoundTransparentWindow" example code.

#import "SyncedPlaybackPanel.h"

@implementation SyncedPlaybackPanel

@synthesize initialLocation;

/*
 In Interface Builder, the class for the window is set to this subclass. Overriding the initializer
 provides a mechanism for controlling how objects of this class are created.
 */
- (id)initWithContentRect:(NSRect)contentRect
                styleMask:(NSUInteger)aStyle
                  backing:(NSBackingStoreType)bufferingType
                    defer:(BOOL)flag {
    
    // Using NSBorderlessWindowMask results in a window without a title bar.
    self = [super initWithContentRect:contentRect styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
    if (self != nil) {
        // Start with no transparency for all drawing into the window
        [self setAlphaValue:1.0];
        // Turn off opacity so that the parts of the window that are not drawn into are transparent.
        [self setOpaque:NO];
        [self setHasShadow:YES];
        [self setBackgroundColor:[NSColor clearColor]];
        [self setMovableByWindowBackground:YES];
        [self setStyleMask:NSResizableWindowMask];
    }
    return self;
}

- (void) awakeFromNib
{
    [document syncedPlaybackPanelAwokeFromNib];
}

- (IBAction)makeKeyAndOrderFront:(id)sender
{
    // I'm basically disabling makeKeyAndOrderFront for this window, because it was being called when creating a new document by [NSDocument showWindows].
    // It doesn't seem there's a convenient place to disable this except for here.
    // [super makeKeyAndOrderFront:sender];
}


- (IBAction) maximizeSyncedPlaybackPanel:(id)sender
{
    NSRect windowFrame = [self frame];
    NSRect screenVisibleFrame = [[NSScreen mainScreen] visibleFrame];
    NSRect newFrame = NSMakeRect(screenVisibleFrame.origin.x,screenVisibleFrame.origin.y + (screenVisibleFrame.size.height - windowFrame.size.height),screenVisibleFrame.size.width,windowFrame.size.height);
    [self setFrame:newFrame display:YES];
}

/*
 Start tracking a potential drag operation here when the user first clicks the mouse, to establish
 the initial location.
 */
- (void)mouseDown:(NSEvent *)theEvent {
    // Get the mouse location in window coordinates.
    self.initialLocation = [theEvent locationInWindow];
}

/*
 Once the user starts dragging the mouse, move the window with it. The window has no title bar for
 the user to drag (so we have to implement dragging ourselves)
 */

- (void)mouseDragged:(NSEvent *)theEvent {
    
    NSRect screenVisibleFrame = [[NSScreen mainScreen] visibleFrame];
    NSRect windowFrame = [self frame];
    NSPoint newOrigin = windowFrame.origin;
    
    // Get the mouse location in window coordinates.
    NSPoint currentLocation = [theEvent locationInWindow];
    // Update the origin with the difference between the new mouse location and the old mouse location.
    newOrigin.x += (currentLocation.x - initialLocation.x);
    newOrigin.y += (currentLocation.y - initialLocation.y);
    
    // Don't let window get dragged up under the menu bar
    if ((newOrigin.y + windowFrame.size.height) > (screenVisibleFrame.origin.y + screenVisibleFrame.size.height)) {
        newOrigin.y = screenVisibleFrame.origin.y + (screenVisibleFrame.size.height - windowFrame.size.height);
    }
    
    // Move the window to the new location
    
    [self setFrameOrigin:newOrigin];
}

- (void) scrollWheel:(NSEvent *)theEvent
{
    if ([theEvent deltaY] > 0) {
        [document stepBackwardAll:self];
    } else if ([theEvent deltaY] < 0) {
        [document stepForwardAll:self];
    }
}

/*--- These key/main window settings are necessary to make text fields in this window editable ---*/

- (BOOL) canBecomeKeyWindow
{
    return YES;
}

- (void) orderFront:(id)sender
{
    [super orderFront:sender];
}

@end
