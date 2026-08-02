/*********************************************************************************                                                                       
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2021 Jason Neuswanger
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


#import "VSTrackedEventType.h"


@implementation VSTrackedEventType

@dynamic name;
@dynamic maxNumPoints;
@dynamic requiresSameTimecode;

@dynamic connectingLineType;
@dynamic connectingLineLengthLabeled;
@dynamic connectingLineThickness;
@dynamic connectingLineLengthLabelFontSize;
@dynamic connectingLineLengthLabelFractionDigits;
@dynamic connectingLineLengthLabelUnitMultiplier;
@dynamic connectingLineLengthLabelUnits;
@dynamic connectingLineLabelShowLength;
@dynamic connectingLineLabelShowSpeed;

@dynamic trackedEvents;

@dynamic project;

- (void)awakeFromFetch
{
	[self addObservers];
	[super awakeFromFetch];
}

- (void)awakeFromInsert
{
	[self addObservers];
	[super awakeFromInsert];
}

- (void)addObservers
{
	[self addObserver:self forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"shape" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"size" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLengthLabeled" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLabelShowLength" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLabelShowSpeed" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineThickness" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineType" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelFontSize" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelFractionDigits" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelUnitMultiplier" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelUnits" options:NSKeyValueObservingOptionNew context:NULL];
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
	if ([keyPath isEqualToString:@"name"]) {
		[self.project.document.trackedEventTypesController rearrangeObjects];
	} else {
		if ([object class] == [VSTrackedEventType class]) [self.project.document refreshOverlaysOfAllClips:self];	// If any overlay-visible event type attributes change, refresh all the overlays.
	}
}

+ (NSDictionary *) loadedDictionaryWithCompatibilityDefaults:(NSDictionary *)eventTypeDictionary
{
	// Fills in defaults for keys that may be missing from files saved by older versions of VidSync.
	NSMutableDictionary *dict = [eventTypeDictionary mutableCopy];
	if ([dict objectForKey:@"connectingLineLabelShowLength"] == nil) [dict setObject:[NSNumber numberWithBool:NO] forKey:@"connectingLineLabelShowLength"];
	if ([dict objectForKey:@"connectingLineLabelShowSpeed"] == nil) [dict setObject:[NSNumber numberWithBool:NO] forKey:@"connectingLineLabelShowSpeed"];
	return dict;
}

+ (VSTrackedEventType *) insertNewTypeFromLoadedDictionary:(NSDictionary *)eventTypeDictionary withName:(NSString *)name inProject:(VSProject *)project inManagedObjectContext:(NSManagedObjectContext *)moc
{
	VSTrackedEventType *newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedEventType" inManagedObjectContext:moc];
	newType.project = project;
	newType.name = name;
	[newType updatePropertiesFromLoadedDictionary:eventTypeDictionary];
	return newType;
}

- (void) updatePropertiesFromLoadedDictionary:(NSDictionary *)eventTypeDictionary
{
	NSDictionary *dict = [VSTrackedEventType loadedDictionaryWithCompatibilityDefaults:eventTypeDictionary];
	self.maxNumPoints = [dict objectForKey:@"maxNumPoints"];
	self.connectingLineType = [dict objectForKey:@"connectingLineType"];
	self.requiresSameTimecode = [dict objectForKey:@"requiresSameTimecode"];
	self.connectingLineLengthLabeled = [dict objectForKey:@"connectingLineLengthLabeled"];
	self.connectingLineThickness = [dict objectForKey:@"connectingLineThickness"];
	self.connectingLineLabelShowLength = [dict objectForKey:@"connectingLineLabelShowLength"];
	self.connectingLineLabelShowSpeed = [dict objectForKey:@"connectingLineLabelShowSpeed"];
	self.connectingLineLengthLabelFontSize = [dict objectForKey:@"connectingLineLengthLabelFontSize"];
	self.connectingLineLengthLabelFractionDigits = [dict objectForKey:@"connectingLineLengthLabelFractionDigits"];
	self.connectingLineLengthLabelUnitMultiplier = [dict objectForKey:@"connectingLineLengthLabelUnitMultiplier"];
	self.connectingLineLengthLabelUnits = [dict objectForKey:@"connectingLineLengthLabelUnits"];
	[super updatePropertiesFromLoadedDictionary:dict];
}

- (BOOL) propertiesMatchLoadedDictionary:(NSDictionary *)eventTypeDictionary
{
	return [super propertiesMatchLoadedDictionary:[VSTrackedEventType loadedDictionaryWithCompatibilityDefaults:eventTypeDictionary]];
}

- (BOOL) canSafelyUpdateFromLoadedDictionary:(NSDictionary *)eventTypeDictionary
{
	// Overwriting this type with the loaded settings would leave existing events incompatible with their own type if an event already has
	// more points than the loaded maxNumPoints, or has points at multiple timecodes when the loaded settings require a shared timecode.
	int newMaxNumPoints = [[eventTypeDictionary objectForKey:@"maxNumPoints"] intValue];
	BOOL newRequiresSameTimecode = [[eventTypeDictionary objectForKey:@"requiresSameTimecode"] boolValue];
	for (VSTrackedEvent *event in self.trackedEvents) {
		if (newMaxNumPoints > 0 && (int) [event.points count] > newMaxNumPoints) return NO;
		if (newRequiresSameTimecode) {
			NSString *firstTimecode = nil;
			for (VSPoint *point in event.points) {
				if (firstTimecode == nil) {
					firstTimecode = point.timecode;
				} else if (![UtilityFunctions timeString:point.timecode isEqualToTimeString:firstTimecode]) {
					return NO;
				}
			}
		}
	}
	return YES;
}

- (NSMutableDictionary *) contentsAsWriteableDictionary
{
	NSMutableDictionary *superDict = [super contentsAsWriteableDictionary];
	[superDict setObject:self.name forKey:@"name"];
	[superDict setObject:self.maxNumPoints forKey:@"maxNumPoints"];
	[superDict setObject:self.requiresSameTimecode forKey:@"requiresSameTimecode"];
	
	[superDict setObject:self.connectingLineType forKey:@"connectingLineType"];
	[superDict setObject:self.connectingLineLengthLabeled forKey:@"connectingLineLengthLabeled"];
	[superDict setObject:self.connectingLineThickness forKey:@"connectingLineThickness"];
	[superDict setObject:self.connectingLineLabelShowLength forKey:@"connectingLineLabelShowLength"];
	[superDict setObject:self.connectingLineLabelShowSpeed forKey:@"connectingLineLabelShowSpeed"];
	[superDict setObject:self.connectingLineLengthLabelFontSize forKey:@"connectingLineLengthLabelFontSize"];
	[superDict setObject:self.connectingLineLengthLabelFractionDigits forKey:@"connectingLineLengthLabelFractionDigits"];
	[superDict setObject:self.connectingLineLengthLabelUnitMultiplier forKey:@"connectingLineLengthLabelUnitMultiplier"];
	[superDict setObject:self.connectingLineLengthLabelUnits forKey:@"connectingLineLengthLabelUnits"];
	
	return superDict;
}

- (void) dealloc
{
	[self carefullyRemoveObserver:self forKeyPath:@"name"];
	[self carefullyRemoveObserver:self forKeyPath:@"shape"];
	[self carefullyRemoveObserver:self forKeyPath:@"size"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineLengthLabeled"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineThickness"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineLabelShowLength"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineLabelShowSpeed"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineType"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineLengthLabelFontSize"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineLengthLabelFractionDigits"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineLengthLabelUnitMultiplier"];
	[self carefullyRemoveObserver:self forKeyPath:@"connectingLineLengthLabelUnits"];
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
