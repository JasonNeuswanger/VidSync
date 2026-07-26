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

// An NSTabView whose selected tab can be bound to a user default.
//
// AppKit exposes no binding for which tab of an NSTabView is selected; only
// NSTabViewController has a bindable selectedTabViewItemIndex, and that is a view controller
// rather than something that can be dropped into a panel in an existing nib. The alternative
// is wiring a delegate through to a controller, which spreads the state of one popup-like
// control across two files. Exposing a KVO-compliant identifier keeps it in one place and
// lets the tab be bound in Interface Builder like any other control.

#import <Cocoa/Cocoa.h>

@interface VSBindableTabView : NSTabView

// The identifier of the selected tab view item. Bindable, and kept in step with the tab the
// user clicks. Setting an identifier that no tab has leaves the selection alone.
@property (nonatomic, copy) NSString *selectedIdentifier;

@end
