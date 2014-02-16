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

@end
