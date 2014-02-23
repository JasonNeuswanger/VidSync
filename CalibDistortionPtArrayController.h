//
//  CalibDistortionPtArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/22/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@class CalibDistortionLineArrayController;

@interface CalibDistortionPtArrayController : VSVisibleItemArrayController {
    
    IBOutlet CalibDistortionLineArrayController *__weak distortionLinesController;
    
}

@end
