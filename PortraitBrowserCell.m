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
#import "VSTrackedObjectPortrait.h"

// Container view that draws the selection border on its own CALayer.
// CALayer renders: background → contents → sublayers → border.
// Setting borderWidth on the container's own layer therefore always appears
// on top of the image and label subviews with no z-order or separate-subview issues.
// wantsUpdateLayer guarantees the layer exists when updateLayer is called,
// unlike setting layer properties directly (where the layer may still be nil).
@interface VSPortraitContainerView : NSView
@property (nonatomic) BOOL showsSelectionBorder;
@end

@implementation VSPortraitContainerView

- (BOOL)wantsUpdateLayer { return YES; }

- (void)updateLayer
{
    if (self.showsSelectionBorder) {
        NSColor *accent = [[NSColor controlAccentColor] colorUsingColorSpace:[NSColorSpace sRGBColorSpace]];
        self.layer.borderColor = (accent ?: [NSColor systemBlueColor]).CGColor;
        self.layer.borderWidth = 3.0;
        self.layer.cornerRadius = 4.0;
    } else {
        self.layer.borderWidth = 0.0;
        self.layer.borderColor = nil;
        self.layer.cornerRadius = 0.0;
    }
}

@end

@implementation PortraitBrowserCell

- (void)loadView
{
    VSPortraitContainerView *containerView = [[VSPortraitContainerView alloc] initWithFrame:NSMakeRect(0, 0, 180, 130)];
    containerView.wantsLayer = YES;  // Required for wantsUpdateLayer to work

    // Image occupies the upper portion; label takes 28 px at the bottom (2 lines)
    NSImageView *imgView = [[NSImageView alloc] initWithFrame:NSMakeRect(0, 28, 180, 102)];
    imgView.imageScaling = NSImageScaleProportionallyUpOrDown;
    imgView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    imgView.editable = NO;
    [containerView addSubview:imgView];
    self.imageView = imgView;

    NSTextField *label = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 180, 28)];
    label.editable = NO;
    label.bordered = NO;
    label.backgroundColor = [NSColor clearColor];
    label.textColor = [NSColor labelColor];
    label.font = [NSFont systemFontOfSize:9.0];
    label.alignment = NSTextAlignmentCenter;
    label.lineBreakMode = NSLineBreakByTruncatingTail;
    label.maximumNumberOfLines = 2;
    label.autoresizingMask = NSViewWidthSizable;
    [containerView addSubview:label];
    self.textField = label;

    self.view = containerView;

    // Sync border in case setSelected: fired before loadView ran.
    [self refreshSelectionBorder];
}

- (void)setRepresentedObject:(id)representedObject
{
    [super setRepresentedObject:representedObject];
    VSTrackedObjectPortrait *portrait = (VSTrackedObjectPortrait *)representedObject;
    if (portrait != nil) {
        self.imageView.image = [portrait image];
        if (self.showObjectCaption) {
            NSString *typeName = portrait.trackedObject.type.name ?: @"Object";
            NSString *index = [portrait.trackedObject.index stringValue] ?: @"?";
            NSString *name = portrait.trackedObject.name;
            NSString *namePart = (name.length > 0) ? [NSString stringWithFormat:@" (%@)", name] : @"";
            NSString *timecode = portrait.timecode ?: @"";
            self.textField.stringValue = [NSString stringWithFormat:@"%@ %@%@\n%@", typeName, index, namePart, timecode];
        } else {
            self.textField.stringValue = portrait.timecode ?: @"";
        }
    } else {
        self.imageView.image = nil;
        self.textField.stringValue = @"";
    }
}

- (void)prepareForReuse
{
    [super prepareForReuse];
    // A recycled cell keeps whatever border its previous index path had until the
    // collection view re-applies selection state, so clear it up front.
    [self setSelectionBorderVisible:NO];
}

- (void)setSelected:(BOOL)selected
{
    [super setSelected:selected];
    [self setSelectionBorderVisible:selected];
}

- (void)refreshSelectionBorder
{
    [self setSelectionBorderVisible:self.isSelected];
}

- (void)setSelectionBorderVisible:(BOOL)visible
{
    ((VSPortraitContainerView *)self.view).showsSelectionBorder = visible;
    [self.view setNeedsDisplay:YES];
}

@end
