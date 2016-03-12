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


#import "EventsPointsController.h"


@implementation EventsPointsController

- (void) awakeFromNib
{
	[self setSortDescriptors:[NSArray arrayWithObject:[[NSSortDescriptor alloc] initWithKey:@"index" ascending:YES]]];
	[super awakeFromNib];
}

- (NSArray *)arrangeObjects:(NSArray *)objects		// overriden to do manual filtering (too fancy for a predicate) of what's shown in the event's points table, based on the pulldown menu above it
{
	NSArray *filteredPoints = [NSArray array];
	CMTime now = [document currentMasterTime];
	if ([[[framesSelectButton selectedItem] title] isEqualToString:@"Currently Visible"]) {				// Show all points visible during the currentFrame, even if they're fading out
		for (VSPoint *point in objects) {
			CMTime startTime = [UtilityFunctions CMTimeFromString:point.timecode];
			CMTime solidDuration = CMTimeMakeWithSeconds([point.trackedEvent.type.duration doubleValue], [[document.project.masterClip timeScale] longValue]);
			CMTime fadingDuration = CMTimeMakeWithSeconds([point.trackedEvent.type.fadeTime doubleValue], [[document.project.masterClip timeScale] longValue]);
			CMTime totalDuration = CMTimeAdd(solidDuration,fadingDuration);
			CMTimeRange totalTimeRange = CMTimeRangeMake(startTime,totalDuration);
			if (CMTimeRangeContainsTime(totalTimeRange,now)) filteredPoints = [filteredPoints arrayByAddingObject:point];
		}
	} else if ([[[framesSelectButton selectedItem] title] isEqualToString:@"Current Frame Only"]) {		// Show only points whose timecode is exactly the current frame
		for (VSPoint *point in objects) {
            CMTime pointsTime = [UtilityFunctions CMTimeFromString:point.timecode];
			if ([UtilityFunctions time:now isEqualToTime:pointsTime]) filteredPoints = [filteredPoints arrayByAddingObject:point];
		}
	} else {																							// the selection is "All Points", so show all points (for the selected event of course)
		filteredPoints = objects;
	}
	return [super arrangeObjects:filteredPoints];
}

- (IBAction)changePointFiltering:(id)sender
{
	[self rearrangeObjects];
}

- (void)remove:(id)sender
{
	[super remove:sender];
	[document refreshOverlaysOfAllClips:sender];
	[[[document trackedEventsController] mainTableView] setNeedsDisplayInRect:[[[document trackedEventsController] mainTableView] rectOfColumn:4]];	// refresh the event table's # Points column

}

- (IBAction) goToPoint:(id)sender
{
	if ([[self selectedObjects] count] > 0) {
		VSPoint *point = [[self selectedObjects] objectAtIndex:0];
		CMTime pointsMasterTime = [UtilityFunctions CMTimeFromString:point.timecode];
		[document goToMasterTime:pointsMasterTime];
	}
}

@end
