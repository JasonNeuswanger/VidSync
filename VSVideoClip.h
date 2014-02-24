//
//  VSVideoClip.h
//  VidSync
//
//  Created by Jason Neuswanger on 10/23/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>
@class VideoWindowController;
@class VSProject;
@class VSCalibration;

@interface VSVideoClip : NSManagedObject {
    
	float frameRate;
    
}

@property (strong) NSString *clipName;
@property (strong) NSString *fileName;
@property (strong) NSString *syncOffset;
@property (strong) NSString *windowFrame;
@property (strong) VSCalibration *calibration;
@property (strong) VSProject *project;
@property (strong) VSProject *isMasterClipOf;
@property (strong) NSNumber *syncIsLocked;
@property (strong) NSSet *eventScreenPoints;
@property (strong) NSSet *hintLines;
@property (strong) NSSet *annotations;

@property (strong) VideoWindowController *windowController;
@property (strong) NSString *masterButtonText;

- (void) relocateClip;

- (void) setMasterControls;

- (NSNumber *) timeScale;

- (NSString *) clipLength;

- (NSString *) clipResolution;

- (double) clipHeight;
- (double) clipWidth;

- (void) setAsMaster;

- (void) setSyncOffset;

- (float)frameRate;

- (BOOL) isAtCalibrationTime;

- (BOOL) isCalibrated;

- (NSXMLNode *) representationAsXMLNode;

@end
