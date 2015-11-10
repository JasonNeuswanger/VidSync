//
//  VSAnnotation.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/30/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VSAnnotation.h"


@implementation VSAnnotation

@dynamic videoClip;
@dynamic observer;
@dynamic screenX;
@dynamic screenY;
@dynamic startTimecode;
@dynamic width;
@dynamic appendsTimer;
@synthesize tempOpacity;

- (void) awakeFromFetch
{
    [self startObservers];
    [super awakeFromFetch];
}

- (void) awakeFromInsert
{
    [self startObservers];
    [super awakeFromFetch];
}

- (void) startObservers
{
    [self addObserver:self forKeyPath:@"width" options:0 context:NULL];
    [self addObserver:self forKeyPath:@"color" options:0 context:NULL];
    [self addObserver:self forKeyPath:@"size" options:0 context:NULL];
    [self addObserver:self forKeyPath:@"shape" options:0 context:NULL];
    [self addObserver:self forKeyPath:@"notes" options:0 context:NULL];
    [self addObserver:self forKeyPath:@"appendsTimer" options:0 context:NULL];
}


- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
	if (self.videoClip != nil && self.videoClip.windowController != nil) [self.videoClip.windowController refreshOverlay];
}

- (NSAttributedString *) tableGlyphForColor
{
    NSMutableAttributedString *glyph = [[NSMutableAttributedString alloc] initWithString:@"\uf0c8"];
    NSRange glyphRange = NSMakeRange(0, [glyph length]);
    [glyph addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:9.0f] range:glyphRange];
    return glyph;
}

- (void) dealloc
{
    [self carefullyRemoveObserver:self forKeyPath:@"width"];
    [self carefullyRemoveObserver:self forKeyPath:@"color"];
    [self carefullyRemoveObserver:self forKeyPath:@"size"];
    [self carefullyRemoveObserver:self forKeyPath:@"shape"];
    [self carefullyRemoveObserver:self forKeyPath:@"notes"];
    [self carefullyRemoveObserver:self forKeyPath:@"appendsTimer"];
}

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath
{
    if (observer != nil) {
        @try {
            [self removeObserver:observer forKeyPath:keyPath];
        } @catch (id exception) {
        }
    }
}

@end
