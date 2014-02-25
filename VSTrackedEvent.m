//
//  VSTrackedEvent.m
//  VidSync
//
//  Created by Jason Neuswanger on 1/11/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VSTrackedEvent.h"


@implementation VSTrackedEvent

@dynamic index;
@dynamic name;
@dynamic type;
@dynamic trackedObjects;
@dynamic points;
@synthesize tempOpacity;

+ (int) highestEventIndexInProject:(VSProject *)project
{
	int highestIndex = 0;
	for (VSTrackedObject *object in project.trackedObjects) for (VSTrackedEvent *event in object.trackedEvents) if ([event.index intValue] > highestIndex) highestIndex = [event.index intValue]; 
	return highestIndex;
}

- (NSNumber *) numPoints
{
	return [NSNumber numberWithInt:[self.points count]];
}


- (NSString *) otherObjectsString
{
	NSMutableString *objStr = [NSMutableString stringWithString:@""];
	bool isFirst = true;
	for (VSTrackedObject *object in self.trackedObjects) {
//		I'd like to make this only list objects OTHER than the one currently selected in objectsController, but I don't know how to get that selection.
//		Since I can't get selectedObject, I'm commenting out this bit of code... for now, it lists all objects.
//		if (![object isEqualTo:selectedObject]) {	
		if (!isFirst) [objStr appendString:@", "];
			[objStr appendFormat:@"%@ %@",object.type.name,object.index];
			if (![object.name isEqualToString:@""]) [objStr appendFormat:@" (%@)",object.name];
			isFirst = false;
//		}
	}
	return objStr;
}

+ (NSSet *)keyPathsForValuesAffectingOtherObjectsString
{
	return [NSSet setWithObjects:@"trackedObjects", nil];
}

- (VSPoint *) pointToTakeScreenPointFromClip:(VSVideoClip *)videoClip atTime:(CMTime)currentTime	// When we click a clip in the Measurement tab, this says which VSPoint the click adds to
{
	VSPoint *returnPoint = nil;
	// Look for points at currentTime (master clip timecode) that still need a VSScreenPoint for videoClip.  If there are any, find the one with the lowest index and return it.

    NSString *currentTimeString = [UtilityFunctions CMStringFromTime:currentTime onScale:[[[[[self.trackedObjects anyObject] project] masterClip] timeScale] longValue]];
    
    NSMutableSet __block *pointsAtCurrentTime = [NSMutableSet new];
    [self.points enumerateObjectsUsingBlock:^(id obj, BOOL *stop) {
        if ([UtilityFunctions timeString:[obj timecode] isEqualToTimeString:currentTimeString]) [pointsAtCurrentTime addObject:obj];
    }];
    
//  I'm commenting out a method of doing the above with a predicate, which would work fine for new files and more quickly. Instead, I'm using the above code for compatibility
//  with files that were created when VidSync sometimes recorded timecodes on funny Quicktime/AVKit timescales like 1,000,000,000 instead of the native video scale, and times have to be compared.
//  NSPredicate *atCurrentTime = [NSPredicate predicateWithFormat:@"timecode == %@",currentTimeString];
//	NSSet *pointsAtCurrentTime = [self.points filteredSetUsingPredicate:atCurrentTime];
     
	if ([pointsAtCurrentTime count] > 0) {
		for (VSPoint *maybePoint in pointsAtCurrentTime) {	// Loop over all points at this timecode, looking for the one with the lowest index that doesn't have a screenPoint for videoClip
			if ([maybePoint screenPointForVideoClip:videoClip] == nil) {	// point has no screenPoint for this videoClip
				if (returnPoint == nil) {									// if no return point is set yet, use this one
					returnPoint = maybePoint;
				} else {													// if there is a return point, use this one only if it has a lower index than that one
					if ([maybePoint.index intValue] < [returnPoint.index intValue]) returnPoint = maybePoint;
				}
			}
		}
		if (returnPoint != nil) return returnPoint;
	}
	// If the function hasn't returned yet, that means there wasn't a VSPoint needing a VSEventScreenPoint for videoClip, and we need to create a new one.  
	// First, check if the current event is at its maxNumPoints, and if it is, create a new event to put the new VSPoint into.
	VSTrackedEvent *eventForNewPoint;
	BOOL currentEventIsAtMaxNumPoints = ([self.points count] > 0 && [self.points count] == [self.type.maxNumPoints intValue]);
    BOOL pointsRequireDifferentTimecode = ([self.type.requiresSameTimecode boolValue] && [self.points count] > 0 && ![UtilityFunctions timeString:[[self.points anyObject] timecode] isEqualToTimeString:currentTimeString]);
	if (currentEventIsAtMaxNumPoints || pointsRequireDifferentTimecode) {
		eventForNewPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedEvent" inManagedObjectContext:[self managedObjectContext]]; 
		eventForNewPoint.trackedObjects = self.trackedObjects;
		eventForNewPoint.type = self.type;
		eventForNewPoint.index = [NSNumber numberWithInt:[VSTrackedEvent highestEventIndexInProject:self.type.project]+1];
		[self.type.project.document.trackedEventsController rearrangeObjects];  // Re-sort the events to put the newly inserted one in the correct spot in the list
		[self.type.project.document.trackedEventsController setSelectedObjects:[NSArray arrayWithObject:eventForNewPoint]];
		[self.type.project.document.trackedEventsController scrollTableToSelectedObject];
	} else {
		eventForNewPoint = self;
	}
	// Now create and return a point with a higher index than any of the others.  Index is local within the event.
	int highestPointIndex = 0;
	for (VSPoint *indPoint in self.points) if ([indPoint.index intValue] > highestPointIndex) highestPointIndex = [indPoint.index intValue];
	returnPoint = [NSEntityDescription insertNewObjectForEntityForName:@"VSPoint" inManagedObjectContext:[self managedObjectContext]];
	returnPoint.index = [NSNumber numberWithInt:highestPointIndex+1];
	returnPoint.trackedEvent = eventForNewPoint;
	returnPoint.timecode = currentTimeString;
	[self.type.project.document.eventsPointsController rearrangeObjects];  // Re-sort the points to put the newly inserted one in the correct spot in the list
	return returnPoint;
}


- (NSArray *) spreadsheetFormattedConnectingLines
{	
	if ([self.points count] == 0 || [self.type.connectingLineLengthLabeled boolValue] == NO) return [NSArray arrayWithObject:@""];
	NSMutableArray *connectingLineStrings = [NSMutableArray new];	// stores each line's data in tab-separated strings followed by a newline
	NSArray *sortedPoints = [self.points sortedArrayUsingDescriptors:[NSArray arrayWithObject:[NSSortDescriptor sortDescriptorWithKey:@"index" ascending:YES]]];	
	VSPoint *previousPoint = [sortedPoints objectAtIndex:0];
	for (int i = 1; i < [sortedPoints count]; i++) {
		VSPoint *point = [sortedPoints objectAtIndex:i];
		if ([point has3Dcoords] && [previousPoint has3Dcoords]) {
			VSTrackedObject *trackedObject = [self.trackedObjects anyObject];
			// Construct the object & event name strings
			NSString *objectString;
			if ([trackedObject.name isEqualToString:@""] || trackedObject.name == nil) {
				objectString = [NSString stringWithFormat:@"%@ %@",trackedObject.type.name,trackedObject.index];
			} else {
				objectString = [NSString stringWithFormat:@"%@ %@ (%@)",trackedObject.type.name,trackedObject.index,trackedObject.name];				
			}
			NSString *eventString;
			if ([self.name isEqualToString:@""] || self.name == nil) {
				eventString = [NSString stringWithFormat:@"%@ %@",self.type.name,self.index];
			} else {
				eventString = [NSString stringWithFormat:@"%@ %@ (%@)",self.type.name,self.index,self.name];				
			}			
			NSNumber *distance = [point distanceToVSPoint:previousPoint];
			[connectingLineStrings addObject:[NSString stringWithFormat:@"%@\t%@\t%@\n",objectString,eventString,distance]];
		}
		previousPoint = point;
	}
	return connectingLineStrings;
}

- (NSXMLNode *) representationAsXMLNode
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"event"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"type" stringValue:self.type.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"index" stringValue:[self.index stringValue]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"notes" stringValue:self.notes]];
	NSSortDescriptor *indexDescriptor = [[NSSortDescriptor alloc] initWithKey:@"index" ascending:YES];	
	NSArray *sortedPoints = [[self.points allObjects] sortedArrayUsingDescriptors:[NSArray arrayWithObjects:indexDescriptor,nil]];
	for (VSPoint *point in sortedPoints) [mainElement addChild:[point representationAsXMLNode]];
	for (VSTrackedObject *object in self.trackedObjects) [mainElement addChild:[object representationAsXMLChildOfEvent]];
	return mainElement;	
}

@end
