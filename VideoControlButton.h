//
//  VideoControlButton.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@interface VideoControlButton : NSButton {
    
	IBOutlet VidSyncDocument *__weak document;
    
    float fontSizeSet;
    
    NSColor *__strong pressedHighlightColor;
    NSColor *__strong unpressedColor;
    
    BOOL enabled;
    
}

@property (assign) BOOL enabled;
@property (strong) NSColor *unpressedColor;

- (void) setCustomTitle:(NSString *)title withColor:(NSColor *)color fontSize:(float)fontSize;

@end