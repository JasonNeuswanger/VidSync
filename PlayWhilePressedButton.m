//
//  PlayWhilePressedButton.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/23/10.
//  Copyright 2010 Jason Neuswanger. All rights reserved.
//

#import "PlayWhilePressedButton.h"

@implementation PlayWhilePressedButton

@synthesize direction;
@synthesize advancedRateToUse;

- (void) mouseDown:(NSEvent *)theEvent
{
    [self startPlaying];
	[super mouseDown:theEvent];
	[self mouseUp:theEvent];		// the [super mouseDown] kills the normal mouseUp; it also waits until the mouse is actually up to execute this call to mouseUp.
}

- (void) mouseUp:(NSEvent *)theEvent
{
    [self stopPlaying];
	[super mouseUp:theEvent];
}

- (void) startPlaying {
	float playRate;
	if (self.advancedRateToUse == 1) {
		playRate = self.direction * [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackRate1"] floatValue];
	} else {	// use advanced rate 2
		playRate = self.direction * [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackRate2"] floatValue];
	}
	[document setAllVideoRates:playRate];
	[document updateMasterTimeDisplay];			// Temp fix; only updates on start and stop; doesn't do overlays
}

- (void) stopPlaying {
	[document pauseAll:self];
	[document updateMasterTimeDisplay];			// Temp fix; only updates on start and stop; doesn't do overlays    
}

@end
