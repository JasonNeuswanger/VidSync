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


#import "ObjectSynonymizeArrayController.h"


@implementation ObjectSynonymizeArrayController

- (NSArray *)arrangeObjects:(NSArray *)objects {
	if ([[mainObjectsController selectedObjects] count] > 0) {
		VSTrackedObject *mainObject = [[mainObjectsController selectedObjects] objectAtIndex:0];
		NSMutableArray *filteredObjects = [NSMutableArray arrayWithArray:objects];
		[filteredObjects removeObject:mainObject];
		if ([[[typeFilterButton selectedItem] title] isEqualToString:@"The Same Type"]) {
			NSMutableArray *objectsOfTheSameType = [NSMutableArray new];
			for (VSTrackedObject *object in filteredObjects) {
				if ([object.type isEqualTo:mainObject.type]) [objectsOfTheSameType addObject:object];
			}
			return [super arrangeObjects:objectsOfTheSameType];
			
			
		} else {	// show other objects of all types
			return [super arrangeObjects:filteredObjects];
		}
	} else {
		return [super arrangeObjects:objects];
	}
}

- (IBAction) doRearrangeObjects:(id)sender
{
	[self rearrangeObjects];
}

- (IBAction) synonymize:(id)sender;
{
    if ([UtilityFunctions ConfirmAction:@"Are you sure you want to combine these two objects into one?"]) {
        VSTrackedObject *deadSynonym = [[self selectedObjects] objectAtIndex:0];
        VSTrackedObject *survivingSynonym = [[mainObjectsController selectedObjects] objectAtIndex:0];
        if (deadSynonym.notes != nil) survivingSynonym.notes = [survivingSynonym.notes stringByAppendingString:[NSString stringWithFormat:@"\n\n%@",deadSynonym.notes]];
        for (VSTrackedEvent *event in deadSynonym.trackedEvents) event.trackedObjects = [event.trackedObjects setByAddingObject:survivingSynonym];
        [self removeObject:deadSynonym];
        [self rearrangeObjects];						
        [mainObjectsController rearrangeObjects];
        [[survivingSynonym managedObjectContext] processPendingChanges];
        [document refreshOverlaysOfAllClips:sender];
    }
}

@end
