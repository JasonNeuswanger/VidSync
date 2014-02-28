//
//  EventsPointsController.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/20/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

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
