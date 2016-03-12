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


#import "EventsOtherObjectsArrayController.h"


@implementation EventsOtherObjectsArrayController

- (NSArray *)arrangeObjects:(NSArray *)objects {
	if ([[eventController selectedObjects] count] > 0) {
		NSMutableArray *filteredObjects = [NSMutableArray arrayWithCapacity:[objects count]];
		NSSet *eventsObjects = [[[eventController selectedObjects] objectAtIndex:0] trackedObjects];
		NSEnumerator *objectsEnumerator = [objects objectEnumerator];
		id item;
		while (item = [objectsEnumerator nextObject]) {
			if (![eventsObjects containsObject:item]) [filteredObjects addObject:item];
		}
		return [super arrangeObjects:filteredObjects];
	} else {
		return [super arrangeObjects:objects];
	}
}

- (IBAction) addSelectedObjectToEvent:(id)sender
{
	if ([[eventController selectedObjects] count] > 0 && [[self selectedObjects] count] > 0) {
		VSTrackedEvent *theEvent = [[eventController selectedObjects] objectAtIndex:0];
		VSTrackedObject *theObject = [[self selectedObjects] objectAtIndex:0];
		theEvent.trackedObjects = [theEvent.trackedObjects setByAddingObject:theObject];
		[self rearrangeObjects];
	}
}

- (IBAction) removeSelectedObjectFromEvent:(id)sender
{
	if ([[eventController selectedObjects] count] > 0 && [[eventsObjectsController selectedObjects] count] > 0) {
		VSTrackedObject *objectToRemove = [[eventsObjectsController selectedObjects] objectAtIndex:0];
		VSTrackedEvent *theEvent = [[eventController selectedObjects] objectAtIndex:0];
		NSMutableSet *trackedObjects = [NSMutableSet setWithSet:theEvent.trackedObjects];
		[trackedObjects removeObject:objectToRemove];
		theEvent.trackedObjects = trackedObjects;
        if ([trackedObjects count] > 0) {
            VSTrackedObject *newlySelectedObject = [trackedObjects anyObject];
            [self setSelectedObjects:@[newlySelectedObject]];
            [objectController setSelectedObjects:@[newlySelectedObject]];
            [eventController setSelectedObjects:@[theEvent]];
            
        }
        [self rearrangeObjects];
	}
}

-(void)tableViewSelectionDidChange:(NSNotification *)notification
{
	[self rearrangeObjects];
}

@end
