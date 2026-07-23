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
        [self addObserver:self forKeyPath:@"arrangedObjects" options:0 context:NULL];
    }
    if (otherPortraitBrowserView != nil) {
        if (otherPortraitBrowserView.collectionViewLayout == nil) {
            otherPortraitBrowserView.collectionViewLayout = makeDefaultPortraitLayout();
        }
        [otherPortraitBrowserView registerClass:[PortraitBrowserCell class] forItemWithIdentifier:@"PortraitBrowserCell"];
    }
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
    if ([keyPath isEqualToString:@"arrangedObjects"]) {
        [self refreshCollectionView];
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
	[portraitBrowserView reloadData];
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

- (void) dealloc
{
    @try {
        [self removeObserver:self forKeyPath:@"arrangedObjects"];
    } @catch (id exception) {}
}

@end
