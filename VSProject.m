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
@dynamic capturePathForMovies;
@dynamic capturePathForStills;
@dynamic movieCaptureStartTime;
@dynamic movieCaptureEndTime;

@synthesize document;

- (NSDate *) dateCreatedAsNSDate
{
	return [NSDate dateWithString:self.dateCreated];
}

- (NSDate *) dateLastSavedAsNSDate
{
	return [NSDate dateWithString:self.dateLastSaved];
}

- (void) dealloc
{
    NSLog(@"deallocing VSProject");
}

@end
