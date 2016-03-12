/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
 * 
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * 
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 ***********************************************************************************/


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
