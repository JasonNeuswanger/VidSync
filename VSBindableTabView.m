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

#import "VSBindableTabView.h"

@implementation VSBindableTabView

- (NSString *) selectedIdentifier
{
	return (NSString *)[[self selectedTabViewItem] identifier];
}

- (void) setSelectedIdentifier:(NSString *)identifier
{
	if (identifier == nil) return;
	if ([[self selectedIdentifier] isEqualToString:identifier]) return;
	if ([self indexOfTabViewItemWithIdentifier:identifier] == NSNotFound) return;
	[self selectTabViewItemWithIdentifier:identifier];
}

// Clicking a tab goes through here, so this is where the bound value has to be told the
// selection changed. Without it the binding would push values in only one direction.
- (void) selectTabViewItem:(NSTabViewItem *)tabViewItem
{
	[self willChangeValueForKey:@"selectedIdentifier"];
	[super selectTabViewItem:tabViewItem];
	[self didChangeValueForKey:@"selectedIdentifier"];
}

// KVO must not fire automatically as well, or the change notification would be sent twice
// for one selection, and once with a stale value since the property is derived.
+ (BOOL) automaticallyNotifiesObserversForKey:(NSString *)key
{
	if ([key isEqualToString:@"selectedIdentifier"]) return NO;
	return [super automaticallyNotifiesObserversForKey:key];
}

@end
