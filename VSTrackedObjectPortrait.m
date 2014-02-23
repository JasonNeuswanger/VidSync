//
//  VSTrackedObjectPortrait.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "VSTrackedObjectPortrait.h"

@implementation VSTrackedObjectPortrait

@dynamic timecode;
@dynamic imageData;
@dynamic trackedObject;
@dynamic sourceVideoClip;
@dynamic frameString;

- (void) setImage:(NSImage *)imageSource
{
    self.imageData = [imageSource TIFFRepresentationUsingCompression:NSTIFFCompressionJPEG factor:0.6f];
}

#pragma mark
#pragma mark IKImageBrowserItem informal protocol conformation methods
// Note: IKImageBrowserItem is an INFORMAL protocol, not defined in any headers, so I don't have to declare this class as conforming to the protocol

- (NSString *) imageUID
{
    return [NSString stringWithFormat:@"Object %@ portrait from %@ in %@ at %@",self.trackedObject.index,self.sourceVideoClip.clipName,self.frameString,self.timecode];
}

- (NSString *) imageTitle
{
    return [self imageUID];
}

- (NSString *) imageRepresentationType
{
    return IKImageBrowserNSImageRepresentationType;
}

- (id) imageRepresentation
{
    if (image == nil) {
        image = [[NSImage alloc] initWithData:self.imageData];
        return image;
        
    } else {
        return image;
    }
}

- (BOOL) isSelectable
{
    return YES;
}

@end
