//
//  SyncedPlaybackView.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@class VideoControlButton;

@interface SyncedPlaybackView : NSView {
    
    IBOutlet VideoControlButton *playOrPauseButton, *stepForwardButton, *stepBackwardButton, *playBackwardButton, *fastForwardButton, *fastBackwardButton;
    
}

@end
