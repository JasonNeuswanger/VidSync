/*********************************************************************************                                                                       
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2021 Jason Neuswanger
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


#import "VideoOverlayWindow.h"
#import "VideoWindowController.h"


@implementation VideoOverlayWindow

- (BOOL)canBecomeKeyWindow
{
	return YES;
}

- (NSUndoManager *)windowWillReturnUndoManager:(NSWindow *)window
{
    // This window is made key whenever the user clicks in the overlay, and it's where nearly all
    // editing happens. Without this, AppKit hands it a private empty undo manager of its own and
    // Edit > Undo is permanently greyed out for measurement, calibration and annotation work.
    // Note that AppKit only asks once and never asks again after a window has made its own manager,
    // so the delegate has to be in place before the window is first shown.
    return [[self.videoWindowController document] undoManager];
}

- (NSUndoManager *)undoManager
{
    // Belt and braces alongside the delegate method above. AppKit asks the delegate only once and
    // caches the answer forever, so if anything ever requested this window's undo manager before the
    // window controller had been attached to its document, the delegate route would be dead for good.
    // Answering here can't get stuck that way.
    NSUndoManager *documentUndoManager = [[self.videoWindowController document] undoManager];
    return (documentUndoManager != nil) ? documentUndoManager : [super undoManager];
}

- (BOOL)validateUserInterfaceItem:(id<NSValidatedUserInterfaceItem>)item
{
    // Borderless windows have no close button, so NSWindow's default validation
    // returns NO for performClose:. Override to keep File > Close enabled.
    if (item.action == @selector(performClose:)) return YES;
    return [super validateUserInterfaceItem:item];
}

- (IBAction)performClose:(id)sender
{
    // File > Close should close the document, not just this video window. This has to go through
    // videoWindowController rather than self.windowController, which is always nil here because
    // nothing ever assigns a window controller to this programmatically created child window.
    NSDocument *doc = (NSDocument *)[self.videoWindowController document];
    for (NSWindowController *wc in doc.windowControllers) {
        if (wc.shouldCloseDocument) {
            [wc.window performClose:sender];
            return;
        }
    }
}

@end
