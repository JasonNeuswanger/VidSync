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


#import "TrackedObjectArrayController.h"


@implementation TrackedObjectArrayController

- (IBAction) add:(id)sender
{
    if ([newObjectType selectedItem] == nil) {
        [UtilityFunctions InformUser:@"You can't add an Object until you have defined at least one Object Type. Use the \"Edit Object/Event Types\" button to get started."];
    } else {
        VSTrackedObject *newObj = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObject" inManagedObjectContext:[self managedObjectContext]];
        newObj.name = [newObjectName stringValue];
        newObj.type = [[newObjectType selectedItem] representedObject];
        newObj.observer = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"currentObserverName"];
        [self addObject:newObj];	// Adding the object to the project before setting its index.  Convenient, and seemingly harmless.
        newObj.index = [NSNumber numberWithInt:[VSTrackedObject highestObjectIndexInProject:newObj.project]+1];
        newObj.color = [newTypeColorWell color];
        [newObjectName setStringValue:@""];
        [objectAddPanel performClose:nil];
    }
}

- (void)remove:(id)sender
{
    VSTrackedObject *objectToDelete = (VSTrackedObject *) [[self selectedObjects] firstObject];
    if ([[objectToDelete trackedEvents] count] > 0) {
        NSInteger alertResult = NSRunAlertPanel(@"Are you sure?",@"Are you sure you want to delete object %@?",@"Yes",@"No",nil,objectToDelete.index);
        if (alertResult == 1) {
            [super remove:sender];
            [document refreshOverlaysOfAllClips:sender];
        }
    } else {
        [super remove:sender];
        [document refreshOverlaysOfAllClips:sender];
    }
}

@end
