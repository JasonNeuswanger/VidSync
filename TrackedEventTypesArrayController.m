//
//  TrackedEventTypesArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/27/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "TrackedEventTypesArrayController.h"

@implementation TrackedEventTypesArrayController

- (void)remove:(id)sender
{
    VSTrackedEventType *typeToRemove = [[self selectedObjects] firstObject];
    NSMutableString *errorMessage = [NSMutableString new];
    if ([typeToRemove.trackedEvents count] > 0) {
        int numItemsBlockingDeletion = 0;
        [errorMessage appendFormat:@"You cannot delete an event type while there are still events associated with that type. Please delete the following events or change their types:\n\n"];
        for (VSTrackedEvent *trackedEvent in typeToRemove.trackedEvents) {
            numItemsBlockingDeletion += 1;
            if (numItemsBlockingDeletion <= 10)[errorMessage appendFormat:@"%@ event with index %@ (associated with object with index %lu).\n",typeToRemove.name,trackedEvent.index,(unsigned long)[(VSTrackedObject *)[trackedEvent.trackedObjects anyObject] index]];
        }
        if (numItemsBlockingDeletion > 10) [errorMessage appendFormat:@"...more items not shown..."];
        NSAlert *cannotDeleteAlert = [NSAlert new];
        [cannotDeleteAlert setMessageText:@"Cannot delete event type yet"];
        [cannotDeleteAlert setInformativeText:errorMessage];
        [cannotDeleteAlert addButtonWithTitle:@"Ok"];
        [cannotDeleteAlert setAlertStyle:NSCriticalAlertStyle];
        [cannotDeleteAlert runModal];
    } else {
        [super remove:sender];
    }
}



@end
