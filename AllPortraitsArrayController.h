//
//  AllPortraitsArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 2/20/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PortraitsArrayController.h"

@interface AllPortraitsArrayController : PortraitsArrayController {
    
}

- (NSDictionary *) imageBrowser:(IKImageBrowserView *)aBrowser groupAtIndex:(NSUInteger)index;

- (NSUInteger) numberOfGroupsInImageBrowser:(IKImageBrowserView *)aBrowser;

- (NSArray *) objectPortraitData;

@end
