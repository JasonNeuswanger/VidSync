//
//  VSHintLine.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/25/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class VSEventScreenPoint;
@class VSVideoClip;

@interface VSHintLine : NSManagedObject {
		
}

@property (strong) NSNumber *frontSurfaceX;
@property (strong) NSNumber *frontSurfaceY;
@property (strong) NSNumber *backSurfaceX;
@property (strong) NSNumber *backSurfaceY;
@property (strong) VSEventScreenPoint *fromScreenPoint;
@property (strong) VSVideoClip *toVideoClip;

+ (void) createHintLineFromScreenPoint:(VSEventScreenPoint *)screenPoint toVideoClip:(VSVideoClip *)videoClip;

- (NSBezierPath *) bezierPathForLineWithInterval:(float)interval;

@end
