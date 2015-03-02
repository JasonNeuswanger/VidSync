//
//  SyncedPlaybackPanelScrubberBackground.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/2/15.
//  Copyright (c) 2015 Jason Neuswanger. All rights reserved.
//

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
