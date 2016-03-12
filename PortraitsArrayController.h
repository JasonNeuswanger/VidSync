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


#import <Cocoa/Cocoa.h>

@class PortraitBrowserView;

// This class primarily implements methods for viewing a collection of portraits (including conforming to the informal IKImageBrowserDataSource protocol).
// The subclass ObjectsPortraitsArrayController manages the addition and removal of objects from a single array controller.

@interface PortraitsArrayController : NSArrayController {

    IBOutlet PortraitBrowserView *__weak portraitBrowserView;
    
    IBOutlet PortraitBrowserView *__weak otherPortraitBrowserView; // Hooked up to reference the object's portraits from all portraits, and vice versa, for convenient updating when changes are made
    
}

- (void) refreshImageBrowserView;

- (NSUInteger) numberOfItemsInImageBrowser:(IKImageBrowserView *)view;

- (id) imageBrowser:(IKImageBrowserView *) view itemAtIndex:(NSUInteger)index;

- (void) imageBrowser:(IKImageBrowserView *) view removeItemsAtIndexes:(NSIndexSet *)indexes;

@end
