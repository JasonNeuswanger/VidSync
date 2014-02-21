//
//  PortraitsArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/19/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "PortraitsArrayController.h"

@implementation PortraitsArrayController

- (void) removeObjectAtArrangedObjectIndex:(NSUInteger)index    // I had to override the superclass's version of this function because for some reason it didn't remove objects from the context
{
    [[self managedObjectContext] deleteObject:[[self arrangedObjects] objectAtIndex:index]];
    [[self managedObjectContext] processPendingChanges];
    [self refreshImageBrowserView];
}

- (void) refreshImageBrowserView
{
    [portraitBrowserView reloadData];
    [otherPortraitBrowserView reloadData];
}

#pragma mark
#pragma mark Methods to conform to the IKImageBrowserDataSource informal protocol

- (NSUInteger) numberOfItemsInImageBrowser:(IKImageBrowserView *)view
{
    return [[self arrangedObjects] count];
}

- (id) imageBrowser:(IKImageBrowserView *) view itemAtIndex:(NSUInteger)index
{
    return [[self arrangedObjects] objectAtIndex:index];
}

- (void) imageBrowser:(IKImageBrowserView *) view removeItemsAtIndexes:(NSIndexSet *)indexes
{
    [self removeObjectsAtArrangedObjectIndexes:indexes];
}

@end
