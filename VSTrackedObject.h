//
//  VSTrackedObject.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/7/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSTrackedObject : VSVisibleItem {
	
}

@property (strong) NSNumber *index;
@property (strong) NSString *name;
@property (strong) VSTrackedObjectType *type;
@property (strong) VSProject *project;
@property (strong) NSSet *trackedEvents;

+ (int) highestObjectIndexInProject:(VSProject *)project;

- (NSNumber *) numEvents;
- (NSString *) tableGlyphForColor;

- (NSXMLNode *) representationAsXMLNode;
- (NSXMLNode *) representationAsXMLChildOfEvent;

- (void) split;

@end
