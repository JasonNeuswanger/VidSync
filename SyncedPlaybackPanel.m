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
    self.initialFirstResponder = nil;
}

- (IBAction)makeKeyAndOrderFront:(id)sender
{
    // This function is called when creating a new document by [NSDocument showWindows], which leads to showing the synced panel when a new
    // document is created, before loading videos or anything. So we check that this isn't the case before passing along the order-front message.
    if (![sender isKindOfClass:[VidSyncDocument class]]) [super makeKeyAndOrderFront:sender];
}

- (IBAction) maximizeSyncedPlaybackPanel:(id)sender
{
    NSRect windowFrame = [self frame];
    NSRect screenVisibleFrame = [[NSScreen mainScreen] visibleFrame];
    NSRect newFrame = NSMakeRect(screenVisibleFrame.origin.x,screenVisibleFrame.origin.y + (screenVisibleFrame.size.height - windowFrame.size.height),screenVisibleFrame.size.width,windowFrame.size.height);
    [self setFrame:newFrame display:YES];
}

- (void) keyDown:(NSEvent *)theEvent
{
    // Option + Arrow plays at normal rate while pressed
    // Control + Option + Arrow plays at advanced playback rate 1 while pressed
    // Command + Option + Arrow plays at advanced playback rate 2 while pressed
    
    if (![theEvent isARepeat]) {
        unichar key = [[theEvent charactersIgnoringModifiers] characterAtIndex: 0];
        
        if ([theEvent modifierFlags] & NSAlternateKeyMask) {    // Forward option+leftarrow and option+rightarrow keypresses to the appropriate PlayWhilePressedButton
            if (key == NSLeftArrowFunctionKey) {
                if ([theEvent modifierFlags] & NSControlKeyMask) {
                    [document.playBackwardAtRate1WhilePressedButton startPlaying];
                } else if ([theEvent modifierFlags] & NSShiftKeyMask) {
                    [document.playBackwardAtRate2WhilePressedButton startPlaying];
                } else {
                    [document.playBackwardWhilePressedButton startPlaying];
                }
            } else if (key == NSRightArrowFunctionKey) {
                if ([theEvent modifierFlags] & NSControlKeyMask) {
                    [document.playForwardAtRate1WhilePressedButton startPlaying];
                } else  if ([theEvent modifierFlags] & NSShiftKeyMask) {
                    [document.playForwardAtRate2WhilePressedButton startPlaying];
                } else {
                    [document.playForwardWhilePressedButton startPlaying];
                }
            }
            return;
        }
        
        if (key == '1') {
            if ([theEvent modifierFlags] & NSControlKeyMask) {
                [document advancedPlayAll:document.playBackwardAtRate1Button];
            } else {
                [document advancedPlayAll:document.playForwardAtRate1Button];
            }
            return;
        } else if (key == '2') {
            if ([theEvent modifierFlags] & NSControlKeyMask) {
                [document advancedPlayAll:document.playBackwardAtRate2Button];
            } else {
                [document advancedPlayAll:document.playForwardAtRate2Button];
            }
            return;
        } else {
            [super keyDown:theEvent];
        }
    }
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
 Old note: Once the user starts dragging the mouse, move the window with it. The window has no title bar for
 the user to drag (so we have to implement dragging ourselves).
 
 New note: In 10.11 El Capitan at least (maybe earlier), the window drags properly without any interference in the mouseDragged method. The 
 function below just caused the window to jump around in strange ways while being dragged before settling into the correct location when the 
 mouse is released. I don't know when this changed, but commenting out the whole thing fixes the problems.
 
 */
/*
- (void)mouseDragged:(NSEvent *)theEvent {
    
     
    NSRect screenVisibleFrame = [[NSScreen mainScreen] visibleFrame];
    NSRect windowFrame = [self frame];
    NSPoint oldOrigin = windowFrame.origin; // TEMPORARY DIAGNOSTIC
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
    
    // Ok, so the window is dragging effectively only when dragging is the first operation I perform on it, before making it key, in which case it doesn't
    // even call this function. When it has to call this function, it's messed up.
    
    //NSLog(@"Dragging by amount (%1.3f, %1.3f) from (%1.3f, %1.3f) to (%1.3f, %1.3f)", (currentLocation.x - initialLocation.x), (currentLocation.y - initialLocation.y), oldOrigin.x, oldOrigin.y, newOrigin.x, newOrigin.y);
    
    [self setFrameOrigin:newOrigin];
 
}
*/
- (void) scrollWheel:(NSEvent *)theEvent
{
    if ([theEvent deltaY] > 0) {
        [document stepBackwardAll:self];
    } else if ([theEvent deltaY] < 0) {
        [document stepForwardAll:self];
    }
}

/*--- These key/main window settings are necessary to make text fields in this window editable ---*/

- (BOOL) acceptsFirstResponder
{
    return YES;
}

- (BOOL) canBecomeKeyWindow
{
    return YES;
}

- (BOOL)canBecomeMainWindow
{
    return YES;
}

- (void) orderFront:(id)sender
{
    [super orderFront:sender];
}

@end
