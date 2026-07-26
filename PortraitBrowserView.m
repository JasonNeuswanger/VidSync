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


#import "PortraitBrowserView.h"

@implementation PortraitBrowserView

- (void) awakeFromNib
{
    [super awakeFromNib];

    // NSCollectionView.selectable defaults to NO, and these browsers are archived in the
    // XIB as plain <customView> elements with only a custom class, so none of NSCollectionView's
    // Interface Builder settings (including "Selectable") are stored in the nib. Without this,
    // clicking an item never updates selectionIndexPaths, so NSCollectionViewItem's setSelected:
    // and the didSelectItemsAtIndexPaths: delegate callbacks never fire and no selection is
    // ever visible. Multiple selection is enabled because the Delete handler in
    // portraitBrowserViewDeleteSelectedItems: is written to remove a whole set of portraits.
    self.selectable = YES;
    self.allowsMultipleSelection = YES;
    self.allowsEmptySelection = YES;

    if (self.collectionViewLayout == nil) {
        NSCollectionViewFlowLayout *layout = [[NSCollectionViewFlowLayout alloc] init];
        layout.itemSize = NSMakeSize(180, 130);
        layout.minimumInteritemSpacing = 4.0;
        layout.minimumLineSpacing = 4.0;
        layout.sectionInset = NSEdgeInsetsMake(4, 4, 4, 4);
        self.collectionViewLayout = layout;
    }
    if (self.enclosingScrollView && self.enclosingScrollView.documentView != self) {
        self.enclosingScrollView.documentView = self;
    }
}

- (void)keyDown:(NSEvent *)event
{
    // Delete (backspace=51) or Forward Delete (117) removes selected portraits
    if ((event.keyCode == 51 || event.keyCode == 117) && self.selectionIndexPaths.count > 0) {
        if ([self.delegate respondsToSelector:@selector(portraitBrowserViewDeleteSelectedItems:)]) {
            [(id<PortraitBrowserViewDelegate>)self.delegate portraitBrowserViewDeleteSelectedItems:self];
        }
    } else {
        [super keyDown:event];
    }
}

- (BOOL)acceptsFirstResponder
{
    return YES;
}

- (void)mouseDown:(NSEvent *)event
{
    // Claim first responder before super processes selection, so that
    // (a) setSelected:/didSelectItemsAtIndexPaths: fire while we ARE the key view,
    // and (b) subsequent keyDown: events (e.g. Delete) reach this view, not
    // whatever editable field held focus before the click.
    [self.window makeFirstResponder:self];

    if (event.clickCount == 2) {
        NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
        NSIndexPath *indexPath = [self indexPathForItemAtPoint:point];
        if (indexPath) {
            NSCollectionViewItem *item = [self itemAtIndexPath:indexPath];
            if (item && [self.delegate respondsToSelector:@selector(portraitBrowserView:didDoubleClickPortrait:)]) {
                [(id<PortraitBrowserViewDelegate>)self.delegate portraitBrowserView:self
                                                              didDoubleClickPortrait:(VSTrackedObjectPortrait *)item.representedObject];
            }
        }
    }
    [super mouseDown:event];
}

- (void)setZoomFactor:(CGFloat)zoom
{
    NSCollectionViewFlowLayout *layout = (NSCollectionViewFlowLayout *)self.collectionViewLayout;
    if ([layout isKindOfClass:[NSCollectionViewFlowLayout class]]) {
        layout.itemSize = NSMakeSize(180.0 * zoom, 130.0 * zoom);
        [self reloadData];
    }
}

@end
