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


#import "PortraitsArrayController.h"
#import "PortraitBrowserView.h"
#import "VSTrackedObjectPortrait.h"

@implementation PortraitsArrayController

static NSCollectionViewFlowLayout *makeDefaultPortraitLayout(void) {
    NSCollectionViewFlowLayout *layout = [[NSCollectionViewFlowLayout alloc] init];
    layout.itemSize = NSMakeSize(180, 130);
    layout.minimumInteritemSpacing = 4.0;
    layout.minimumLineSpacing = 4.0;
    layout.sectionInset = NSEdgeInsetsMake(4, 4, 4, 4);
    return layout;
}

- (void) awakeFromNib
{
    if (portraitBrowserView != nil) {
        if (portraitBrowserView.collectionViewLayout == nil) {
            portraitBrowserView.collectionViewLayout = makeDefaultPortraitLayout();
        }
        [portraitBrowserView registerClass:[PortraitBrowserCell class] forItemWithIdentifier:@"PortraitBrowserCell"];
        portraitBrowserView.dataSource = self;
        portraitBrowserView.delegate = self;
        // Disable automatic re-sort/re-filter on every Core Data context notification.
        // With this off, arrangedObjects KVO only fires when the portrait content actually
        // changes (different selected object, portrait added/deleted) — NOT on every
        // timer-triggered write to unrelated entities like VSVideoClip. This eliminates
        // the main-thread stall that caused beachballing after close/reopen.
        self.automaticallyRearrangesObjects = NO;
        [self addObserver:self forKeyPath:@"arrangedObjects" options:0 context:NULL];
        if (zoomDefaultsKey != nil) {
            CGFloat zoom = [[NSUserDefaults standardUserDefaults] floatForKey:zoomDefaultsKey];
            if (zoom > 0.0) [portraitBrowserView setZoomFactor:zoom];
            [[NSUserDefaults standardUserDefaults] addObserver:self forKeyPath:zoomDefaultsKey options:NSKeyValueObservingOptionNew context:NULL];
        }
    }
    if (otherPortraitBrowserView != nil) {
        if (otherPortraitBrowserView.collectionViewLayout == nil) {
            otherPortraitBrowserView.collectionViewLayout = makeDefaultPortraitLayout();
        }
        [otherPortraitBrowserView registerClass:[PortraitBrowserCell class] forItemWithIdentifier:@"PortraitBrowserCell"];
        // Do NOT set dataSource/delegate here: otherPortraitBrowserView is owned by the
        // OTHER controller (its portraitBrowserView), which sets those in its own awakeFromNib.
        // Setting them here would hijack the other controller's view.
    }
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
    if ([keyPath isEqualToString:@"arrangedObjects"]) {
        [self refreshCollectionView];
    } else if (zoomDefaultsKey != nil && [keyPath isEqualToString:zoomDefaultsKey]) {
        CGFloat zoom = [[NSUserDefaults standardUserDefaults] floatForKey:zoomDefaultsKey];
        if (zoom > 0.0) [portraitBrowserView setZoomFactor:zoom];
    } else {
        [super observeValueForKeyPath:keyPath ofObject:object change:change context:context];
    }
}

- (void) removeObjectAtArrangedObjectIndex:(NSUInteger)index    // I had to override the superclass's version of this function because for some reason it didn't remove objects from the context
{
	[[self managedObjectContext] deleteObject:[[self arrangedObjects] objectAtIndex:index]];
	[[self managedObjectContext] processPendingChanges];
	[self refreshCollectionView];
}

- (void) refreshCollectionView
{
    // Save selection before reload; reloadData clears selectionIndexPaths.
    NSSet<NSIndexPath *> *previousSelection = [portraitBrowserView selectionIndexPaths];
    [portraitBrowserView reloadData];
    if (previousSelection.count > 0) {
        NSInteger count = (NSInteger)[[self arrangedObjects] count];
        NSMutableSet<NSIndexPath *> *validPaths = [NSMutableSet set];
        for (NSIndexPath *ip in previousSelection) {
            if ((NSInteger)ip.item < count) [validPaths addObject:ip];
        }
        if (validPaths.count > 0) [portraitBrowserView setSelectionIndexPaths:validPaths];
    }
    [otherPortraitBrowserView reloadData];
}


#pragma mark
#pragma mark NSCollectionViewDataSource protocol methods

- (NSInteger)numberOfSectionsInCollectionView:(NSCollectionView *)collectionView {
	return 1;
}

- (NSInteger)collectionView:(NSCollectionView *)collectionView numberOfItemsInSection:(NSInteger)section
{
	return (section == 0) ? (NSInteger)[[self arrangedObjects] count] : 0;
}

- (NSCollectionViewItem *)collectionView:(NSCollectionView *)collectionView itemForRepresentedObjectAtIndexPath:(NSIndexPath *)indexPath
{
    PortraitBrowserCell *item = (PortraitBrowserCell *)[collectionView makeItemWithIdentifier:@"PortraitBrowserCell" forIndexPath:indexPath];
    item.representedObject = [[self arrangedObjects] objectAtIndex:[indexPath item]];
    return item;
}

// PortraitBrowserCell draws its own selection border from its setSelected: override, which
// covers both interactive and programmatic selection, so no didSelectItemsAtIndexPaths: /
// didDeselectItemsAtIndexPaths: handling is needed here.

#pragma mark PortraitBrowserViewDelegate — forward action events to the document

- (void)portraitBrowserView:(NSCollectionView *)browserView didDoubleClickPortrait:(VSTrackedObjectPortrait *)portrait
{
    [self.portraitActionDelegate portraitBrowserView:browserView didDoubleClickPortrait:portrait];
}

- (void)portraitBrowserViewDeleteSelectedItems:(NSCollectionView *)browserView
{
    [self.portraitActionDelegate portraitBrowserViewDeleteSelectedItems:browserView];
}

- (void) dealloc
{
    @try {
        [self removeObserver:self forKeyPath:@"arrangedObjects"];
    } @catch (id exception) {}
    if (zoomDefaultsKey != nil) {
        @try {
            [[NSUserDefaults standardUserDefaults] removeObserver:self forKeyPath:zoomDefaultsKey];
        } @catch (id exception) {}
    }
}

@end
