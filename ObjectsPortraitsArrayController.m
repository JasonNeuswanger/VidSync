//
//  ObjectsPortraitsArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "ObjectsPortraitsArrayController.h"

@implementation ObjectsPortraitsArrayController

- (void) awakeFromNib {
    
//    [portraitBrowserView setIntercellSpacing:NSMakeSize(2.0f,2.0f)];
//    [portraitBrowserView setCellSize:NSMakeSize(200.0f,125.0f)];
    
}

- (void) addImage:(NSImage *)image ofObject:(VSTrackedObject *)object fromSourceClip:(VSVideoClip *)sourceVideoClip inRect:(NSRect)rect withTimecode:(NSString *)timecode {
    VSTrackedObjectPortrait *newPortrait = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObjectPortrait" inManagedObjectContext:[self managedObjectContext]];
    newPortrait.timecode = timecode;
    newPortrait.sourceVideoClip = sourceVideoClip;
    newPortrait.trackedObject = object;
    newPortrait.frameString = NSStringFromRect(rect);
    [newPortrait setImage:image];
    [self addObject:newPortrait];
    [[self managedObjectContext] processPendingChanges];
    [self refreshImageBrowserView];
}

@end
