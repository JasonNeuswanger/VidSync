//
//  PlaybackDurationTabView.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/26/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@class SyncedPlaybackPanel;

@interface PlaybackDurationTabView : NSTabView {
    
    IBOutlet SyncedPlaybackPanel *__weak syncedPlaybackPanel;
    
}

@end
