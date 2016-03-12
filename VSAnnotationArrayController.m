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


#import "VSAnnotationArrayController.h"


@implementation VSAnnotationArrayController

- (void) awakeFromNib
{
	NSSortDescriptor *timecodeDescriptor = [[NSSortDescriptor alloc] initWithKey:@"startTimecode" ascending:YES];
	NSSortDescriptor *contentsDescriptor = [[NSSortDescriptor alloc] initWithKey:@"notes" ascending:YES];
	[self setSortDescriptors:[NSArray arrayWithObjects:timecodeDescriptor,contentsDescriptor,nil]];
	[super awakeFromNib];
}

- (IBAction) goToAnnotation:(id)sender
{
	if ([[self selectedObjects] count] > 0) {
		VSAnnotation *annotation = [[self selectedObjects] objectAtIndex:0];
		CMTime pointsMasterTime = [UtilityFunctions CMTimeFromString:annotation.startTimecode];
		[document goToMasterTime:pointsMasterTime];
	}	
}

- (IBAction) mirrorSelectedAnnotation:(id)sender
{
    if ([[self selectedObjects] count] > 0) {
        VSAnnotation *selectedAnnotation = [[self selectedObjects] objectAtIndex:0];
        for (VSVideoClip *clip in selectedAnnotation.videoClip.project.videoClips) {
            if (![clip isEqualTo:selectedAnnotation.videoClip]) {
                VSAnnotation *newAnnotation = (VSAnnotation *) [UtilityFunctions Clone:selectedAnnotation inContext:[self managedObjectContext] deep:NO];
                newAnnotation.videoClip = clip;
            }
        }
	}
    [[self managedObjectContext] processPendingChanges];
	[document refreshOverlaysOfAllClips:self];
}

@end
