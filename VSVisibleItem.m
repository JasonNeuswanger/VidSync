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


#import "VSVisibleItem.h"


@implementation VSVisibleItem

@dynamic color;
@dynamic notes;
@dynamic duration;
@dynamic fadeTime;
@dynamic shape;
@dynamic size;

- (NSMutableDictionary *) contentsAsWriteableDictionary
{
	NSDictionary *colorDict = [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithFloat:[self.color redComponent]],@"red",
																	   [NSNumber numberWithFloat:[self.color greenComponent]],@"green",
																		[NSNumber numberWithFloat:[self.color blueComponent]],@"blue",
																	   [NSNumber numberWithFloat:[self.color alphaComponent]],@"alpha",
							   nil];
	NSString *notesToStore;	// I don't know why this middleman variable is necessary, but I get odd problems without it
	if (self.notes == nil) {
		notesToStore = @"nil";
	} else {
		notesToStore = self.notes;
	}
	NSMutableDictionary *fullDict = [NSMutableDictionary dictionaryWithObjectsAndKeys:colorDict,@"color",
														  notesToStore,@"notes",
														 self.duration,@"duration",
														 self.fadeTime,@"fadeTime",
														    self.shape,@"shape",
															 self.size,@"size",
			nil];
	return fullDict;
}

- (void) setVisibleItemPropertiesFromDictionary:(NSDictionary *)typeDictionary
{
	NSDictionary *colorDictionary = [typeDictionary objectForKey:@"color"];
	self.color = [NSColor colorWithCalibratedRed:[[colorDictionary objectForKey:@"red"] floatValue]
									   green:[[colorDictionary objectForKey:@"green"] floatValue]
										blue:[[colorDictionary objectForKey:@"blue"] floatValue]
									   alpha:[[colorDictionary objectForKey:@"alpha"] floatValue]
	];
	if (![[typeDictionary objectForKey:@"notes"] isEqualToString:@"nil"]) self.notes = [typeDictionary objectForKey:@"notes"];
	self.duration = [typeDictionary objectForKey:@"duration"];
	self.fadeTime = [typeDictionary objectForKey:@"fadeTime"];
	self.shape = [typeDictionary objectForKey:@"shape"];
	self.size = [typeDictionary objectForKey:@"size"];
	
}


@end
