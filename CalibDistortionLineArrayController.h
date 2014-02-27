//
//  CalibDistortionLineArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/18/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface CalibDistortionLineArrayController : VSVisibleItemArrayController {

	IBOutlet VidSyncDocument *__weak document;
	
}

- (IBAction) add:(id)sender;
- (IBAction) goToLine:(id)sender;

- (void) appendPointToSelectedLineAt:(NSPoint)coords;
- (void) addNewAutodetectedLineWithNumber:(int)number ofPoints:(void *)points;

@end
