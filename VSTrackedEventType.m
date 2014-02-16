//
//  VSTrackedEventType.m
//  VidSync
//
//  Created by Jason Neuswanger on 11/20/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

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

@dynamic project;

- (void)awakeFromFetch
{
	// Observe the values of all the visually obvious fields, so the overlays can be updated live when they're changed.
	[self addObserver:self forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"shape" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"size" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineLengthLabeled" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineThickness" options:NSKeyValueObservingOptionNew context:NULL];
	[self addObserver:self forKeyPath:@"connectingLineType" options:NSKeyValueObservingOptionNew context:NULL];	
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelFontSize" options:NSKeyValueObservingOptionNew context:NULL];	
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelFractionDigits" options:NSKeyValueObservingOptionNew context:NULL];	
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelUnitMultiplier" options:NSKeyValueObservingOptionNew context:NULL];	
	[self addObserver:self forKeyPath:@"connectingLineLengthLabelUnits" options:NSKeyValueObservingOptionNew context:NULL];	
	[super awakeFromFetch];
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
	if ([keyPath isEqualToString:@"name"]) {
		[self.project.document.trackedEventTypesController rearrangeObjects];
	} else {
		if ([object class] == [VSTrackedEventType class]) [self.project.document refreshOverlaysOfAllClips:self];	// If any overlay-visible event type attributes change, refresh all the overlays.
	}
}

+ (void) insertNewTypeFromLoadedDictionary:(NSDictionary *)eventTypeDictionary inProject:(VSProject *)project inManagedObjectContext:(NSManagedObjectContext *)moc
{
	VSTrackedEventType *newType = nil;
	for (VSTrackedEventType *oldType in project.trackedEventTypes) {
		if ([oldType.name isEqualToString:[eventTypeDictionary objectForKey:@"name"]]) {		// If a type exists with the same name as the one being imported, overwrite it.
			newType = oldType;
		}
	}
	if (newType == nil) newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedEventType" inManagedObjectContext:moc];
	[newType addObserver:newType forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	newType.project = project;
	newType.name = [eventTypeDictionary objectForKey:@"name"];
	newType.maxNumPoints = [eventTypeDictionary objectForKey:@"maxNumPoints"];
	newType.connectingLineType = [eventTypeDictionary objectForKey:@"connectingLineType"];
	newType.requiresSameTimecode = [eventTypeDictionary objectForKey:@"requiresSameTimecode"];
	newType.connectingLineLengthLabeled = [eventTypeDictionary objectForKey:@"connectingLineLengthLabeled"];
	newType.connectingLineThickness = [eventTypeDictionary objectForKey:@"connectingLineThickness"];
	newType.connectingLineLengthLabelFontSize = [eventTypeDictionary objectForKey:@"connectingLineLengthLabelFontSize"];
	newType.connectingLineLengthLabelFractionDigits = [eventTypeDictionary objectForKey:@"connectingLineLengthLabelFractionDigits"];
	newType.connectingLineLengthLabelUnitMultiplier = [eventTypeDictionary objectForKey:@"connectingLineLengthLabelUnitMultiplier"];
	newType.connectingLineLengthLabelUnits = [eventTypeDictionary objectForKey:@"connectingLineLengthLabelUnits"];
	[newType setVisibleItemPropertiesFromDictionary:eventTypeDictionary];	
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
	[superDict setObject:self.connectingLineLengthLabelFontSize forKey:@"connectingLineLengthLabelFontSize"];	
	[superDict setObject:self.connectingLineLengthLabelFractionDigits forKey:@"connectingLineLengthLabelFractionDigits"];	
	[superDict setObject:self.connectingLineLengthLabelUnitMultiplier forKey:@"connectingLineLengthLabelUnitMultiplier"];	
	[superDict setObject:self.connectingLineLengthLabelUnits forKey:@"connectingLineLengthLabelUnits"];	
	
	return superDict;
}

@end
