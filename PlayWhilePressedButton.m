/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
 * 
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * 
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 ***********************************************************************************/


#import "PlayWhilePressedButton.h"

@implementation PlayWhilePressedButton

@synthesize direction;
@synthesize advancedRateToUse;

- (void) awakeFromNib
{
    [super awakeFromNib];
    pressedHighlightColor = [NSColor greenColor];
}

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
	} else if (self.advancedRateToUse == 2) {	// use advanced rate 2
		playRate = self.direction * [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"advancedPlaybackRate2"] floatValue];
	} else {    // advancedRate is zero, use 1
        playRate = self.direction;
    }
	[document setAllVideoRates:playRate];
	[document updateMasterTimeDisplay];			// Temp fix; only updates on start and stop; doesn't do overlays
}

- (void) stopPlaying {
	[document pauseAll:self];
	[document updateMasterTimeDisplay];			// Temp fix; only updates on start and stop; doesn't do overlays    
}

@end
