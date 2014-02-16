//
//  TypesArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/9/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface TypesArrayController : NSArrayController {

	IBOutlet VidSyncDocument *document;
	IBOutlet NSTextField *newTypeName;
	IBOutlet NSTextField *newTypeDescription;
	IBOutlet NSPanel *inputPanel;
	
}

- (IBAction) add:(id)sender;

@end
