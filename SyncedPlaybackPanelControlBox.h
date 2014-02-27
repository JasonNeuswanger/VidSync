//
//  SyncedPlaybackPanelControlBox.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/20/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@interface SyncedPlaybackPanelControlBox : NSView {
    
    IBOutlet VideoControlButton *__weak playForwardButton, *__weak playBackwardButton, *__weak stepForwardButton, *__weak stepBackwardButton;

    IBOutlet PlayWhilePressedButton *__weak playForwardWhilePressedButton, *__weak playBackwardWhilePressedButton;
    
}

@end
