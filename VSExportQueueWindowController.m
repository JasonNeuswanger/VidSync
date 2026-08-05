/*********************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2026 Jason Neuswanger
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

#import "VSExportQueueWindowController.h"
#import "VSExportQueue.h"
#import "VSClipExportTask.h"

#pragma mark VSExportQueueRowView

// One table row: clip name, status text, progress bar, and a button that is Cancel while the export is
// running and Open once it has finished.

@interface VSExportQueueRowView : NSTableCellView {
	NSTextField *__strong nameLabel;
	NSTextField *__strong statusLabel;
	NSProgressIndicator *__strong progressBar;
	NSButton *__strong cancelButton;
	NSButton *__strong openButton;
	NSButton *__strong revealButton;
}
@property (weak) VSClipExportTask *task;
@property (weak) VSExportQueue *queue;
- (void) refreshFromTask;
@end

@implementation VSExportQueueRowView

- (instancetype) initWithFrame:(NSRect)frameRect
{
	self = [super initWithFrame:frameRect];
	if (self) {
		float width = frameRect.size.width;

		nameLabel = [NSTextField labelWithString:@""];
		[nameLabel setFont:[NSFont boldSystemFontOfSize:12.0]];
		[nameLabel setLineBreakMode:NSLineBreakByTruncatingTail];
		[nameLabel setFrame:NSMakeRect(12,34,width-190,17)];
		[nameLabel setAutoresizingMask:NSViewWidthSizable|NSViewMinYMargin];
		[self addSubview:nameLabel];

		statusLabel = [NSTextField labelWithString:@""];
		[statusLabel setFont:[NSFont systemFontOfSize:11.0]];
		[statusLabel setTextColor:[NSColor secondaryLabelColor]];
		[statusLabel setAlignment:NSTextAlignmentRight];
		[statusLabel setLineBreakMode:NSLineBreakByTruncatingTail];
		[statusLabel setFrame:NSMakeRect(width-172,34,160,15)];
		[statusLabel setAutoresizingMask:NSViewMinXMargin|NSViewMinYMargin];
		[self addSubview:statusLabel];

		progressBar = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(12,12,width-176,16)];	// leaves room for two buttons on finished rows
		[progressBar setStyle:NSProgressIndicatorStyleBar];
		[progressBar setIndeterminate:NO];
		[progressBar setMinValue:0.0];
		[progressBar setMaxValue:1.0];
		[progressBar setAutoresizingMask:NSViewWidthSizable|NSViewMaxYMargin];
		[self addSubview:progressBar];

		cancelButton = [NSButton buttonWithTitle:@"Cancel" target:self action:@selector(cancelPressed:)];
		[cancelButton setBezelStyle:NSBezelStyleRounded];
		[cancelButton setControlSize:NSControlSizeSmall];
		[cancelButton setFont:[NSFont systemFontOfSize:11.0]];
		[cancelButton setFrame:NSMakeRect(width-84,8,72,24)];
		[cancelButton setAutoresizingMask:NSViewMinXMargin|NSViewMaxYMargin];
		[self addSubview:cancelButton];

		// Shares the cancel button's place, which is free by the time it appears: a task is either still going, and
		// can be cancelled, or it has finished, and can be opened. Each row opens its own file, because the tasks in
		// a queue need not have been written to the same folder.
		openButton = [NSButton buttonWithTitle:@"Open" target:self action:@selector(openPressed:)];
		[openButton setBezelStyle:NSBezelStyleRounded];
		[openButton setControlSize:NSControlSizeSmall];
		[openButton setFont:[NSFont systemFontOfSize:11.0]];
		[openButton setFrame:NSMakeRect(width-84,8,72,24)];
		[openButton setAutoresizingMask:NSViewMinXMargin|NSViewMaxYMargin];
		[openButton setToolTip:@"Open this video in whichever application the system uses for its file type."];
		[self addSubview:openButton];

		revealButton = [NSButton buttonWithTitle:@"Show File" target:self action:@selector(revealPressed:)];
		[revealButton setBezelStyle:NSBezelStyleRounded];
		[revealButton setControlSize:NSControlSizeSmall];
		[revealButton setFont:[NSFont systemFontOfSize:11.0]];
		[revealButton setFrame:NSMakeRect(width-160,8,72,24)];
		[revealButton setAutoresizingMask:NSViewMinXMargin|NSViewMaxYMargin];
		[revealButton setToolTip:@"Reveal this video in the Finder."];
		[self addSubview:revealButton];
	}
	return self;
}

- (void) revealPressed:(id)sender
{
	NSString *path = self.task.outputPath;
	if ([path length] == 0) return;
	if (![[NSWorkspace sharedWorkspace] selectFile:path inFileViewerRootedAtPath:@""]) {
		[UtilityFunctions InformUser:[NSString stringWithFormat:@"Nothing exists at %@ any more. It was probably moved or deleted after it was exported.",path] withTitle:@"That video is no longer there"];
	}
}

- (void) cancelPressed:(id)sender
{
	if (self.task != nil) [self.queue cancelTask:self.task];
}

- (void) openPressed:(id)sender
{
	NSString *path = self.task.outputPath;
	if ([path length] == 0) return;
	// Checked here rather than when the button is drawn, because a file exported minutes ago can be moved or deleted
	// at any time and the row has no way to hear about it. Saying so is more use than a button that quietly does
	// nothing.
	if (![[NSFileManager defaultManager] fileExistsAtPath:path]) {
		NSAlert *alert = [[NSAlert alloc] init];
		[alert setMessageText:@"That video is no longer there."];
		[alert setInformativeText:[NSString stringWithFormat:@"Nothing exists at %@ any more. It was probably moved or deleted after it was exported.",path]];
		[alert runModal];
		return;
	}
	[[NSWorkspace sharedWorkspace] openURL:[NSURL fileURLWithPath:path]];
}

- (void) refreshFromTask
{
	VSClipExportTask *task = self.task;
	if (task == nil) return;
	NSString *fileName = [task.outputPath lastPathComponent];
	[nameLabel setStringValue:(task.displayName != nil) ? [NSString stringWithFormat:@"%@ — %@",task.displayName,fileName] : (fileName ?: @"")];
	[statusLabel setStringValue:task.statusMessage ?: [task localizedStatusDescription]];
	[progressBar setDoubleValue:task.progress];
	[cancelButton setHidden:![task isActive]];
	// Only a task that finished has a file to open. A cancelled or failed one may have left a partial file behind,
	// which is not something to offer to play.
	[openButton setHidden:(task.status != VSClipExportTaskStatusFinished)];
	[revealButton setHidden:(task.status != VSClipExportTaskStatusFinished)];
}

@end

#pragma mark
#pragma mark VSExportQueueWindowController

@interface VSExportQueueWindowController () {
	VSExportQueue *__weak queue;
	NSTableView *__strong tableView;
	NSTimer *__strong progressRefreshTimer;
	NSButton *__strong clearButton;
}
@end

@implementation VSExportQueueWindowController

- (instancetype) initWithQueue:(VSExportQueue *)inQueue
{
	// An ordinary window rather than a utility panel. A utility panel floats above every other window in the
	// application and cannot be miniaturized, so an export running in the background sat on top of the work it was
	// meant to leave alone. This one layers and miniaturizes like any other window; the exports are unaffected by
	// what happens to it.
	NSRect contentRect = NSMakeRect(0,0,520,300);
	NSWindow *window = [[NSWindow alloc] initWithContentRect:contentRect
												   styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable|NSWindowStyleMaskResizable
													 backing:NSBackingStoreBuffered
													   defer:YES];
	[window setTitle:@"Video Export Queue"];
	[window setMinSize:NSMakeSize(380,160)];
	[window setReleasedWhenClosed:NO];

	self = [super initWithWindow:window];
	if (self) {
		queue = inQueue;

		NSView *contentView = [window contentView];

		clearButton = [NSButton buttonWithTitle:@"Clear Finished" target:self action:@selector(clearFinishedPressed:)];
		[clearButton setBezelStyle:NSBezelStyleRounded];
		[clearButton setControlSize:NSControlSizeSmall];
		[clearButton setFont:[NSFont systemFontOfSize:11.0]];
		[clearButton sizeToFit];
		NSRect clearFrame = [clearButton frame];
		clearFrame.origin = NSMakePoint(contentRect.size.width-clearFrame.size.width-12,10);
		[clearButton setFrame:clearFrame];
		[clearButton setAutoresizingMask:NSViewMinXMargin|NSViewMaxYMargin];
		[contentView addSubview:clearButton];

		float tableTop = 40;	// space below for the clear button
		NSScrollView *scrollView = [[NSScrollView alloc] initWithFrame:NSMakeRect(0,tableTop,contentRect.size.width,contentRect.size.height-tableTop)];
		[scrollView setHasVerticalScroller:YES];
		[scrollView setAutoresizingMask:NSViewWidthSizable|NSViewHeightSizable];
		[scrollView setBorderType:NSNoBorder];

		tableView = [[NSTableView alloc] initWithFrame:[scrollView bounds]];
		NSTableColumn *column = [[NSTableColumn alloc] initWithIdentifier:@"export"];
		[column setResizingMask:NSTableColumnAutoresizingMask];
		[column setWidth:[scrollView bounds].size.width];
		[tableView addTableColumn:column];
		[tableView setHeaderView:nil];
		[tableView setRowHeight:56.0];
		[tableView setAllowsEmptySelection:YES];
		[tableView setSelectionHighlightStyle:NSTableViewSelectionHighlightStyleNone];
		[tableView setColumnAutoresizingStyle:NSTableViewUniformColumnAutoresizingStyle];
		[tableView setDataSource:self];
		[tableView setDelegate:self];

		[scrollView setDocumentView:tableView];
		[tableView sizeLastColumnToFit];
		[contentView addSubview:scrollView];
	}
	return self;
}

- (void) showWindow:(id)sender
{
	// Ordered front rather than made key, which is what the inherited implementation does. Queuing a capture should
	// put the window where the user can see it without taking the keyboard away from whatever they were doing; they
	// can click it if they want it focused.
	[[self window] orderFront:sender];
}

- (void) clearFinishedPressed:(id)sender
{
	[queue clearInactiveTasks];
}

- (void) noteTasksChanged
{
	[tableView reloadData];
	VSExportQueue *strongQueue = queue;
	BOOL active = [strongQueue hasActiveTasks];
	if (active && progressRefreshTimer == nil) {
		progressRefreshTimer = [NSTimer scheduledTimerWithTimeInterval:0.1 target:self selector:@selector(refreshProgress) userInfo:nil repeats:YES];
	} else if (!active && progressRefreshTimer != nil) {
		[progressRefreshTimer invalidate];
		progressRefreshTimer = nil;
		[self refreshProgress];		// one last pass so final states display correctly
	}
}

- (void) refreshProgress
{
	// Update the visible rows in place rather than reloading, so buttons don't flicker under the mouse.
	for (NSInteger row = 0; row < [tableView numberOfRows]; row++) {
		VSExportQueueRowView *rowView = [tableView viewAtColumn:0 row:row makeIfNecessary:NO];
		if ([rowView isKindOfClass:[VSExportQueueRowView class]]) [rowView refreshFromTask];
	}
}

#pragma mark NSTableViewDataSource / NSTableViewDelegate

- (NSInteger) numberOfRowsInTableView:(NSTableView *)aTableView
{
	VSExportQueue *strongQueue = queue;
	return [strongQueue.tasks count];
}

- (NSView *) tableView:(NSTableView *)aTableView viewForTableColumn:(NSTableColumn *)tableColumn row:(NSInteger)row
{
	VSExportQueue *strongQueue = queue;
	if (row < 0 || row >= (NSInteger)[strongQueue.tasks count]) return nil;
	VSExportQueueRowView *rowView = [aTableView makeViewWithIdentifier:@"VSExportQueueRow" owner:self];
	if (rowView == nil) {
		rowView = [[VSExportQueueRowView alloc] initWithFrame:NSMakeRect(0,0,[aTableView bounds].size.width,56)];
		[rowView setIdentifier:@"VSExportQueueRow"];
	}
	rowView.queue = strongQueue;
	rowView.task = [strongQueue.tasks objectAtIndex:row];
	[rowView refreshFromTask];
	return rowView;
}

@end
