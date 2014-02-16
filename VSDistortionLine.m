//
//  VSDistortionLine.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/18/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import "VSDistortionLine.h"


@implementation VSDistortionLine

@dynamic lambda;
@dynamic timecode;
@dynamic calibration;
@dynamic distortionPoints;

- (NSNumber *)numPoints
{
	return [NSNumber numberWithFloat:[self.distortionPoints count]];
}

- (NSXMLNode *) representationAsXMLNode	// partial implementation
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"distortionLine"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"timecode" stringValue:self.timecode]];
	for (VSDistortionPoint *distortionPoint in self.distortionPoints) [mainElement addChild:[distortionPoint representationAsXMLNode]];
	return mainElement;
}

@end
