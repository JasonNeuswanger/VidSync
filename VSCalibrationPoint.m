//
//  VSScreenPoint.m
//  VidSync
//
//  Created by Jason Neuswanger on 11/12/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VSCalibrationPoint.h"


@implementation VSCalibrationPoint

@dynamic screenX;
@dynamic screenY;
@dynamic worldHcoord;
@dynamic worldVcoord;
@dynamic index;
@dynamic calibration;

@synthesize apparentWorldHcoord;
@synthesize apparentWorldVcoord;

- (NSXMLNode *) representationAsXMLNode
{
	NSNumberFormatter *nf = self.calibration.videoClip.project.document.decimalFormatter;
    NSPoint screenPoint = NSMakePoint([self.screenX floatValue],[self.screenY floatValue]);
    NSPoint undistortedScreenPoint = [self.calibration undistortPoint:screenPoint];
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"screenpoint"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"x" stringValue:[nf stringFromNumber:self.screenX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"y" stringValue:[nf stringFromNumber:self.screenY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"xu" stringValue:[nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.x]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"yu" stringValue:[nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.y]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"worldHcoord" stringValue:[nf stringFromNumber:self.worldHcoord]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"worldVcoord" stringValue:[nf stringFromNumber:self.worldVcoord]]];    
	return mainElement;
}

@end
