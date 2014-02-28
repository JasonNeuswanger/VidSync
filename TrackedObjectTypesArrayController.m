//
//  TrackedObjectTypesArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 2/27/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import "TrackedObjectTypesArrayController.h"

@implementation TrackedObjectTypesArrayController

- (void)remove:(id)sender
{
    VSTrackedObjectType *typeToRemove = [[self selectedObjects] firstObject];
    NSMutableString *errorMessage = [NSMutableString new];
    if ([typeToRemove.trackedObjects count] > 0) {
        int numItemsBlockingDeletion = 0;
        [errorMessage appendFormat:@"You cannot delete an object type while there are still objects associated with that type. Please delete the following objects or change their types:\n\n"];
        for (VSTrackedObject *trackedObject in typeToRemove.trackedObjects) {
            numItemsBlockingDeletion += 1;
            if (numItemsBlockingDeletion <= 10)[errorMessage appendFormat:@"%@ object with index %@.\n",typeToRemove.name,trackedObject.index];
        }
        if (numItemsBlockingDeletion > 10) [errorMessage appendFormat:@"...more items not shown..."];
        NSAlert *cannotDeleteAlert = [NSAlert new];
        [cannotDeleteAlert setMessageText:@"Cannot delete object type yet"];
        [cannotDeleteAlert setInformativeText:errorMessage];
        [cannotDeleteAlert addButtonWithTitle:@"Ok"];
        [cannotDeleteAlert setAlertStyle:NSCriticalAlertStyle];
        [cannotDeleteAlert runModal];
    } else {
        [super remove:sender];
    }
}

@end
