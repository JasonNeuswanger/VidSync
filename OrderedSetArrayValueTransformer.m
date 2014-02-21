//
//  OrderedSetArrayValueTransformer.m
//  VidSync
//
//  Modified from http://www.wannabegeek.com/?p=74
//

#import "OrderedSetArrayValueTransformer.h"

@implementation OrderedSetArrayValueTransformer

+ (Class)transformedValueClass {
    return [NSArray class];
}

+ (BOOL)allowsReverseTransformation {
    return YES;
}

- (id)transformedValue:(id)value {
    return [(NSOrderedSet *)value array];
}

- (id)reverseTransformedValue:(id)value {
	return [NSOrderedSet orderedSetWithArray:value];
}

@end
