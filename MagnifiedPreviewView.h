//
//  MagnifiedPreviewView.h
//  VidSync
//
//  Created by Jason Neuswanger on 10/27/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>

@interface MagnifiedPreviewView : NSClipView {
	
	NSView *__strong previewMovieView;
	
	CALayer *__strong previewMovieContainer;
    
    AVPlayerLayer *__strong previewMovieLayer;
    CALayer *__strong videoFilterContainerLayer;
	CAShapeLayer *__strong previewDot;
	CAShapeLayer *__strong previewReticle;
    
	NSPoint previewCenterPoint;
	CGPoint crosshairsCenterPoint;
	NSPoint lastMousePoint;
	AVPlayerItem *__weak lastPlayerItem;
	
	CIFilter *__strong exposureFilter, *__strong gammaFilter, *__strong unsharpMaskFilter, *__strong sharpenFilter;

}

+ (void) setFiltersToDefaults;

- (void) observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context;
- (void) updateFilterWithUserDefaultsKey:(NSString *)defaultsKey andLayerKeyPath:(NSString *)layerKeyPath;
- (void) setPlayerLayer:(AVPlayerLayer*)playerLayer;
- (void) updatePreviewFrameFromPlayerItem:(AVPlayerItem*)playerItem;
- (void) setPreviewDot;
- (void) setPreviewReticle;
+ (void) buildArcRingAtRadius:(CGFloat)r1 withHalfArcRadians:(CGFloat)halfArc inPath:(CGMutablePathRef)path;
- (void) setCenterPoint:(NSPoint)mousePoint;


@end
