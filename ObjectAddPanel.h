//
//  ObjectAddPanel.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/1/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//
//  I'm subclassing NSPanel here so I can implement proper behavior of the "color" control with regard to the selected object type's color.


#import <Cocoa/Cocoa.h>


@interface ObjectAddPanel : NSPanel {	

	IBOutlet NSColorWell *__weak colorWell;
	IBOutlet NSPopUpButton *__weak typeButton;
	
}

- (void)makeKeyAndOrderFront:(id)sender;
- (IBAction) updateColor:(id)sender;

@end
