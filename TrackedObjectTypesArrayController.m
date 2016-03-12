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
