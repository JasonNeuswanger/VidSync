//
//  VSDistortionPoint.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/18/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSDistortionPoint : NSManagedObject {
	
}

@property (strong) NSNumber *screenX;
@property (strong) NSNumber *screenY;
@property (strong) NSNumber *index;
@property (strong) VSDistortionLine *distortionLine;

- (NSXMLNode *) representationAsXMLNode;

@end
