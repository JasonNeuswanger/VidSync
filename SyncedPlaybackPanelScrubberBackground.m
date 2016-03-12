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


#import "SyncedPlaybackPanelScrubberBackground.h"

@implementation SyncedPlaybackPanelScrubberBackground

- (id)initWithFrame:(NSRect)frame
{
    self = [super initWithFrame:frame];
    if (self) {
        [self setWantsLayer:YES];
        
        // Apple's upgrade from Mavericks (10.9) to Yosemite (10.10) changed the default color of NSSliders to be darker so they no longer
        // contrasted against the dark background of my video control. Therefore I'm using a Core Animation to invert the appearance of the
        // entire layer to restore light, contrasting controls and ticks.
        
        CIFilter *invertFilter = [CIFilter filterWithName:@"CIColorInvert"];
        [invertFilter setDefaults];
        self.layer.filters = [NSArray arrayWithObjects:invertFilter,nil];
        
        // commented out: the layer controls for the other control boxes in the synced playback scrubber
        //self.layer.backgroundColor = [[NSColor colorWithCalibratedRed:1.0 green:1.0 blue:1.0 alpha:0.07] CGColor];
        //self.layer.borderColor = [[NSColor colorWithCalibratedRed:1.0 green:1.0 blue:1.0 alpha:0.15] CGColor];
        //self.layer.borderWidth = 1.0f;
        //[self.layer setCornerRadius:5.0f];
    }
    return self;
}

@end
