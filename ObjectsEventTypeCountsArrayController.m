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

#import "ObjectsEventTypeCountsArrayController.h"

@implementation ObjectsEventTypeCountsArrayController

- (void) awakeFromNib
{
    NSSortDescriptor *typeDescriptor = [[NSSortDescriptor alloc] initWithKey:@"type.name" ascending:YES];
    [self setSortDescriptors:[NSArray arrayWithObjects:typeDescriptor,nil]];
    [super awakeFromNib];
}

- (NSArray *)arrangeObjects:(NSArray *)objects
{
    // This function creates a dictionary of trackedEvents, just one of each type, and uses that one event's
    // countOfType property to store the count of all events of that type for reading by the event count tableview.
    NSMutableDictionary *typeCounts = [NSMutableDictionary dictionary];
    for (VSTrackedEvent *trackedEvent in objects) {
        if ([[typeCounts allKeys] containsObject:trackedEvent.type.name]) {
            VSTrackedEvent *countedEvent = [typeCounts objectForKey:trackedEvent.type.name];
            countedEvent.countOfType += 1;
        } else if (trackedEvent.type.name != nil) { // this nonnil condition excludes events just created without any type given yet
            trackedEvent.countOfType = 1;
            [typeCounts setObject:trackedEvent forKey:trackedEvent.type.name];
        } else {
            // This arrangeObjects function is called by a notification the instant a new trackedEvent is created in the managedObjectContext.
            // That happens before it's assigned a name or a type, which generates an error here when we go to add it to a count above. Therefore
            // we only do that step when it's not nil. If it's a newly created event with a nil type, the line below says to wait 0.05 seconds
            // (after which the event will have a type) and then rearrange everything, properly incorporating it into the count.
            [self performSelector:@selector(rearrangeObjects) withObject:self afterDelay:0.05];
        }
    }
    return [super arrangeObjects:[typeCounts allValues]];
}



@end
