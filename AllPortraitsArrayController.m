//
//  AllPortraitsArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/20/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "AllPortraitsArrayController.h"

@implementation AllPortraitsArrayController

- (void) awakeFromNib {
    // initialization (if any) to execute before the objects are fetched
    [self setEntityName:@"VSTrackedObjectPortrait"];
    [self setSortDescriptors:@[[NSSortDescriptor sortDescriptorWithKey:@"trackedObject.index" ascending:YES]]];
    NSError *error;
    [self fetchWithRequest:nil merge:NO error:&error];
    if (error != nil) [NSApp presentError:error];
    [portraitBrowserView reloadData];
}

#pragma mark
#pragma mark IKImageBrowserDataSource informal protocol methods for grouping

- (NSUInteger) numberOfGroupsInImageBrowser:(IKImageBrowserView *) aBrowser
{
    return [[self objectPortraitData] count];
}

- (NSDictionary *) imageBrowser:(IKImageBrowserView *) aBrowser groupAtIndex:(NSUInteger) index
{
    
    NSArray *objectPortraitData = [self objectPortraitData];
    
    return @{IKImageBrowserGroupRangeKey: [[objectPortraitData objectAtIndex:index] valueForKey:@"portraitIndexRange"],
             IKImageBrowserGroupBackgroundColorKey: [NSColor redColor],
             IKImageBrowserGroupTitleKey: [[objectPortraitData objectAtIndex:index] valueForKey:@"title"],
             IKImageBrowserGroupStyleKey: [NSNumber numberWithInt:IKGroupDisclosureStyle]}; // disclosure vs bezel
}

- (NSArray *) objectPortraitData
{
    // First, to tally the counts, I create an NSDictionary with the object index as the key and its portrait count as the value
    NSMutableDictionary *portraitCountsDict = [NSMutableDictionary dictionary];
    NSUInteger currentPortraitIndex = 0;
    for (VSTrackedObjectPortrait *portrait in [self arrangedObjects]) {
        if ([[portraitCountsDict allKeys] containsObject:portrait.trackedObject.index]) {
            NSMutableDictionary *currentPortraitDict = [(NSMutableDictionary *) portraitCountsDict objectForKey:portrait.trackedObject.index];
            NSNumber *updatedGroupLength = [NSNumber numberWithInt:[[currentPortraitDict objectForKey:@"length"] intValue] + 1];
            [currentPortraitDict setObject:updatedGroupLength forKey:@"length"];
        } else {
            NSString *titleName = ([portrait.trackedObject.name isEqualToString:@""]) ? @"" : [NSString stringWithFormat:@" (%@)",portrait.trackedObject.name];
            NSMutableDictionary *newObjectDict = [NSMutableDictionary dictionaryWithDictionary:@{
                                                                                                    @"start"  : [NSNumber numberWithInt:currentPortraitIndex],
                                                                                                    @"length" : [NSNumber numberWithInt:1],
                                                                                                    @"title"  : [NSString stringWithFormat:@"Object %@%@",portrait.trackedObject.index,titleName]
                                                                                                    }];
            [portraitCountsDict setObject:newObjectDict forKey:portrait.trackedObject.index];
        }
        currentPortraitIndex += 1;
    }
    // To put the data back in order by object index, I convert the dictionary of dictionaries into an array of dictionaries
    NSMutableArray *portraitCountsArray = [NSMutableArray array];
    [portraitCountsDict enumerateKeysAndObjectsUsingBlock:^(id key, id obj, BOOL *stop) {
        NSRange indexRange = {[[obj objectForKey:@"start"] intValue], [[obj objectForKey:@"length"] intValue]};
        [portraitCountsArray addObject:@{ @"objectIndex" : key, @"portraitIndexRange" : [NSValue valueWithRange:indexRange], @"title" : [obj objectForKey:@"title"]}];
    }];
    // Then I return a sorted version of the array
    return [portraitCountsArray sortedArrayUsingDescriptors:@[[NSSortDescriptor sortDescriptorWithKey:@"objectIndex" ascending:YES]]];
}

@end
