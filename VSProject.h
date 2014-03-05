//
//  VSProject.h
//  VidSync
//
//  Created by Jason Neuswanger on 10/25/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class VidSyncDocument;

@interface VSProject : NSManagedObject {
    
	VidSyncDocument *__weak document;

}

@property (strong) NSString *name;
@property (strong) NSString *notes;
@property (strong) NSString *currentTimecode;
@property (strong) NSString *calibrationTimecode;
@property (strong) NSString *dateCreated;
@property (strong) NSString *dateLastSaved;
@property (strong) VSVideoClip *masterClip;
@property (strong) NSMutableSet *videoClips;

@property (strong) NSNumber *useIterativeTriangulation;

@property (strong) NSString *exportPathForData;
@property (strong) NSNumber *exportClipSelectedClipName;
@property (strong) NSString *capturePathForMovies;
@property (strong) NSString *capturePathForStills;
@property (strong) NSString *movieCaptureStartTime;
@property (strong) NSString *movieCaptureEndTime;

@property (weak) VidSyncDocument *document;
@property (strong) NSMutableSet *trackedObjectTypes;
@property (strong) NSMutableSet *trackedEventTypes;
@property (strong) NSMutableSet *trackedObjects;
@property (strong) NSMutableSet *trackedEvents;

- (NSDate *) dateCreatedAsNSDate;
- (NSDate *) dateLastSavedAsNSDate;

@end
