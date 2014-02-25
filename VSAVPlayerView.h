//
//  VSAVPlayerView.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/24/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <AVKit/AVKit.h>

@class VideoWindowController;

@interface VSAVPlayerView : AVPlayerView {
    
    IBOutlet VideoWindowController *__weak videoWindowController;
    
}

@end
