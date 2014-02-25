//
//  SyncedPlaybackPanel.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/18/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@interface SyncedPlaybackPanel : NSWindow {

    NSPoint initialLocation;
    
    IBOutlet VidSyncDocument *__weak document;
    
}

@property NSPoint initialLocation;

@end
