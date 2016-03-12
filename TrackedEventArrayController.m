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


#import "TrackedEventArrayController.h"

@implementation TrackedEventArrayController

- (IBAction) add:(id)sender
{
    if ([newEventType selectedItem] == nil) {
        [UtilityFunctions InformUser:@"You can't add an Event until you have defined at least one Event Type. Use the \"Edit Object/Event Types\" button to get started."];
    } else {
        VSTrackedEvent *newEvent = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedEvent" inManagedObjectContext:[self managedObjectContext]];
        newEvent.name = [newEventName stringValue];
        newEvent.type = [[newEventType selectedItem] representedObject];
        newEvent.observer = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"currentObserverName"];
        [self addObject:newEvent];
        newEvent.index = [NSNumber numberWithInt:[VSTrackedEvent highestEventIndexInProject:document.project]+1];
        [newEventName setStringValue:@""];
        [eventAddPanel performClose:nil];
    }
}

- (void)remove:(id)sender
{
    VSTrackedEvent *eventToDelete = (VSTrackedEvent *) [[self selectedObjects] firstObject];
    if ([eventToDelete.points count] > 0) {
        NSInteger alertResult = NSRunAlertPanel(@"Are you sure?",@"Are you sure you want to delete event %@?",@"Yes",@"No",nil,eventToDelete.index);
        if (alertResult == 1) {
            [super remove:sender];
            [document refreshOverlaysOfAllClips:sender];
        }
    } else {
        [super remove:sender];
        [document refreshOverlaysOfAllClips:sender];
    }
}

- (IBAction) sortByEarliestTimecode:(id)sender
{
    [self rearrangeObjects];
    NSSortDescriptor *timeDescriptor = [[NSSortDescriptor alloc] initWithKey:@"earliestPointTimecode" ascending:YES];
    [self.mainTableView setSortDescriptors:[NSArray arrayWithObjects:timeDescriptor,nil]];
}

@end
