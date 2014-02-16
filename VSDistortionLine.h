//
//  VSDistortionLine.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/18/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSDistortionLine : NSManagedObject {
	
}

@property (strong) NSNumber *lambda;
@property (strong) NSString *timecode;
@property (strong) VSCalibration *calibration;
@property (strong) NSSet *distortionPoints;

- (NSNumber *)numPoints;

- (NSXMLNode *) representationAsXMLNode;

@end
