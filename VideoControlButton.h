//
//  VideoControlButton.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@interface VideoControlButton : NSButton {
    
	IBOutlet VidSyncDocument *document;
    
    float fontSizeSet;
    
    NSColor *pressedHighlightColor;
    
    BOOL enabled;
    
}

@property BOOL enabled;

- (void) setCustomTitle:(NSString *)title withColor:(NSColor *)color fontSize:(float)fontSize;

@end