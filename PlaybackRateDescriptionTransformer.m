//
//  PlaybackRateDescriptionTransformer.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/20/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PlaybackRateDescriptionTransformer.h"

// Transforms an advanced playback rate (NSNumber float) to a qualitative description, i.e. slow motion or fast forward, for display in the playback controls

@implementation PlaybackRateDescriptionTransformer

+ (Class)transformedValueClass { return [NSString class]; }

+ (BOOL)allowsReverseTransformation { return NO; }

- (id)transformedValue:(id)value {
	if (value == nil) {
		return nil;
	} else {
        NSNumber *playbackRate = (NSNumber *) value;
        if ([playbackRate floatValue] < 1.0f) {
            return @"(slow motion)";
        } else if ([playbackRate floatValue] > 1.0f) {
            return @"(fast forward/reverse)";
        } else {
            return @"(normal speed playback)";
        }
	}
}

@end
