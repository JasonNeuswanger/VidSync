//
//  VSScreenPoint.h
//  VidSync
//
//  Created by Jason Neuswanger on 11/12/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class VSCalibration;

@interface VSCalibrationPoint : NSManagedObject {
    
}

@property (strong) NSNumber *screenX;
@property (strong) NSNumber *screenY;
@property (strong) NSNumber *worldHcoord;
@property (strong) NSNumber *worldVcoord;
@property (strong) NSNumber *index;
@property (strong) VSCalibration *calibration;

@property (strong) NSNumber *apparentWorldHcoord;   // These are the values actually used in the calibration.  Depending on refraction correction settings and which face they're on, they're either corrected
@property (strong) NSNumber *apparentWorldVcoord;   // for refraction or they're just direct copies of worldHcoord and worldVcoord.

- (NSXMLNode *) representationAsXMLNode;

@end
