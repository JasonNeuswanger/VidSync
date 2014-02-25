//
//  SyncedPlaybackView.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@class VideoControlButton;
@class BookmarkControlButton;

@interface SyncedPlaybackView : NSView {
    
    IBOutlet __weak VideoControlButton *playOrPauseButton, *stepForwardButton, *stepBackwardButton, *playBackwardButton, *fastForwardButton, *fastBackwardButton, *bookmarkSetButton1, *bookmarkSetButton2, *bookmarkGoButton1, *bookmarkGoButton2;

}

@end
