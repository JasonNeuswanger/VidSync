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


#import "PortraitBrowserCell.h"

@implementation PortraitBrowserCell

- (void)loadView
{
    NSView *containerView = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 180, 130)];
    containerView.wantsLayer = YES;

    NSImageView *imgView = [[NSImageView alloc] initWithFrame:NSMakeRect(0, 18, 180, 112)];
    imgView.imageScaling = NSImageScaleProportionallyUpOrDown;
    imgView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    imgView.editable = NO;
    [containerView addSubview:imgView];
    self.imageView = imgView;

    NSTextField *label = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 180, 16)];
    label.editable = NO;
    label.bordered = NO;
    label.backgroundColor = [NSColor clearColor];
    label.textColor = [NSColor labelColor];
    label.font = [NSFont systemFontOfSize:9.0];
    label.alignment = NSTextAlignmentCenter;
    label.lineBreakMode = NSLineBreakByTruncatingMiddle;
    label.autoresizingMask = NSViewWidthSizable;
    [containerView addSubview:label];
    self.textField = label;

    self.view = containerView;
}

- (void)setRepresentedObject:(id)representedObject
{
    [super setRepresentedObject:representedObject];
    VSTrackedObjectPortrait *portrait = (VSTrackedObjectPortrait *)representedObject;
    if (portrait != nil) {
        self.imageView.image = [portrait image];
        self.textField.stringValue = portrait.timecode ?: @"";
    } else {
        self.imageView.image = nil;
        self.textField.stringValue = @"";
    }
}

@end
