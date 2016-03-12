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

- (void) dealloc
{
}

@end
