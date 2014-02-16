//
//  PlayWhilePressedButton.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/23/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface PlayWhilePressedButton : NSButton {

	IBOutlet VidSyncDocument *document;
	float direction;
	int advancedRateToUse;
	
}

@property (assign) float direction;
@property (assign) int advancedRateToUse;

- (void) startPlaying;
- (void) stopPlaying;

@end
