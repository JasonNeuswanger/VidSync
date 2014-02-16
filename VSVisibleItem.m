//
//  VSVisibleItem.m
//  VidSync
//
//  Created by Jason Neuswanger on 11/20/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

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
