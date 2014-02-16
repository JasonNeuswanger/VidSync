//
//  VSTrackedObject.m
//  VidSync
//
//  Created by Jason Neuswanger on 1/7/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VSTrackedObject.h"


@implementation VSTrackedObject

@dynamic index;
@dynamic name;
@dynamic type;
@dynamic project;
@dynamic trackedEvents;

+ (int) highestObjectIndexInProject:(VSProject *)project
{
	int highestIndex = 0;
	for (VSTrackedObject *object in project.trackedObjects) if ([object.index intValue] > highestIndex) highestIndex = [object.index intValue]; 
	return highestIndex;
}

- (NSNumber *) numEvents
{
	return [NSNumber numberWithInt:[self.trackedEvents count]];
}

- (NSString *) tableGlyphForColor
{
	return @"█";
}

+ (NSSet *)keyPathsForValuesAffectingNumEvents
{
	return [NSSet setWithObjects:@"trackedEvents", nil];
}

- (void)prepareForDeletion
{
	for (VSTrackedEvent *event in self.trackedEvents) {
		if ([event.trackedObjects count] == 1) {
			[[self managedObjectContext] deleteObject:event];	// delete events that are associated with this object & not with any other objects
		}
	}
}

- (NSXMLNode *) representationAsXMLNode
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"object"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"type" stringValue:self.type.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"index" stringValue:[self.index stringValue]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"colorR" stringValue:[NSString stringWithFormat:@"%1.4f",[self.color redComponent]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"colorG" stringValue:[NSString stringWithFormat:@"%1.4f",[self.color greenComponent]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"colorB" stringValue:[NSString stringWithFormat:@"%1.4f",[self.color blueComponent]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"notes" stringValue:self.notes]];
	for (VSTrackedEvent *trackedEvent in self.trackedEvents) [mainElement addChild:[trackedEvent representationAsXMLNode]];
	return mainElement;
}

- (NSXMLNode *) representationAsXMLChildOfEvent
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"objectChildOfEvent"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"type" stringValue:self.type.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"index" stringValue:[self.index stringValue]]];
	return mainElement;	
}

- (void) split	
{
	// splits the object's event around the current timecode, placing all events with a later timecode into a new and otherwise identical object
	// events that have no point with a timecode stay with the current object (e.g. they're ignored)
	// events with points on either side of the current timecode (a very rare case probably) get moved depending on what anyObject randomly chooses
	// if the point is right AT the current timecode, it stays with the original object
	
	VSTrackedObject *newObj = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObject" inManagedObjectContext:[self managedObjectContext]];	
	newObj.name = [NSString stringWithFormat:@"%@_split",self.name];
	newObj.type = self.type;
	newObj.color = self.color;
	newObj.index = [NSNumber numberWithInt:[VSTrackedObject highestObjectIndexInProject:self.project]+1];
	
	
	NSMutableSet *eventsObjects;
	CMTime currentTime = [self.project.document currentMasterTime];
	CMTime eventTime;
	NSArray *allEvents = [self.trackedEvents allObjects];
	VSTrackedEvent *event;
	for (int i = 0; i < [allEvents count]; i++) {
		event = [allEvents objectAtIndex:i];
		if ([event.points count] > 0) {
			eventTime = [UtilityFunctions CMTimeFromString:[[event.points anyObject] timecode]];
			if (CMTimeCompare(eventTime,currentTime) == NSOrderedDescending) {
				eventsObjects = [NSMutableSet setWithSet:event.trackedObjects];
				[eventsObjects addObject:newObj];
				[eventsObjects removeObject:self];
				event.trackedObjects = eventsObjects;
			}
		}
	}
	
	newObj.project = self.project;
}


@end
