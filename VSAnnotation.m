//
//  VSAnnotation.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/30/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VSAnnotation.h"


@implementation VSAnnotation

@dynamic videoClip;
@dynamic screenX;
@dynamic screenY;
@dynamic startTimecode;
@dynamic width;
@synthesize tempOpacity;

- (NSString *) tableGlyphForColor
{
	return @"█";
}

- (void) dealloc
{
    [self carefullyRemoveObserver:self.videoClip.windowController forKeyPath:@"width"];
    [self carefullyRemoveObserver:self.videoClip.windowController forKeyPath:@"color"];
    [self carefullyRemoveObserver:self.videoClip.windowController forKeyPath:@"size"];
    [self carefullyRemoveObserver:self.videoClip.windowController forKeyPath:@"shape"];
    [self carefullyRemoveObserver:self.videoClip.windowController forKeyPath:@"notes"];
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
