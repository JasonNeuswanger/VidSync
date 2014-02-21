//
//  ObjectsPortraitsArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PortraitsArrayController.h"

@class PortraitBrowserView;

@interface ObjectsPortraitsArrayController : PortraitsArrayController {
    
}

- (void) addImage:(NSImage *)image ofObject:(VSTrackedObject *)object fromSourceClip:(VSVideoClip *)sourceVideoClip withTimecode:(NSString *)timecode;

@end
