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


#import "ObjectsPortraitsArrayController.h"

@implementation ObjectsPortraitsArrayController

- (void) awakeFromNib {
    
//    [portraitBrowserView setIntercellSpacing:NSMakeSize(2.0f,2.0f)];
//    [portraitBrowserView setCellSize:NSMakeSize(200.0f,125.0f)];
    
}

- (void) addImage:(NSImage *)image ofObject:(VSTrackedObject *)object fromSourceClip:(VSVideoClip *)sourceVideoClip inRect:(NSRect)rect withTimecode:(NSString *)timecode {
    VSTrackedObjectPortrait *newPortrait = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObjectPortrait" inManagedObjectContext:[self managedObjectContext]];
    newPortrait.timecode = timecode;
    newPortrait.sourceVideoClip = sourceVideoClip;
    newPortrait.trackedObject = object;
    newPortrait.frameString = NSStringFromRect(rect);
    [newPortrait setImage:image];
    [self addObject:newPortrait];
    [[self managedObjectContext] processPendingChanges];
    [self refreshImageBrowserView];
}

@end
