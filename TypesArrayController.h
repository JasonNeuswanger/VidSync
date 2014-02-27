//
//  TypesArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/9/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface TypesArrayController : NSArrayController {

	IBOutlet VidSyncDocument *__weak document;
	IBOutlet NSTextField *__weak newTypeName;
	IBOutlet NSTextField *__weak newTypeDescription;
	IBOutlet NSPanel *__weak inputPanel;
	
}

- (IBAction) add:(id)sender;

@end
