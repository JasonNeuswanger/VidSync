//
//  VSDistortionPoint.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/18/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import "VSDistortionPoint.h"


@implementation VSDistortionPoint

@dynamic screenX;
@dynamic screenY;
@dynamic index;
@dynamic distortionLine;

- (NSXMLNode *) representationAsXMLNode	// partial implementation
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"distortionPoint"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"index" stringValue:[self.index stringValue]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"x" stringValue:[self.screenX stringValue]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"y" stringValue:[self.screenY stringValue]]];
	return mainElement;
}

@end
