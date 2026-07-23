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

- (void)mouseDown:(NSEvent *)event
{
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
