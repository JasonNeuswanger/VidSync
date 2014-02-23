//
//  VSTrackedObjectPortrait.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <CoreData/CoreData.h>
#import <ImageKit/ImageKit.h>

@interface VSTrackedObjectPortrait : NSManagedObject {

    NSImage __strong *image;
    
}

@property (strong) NSString *timecode;
@property (strong) NSData *imageData;
@property (strong) NSString *frameString;
@property (strong) VSTrackedObject *trackedObject;
@property (strong) VSVideoClip *sourceVideoClip;

- (void) setImage:(NSImage *)imageSource;


// Methods to conform to the informal protocol IKImageBrowserItem
- (NSString *) imageUID;
- (NSString *) imageTitle;
- (NSString *) imageRepresentationType;
- (id) imageRepresentation;
- (BOOL) isSelectable;


@end
