//
//  VS2DMatrixToStringTransformer.m
//  VidSync
//
//  Created by Jason Neuswanger on 11/17/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VS2DMatrixToStringTransformer.h"


@implementation VS2DMatrixToStringTransformer

+ (Class)transformedValueClass { return [NSString class]; }

+ (BOOL)allowsReverseTransformation { return NO; }

- (id)transformedValue:(id)value {
	if (value == nil) {
		return nil;
	} else {
		NSMutableString *fullString = [NSMutableString new];
		NSMutableString *rowString;		
		NSNumberFormatter *nf = [[NSNumberFormatter alloc] init];
		[nf setFormatterBehavior:NSNumberFormatterBehavior10_4];
		[nf setNumberStyle:NSNumberFormatterScientificStyle];
		[nf setUsesSignificantDigits:YES];
		[nf setMaximumSignificantDigits:5];
		[nf setPositivePrefix:@" "];
		[nf setPositiveSuffix:@"    "];
		[nf setNegativeSuffix:@"    "];
		for (NSArray *row in value) {
			rowString = [NSMutableString new];
			for (NSNumber *num in row) [rowString appendString:[nf stringFromNumber:num]];
			[fullString appendFormat:@"%@\n",rowString];
		}
		return fullString;	
	}	
}

@end
