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
    
    unsigned int fontSize;
	
}

@property (assign) unsigned int fontSize;

- (void) setCustomTitle:(NSString *)title withColor:(NSColor *)color;

@end