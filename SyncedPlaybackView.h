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
@class PlayWhilePressedButton;
@class VidSyncDocument;

@interface SyncedPlaybackView : NSView {
    
    IBOutlet VideoControlButton __weak *playOrPauseButton;
    IBOutlet VideoControlButton __weak *stepForwardButton;
    IBOutlet VideoControlButton __weak *stepBackwardButton;
    IBOutlet VideoControlButton __weak *playBackwardButton;
    IBOutlet VideoControlButton __weak *bookmarkSetButton1;
    IBOutlet VideoControlButton __weak *bookmarkSetButton2;
    IBOutlet VideoControlButton __weak *bookmarkGoButton1;
    IBOutlet VideoControlButton __weak *bookmarkGoButton2;
    
    IBOutlet VideoControlButton __weak *maximizeButton;

    IBOutlet PlayWhilePressedButton __weak *mainPlayForwardWhilePressedButton;
    IBOutlet PlayWhilePressedButton __weak *mainPlayBackwardWhilePressedButton;
    
    IBOutlet VidSyncDocument __weak *document;
    
}

@end
