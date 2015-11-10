//
//  VSTrackedEvent.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/11/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSTrackedEvent : VSVisibleItem {

	float tempOpacity;
	
}

@property (strong) NSNumber *index;
@property (strong) NSString *observer;
@property (strong) NSString *name;
@property (strong) VSTrackedEventType *type;
@property (strong) NSSet *trackedObjects;
@property (strong) NSSet *points;
@property (assign) float tempOpacity;		// passed around as an object property during drawing, to prevent having to recalculate opacity or use an extra nsset/array

+ (int) highestEventIndexInProject:(VSProject *)project;

- (NSNumber *) numPoints;
- (NSString *) otherObjectsString;
- (VSPoint *) pointToTakeScreenPointFromClip:(VSVideoClip *)videoClip atTime:(CMTime)currentTime;
- (NSArray *) spreadsheetFormattedConnectingLines;

- (NSXMLNode *) representationAsXMLNode;

@end
