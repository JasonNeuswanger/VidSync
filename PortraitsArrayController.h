//
//  PortraitsArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@class PortraitBrowserView;

// This class primarily implements methods for viewing a collection of portraits (including conforming to the informal IKImageBrowserDataSource protocol).
// The subclass ObjectsPortraitsArrayController manages the addition and removal of objects from a single array controller.

@interface PortraitsArrayController : NSArrayController {

    IBOutlet PortraitBrowserView *portraitBrowserView;
    
    IBOutlet PortraitBrowserView *otherPortraitBrowserView; // Hooked up to reference the object's portraits from all portraits, and vice versa, for convenient updating when changes are made
    
}

- (void) refreshImageBrowserView;

- (NSUInteger) numberOfItemsInImageBrowser:(IKImageBrowserView *)view;

- (id) imageBrowser:(IKImageBrowserView *) view itemAtIndex:(NSUInteger)index;

- (void) imageBrowser:(IKImageBrowserView *) view removeItemsAtIndexes:(NSIndexSet *)indexes;

@end
