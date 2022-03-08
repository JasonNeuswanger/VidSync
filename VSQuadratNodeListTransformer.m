//
//  VSQuadratNodeListTransformer.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/22/21.
//  Copyright © 2021 Jason Neuswanger. All rights reserved.
//

#import "VSQuadratNodeListTransformer.h"

@implementation VSQuadratNodeListTransformer

+ (NSArray<Class> *)allowedTopLevelClasses {

	   return @[NSAttributedString.class];
}

@end
