//
//  VSColorCoreDataTransformer.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/22/21.
//  Copyright © 2021 Jason Neuswanger. All rights reserved.
//

#import "VSColorCoreDataTransformer.h"

@implementation VSColorCoreDataTransformer

+ (NSArray<Class> *)allowedTopLevelClasses {

	   return @[NSColor.class];
}

@end
