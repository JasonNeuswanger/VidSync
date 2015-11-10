//
//  VSTrackedObject.h
//  VidSync
//
//  Created by Jason Neuswanger on 1/7/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSTrackedObject : VSVisibleItem {
    
    NSString __strong *portraitStatus;
	
}

@property (strong) NSNumber *index;
@property (strong) NSString *observer;
@property (strong) NSString *name;
@property (strong) VSTrackedObjectType *type;
@property (strong) VSProject *project;
@property (strong) NSSet *trackedEvents;
@property (strong) NSOrderedSet *portraits;

+ (int) highestObjectIndexInProject:(VSProject *)project;

- (NSNumber *) numEvents;
- (NSAttributedString *) tableGlyphForColor;
- (NSAttributedString *) tableGlyphForPortrait;

- (NSXMLNode *) representationAsXMLNode;
- (NSXMLNode *) representationAsXMLChildOfEvent;

- (void) split;

@end
