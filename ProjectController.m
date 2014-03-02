//
//  ProjectController.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/1/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "ProjectController.h"

@implementation ProjectController

- (void) dealloc
{
    /*
    VSProject *project = [self content];
    for (VSVideoClip *clip in project.videoClips) {
        clip.windowController = nil;
    }*/
    NSLog(@"deallocing ProjectController");
}

@end
