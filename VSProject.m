//
//  VSProject.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/25/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VSProject.h"


@implementation VSProject

@dynamic name;
@dynamic notes;
@dynamic currentTimecode;
@dynamic calibrationTimecode;
@dynamic dateCreated;
@dynamic dateLastSaved;
@dynamic masterClip;
@dynamic videoClips;
@dynamic useIterativeTriangulation;
@dynamic trackedObjectTypes;
@dynamic trackedEventTypes;
@dynamic trackedObjects;
@dynamic trackedEvents;

@dynamic exportPathForData;
@dynamic exportClipSelectedClipName;
@dynamic capturePathForMovies;
@dynamic capturePathForStills;
@dynamic movieCaptureStartTime;
@dynamic movieCaptureEndTime;
@dynamic distortionDisplayMode;

@synthesize document;

- (NSDate *) dateCreatedAsNSDate
{
	return [NSDate dateWithString:self.dateCreated];
}

- (NSDate *) dateLastSavedAsNSDate
{
	return [NSDate dateWithString:self.dateLastSaved];
}

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath
{
    if (observer != nil) {
        @try {
            [self removeObserver:observer forKeyPath:keyPath];
        } @catch (id exception) {
        }
    }
}

@end
