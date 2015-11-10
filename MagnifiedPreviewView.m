//
//  MagnifiedPreviewView.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/27/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "MagnifiedPreviewView.h"


@implementation MagnifiedPreviewView

+ (void) setFiltersToDefaults
{
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithFloat:2.0] forKey:@"previewMagnification"];
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithFloat:0.0] forKey:@"previewExposure"];	
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithFloat:1.0] forKey:@"previewGamma"];
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithFloat:0.0] forKey:@"previewUnsharpMaskRadius"];	
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithFloat:0.0] forKey:@"previewUnsharpMaskIntensity"];	
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:[NSNumber numberWithFloat:0.0] forKey:@"previewSharpness"];	
}

- (id)initWithFrame:(NSRect)frame {
   self = [super initWithFrame:frame];
    if (self) {
		[self setCopiesOnScroll:YES]; // Renders slightly faster than 'NO'
		
		previewMovieView = [[NSView alloc] initWithFrame:frame];
        previewMovieView.layerUsesCoreImageFilters = YES;
        
		previewMovieContainer = [CALayer layer];
		[previewMovieView setLayer:previewMovieContainer];  // Calling setLayer before setWantsLayer establishes a layer-hosting view (capable of hosting sublayers) as opposed to a layer-backed view (no sublayers).
		[previewMovieView setWantsLayer:YES];
        videoFilterContainerLayer = [CALayer layer];        // This is a separate container just for the video so I can apply CIFilters to the swapped AVPlayerLayers without also applying them to the reticles.
        [previewMovieContainer insertSublayer:videoFilterContainerLayer atIndex:0];
        
		previewDot = [CAShapeLayer layer];
		previewReticle = [CAShapeLayer layer];
        [previewMovieContainer insertSublayer:[CALayer layer] atIndex:1];   // dummy layer, necessary for some reason to keep preview dot or reticle from being hidden when movie layer is swapped for different videos
		[previewMovieContainer insertSublayer:previewReticle atIndex:2];
		[previewMovieContainer insertSublayer:previewDot atIndex:3];
		
		exposureFilter = [CIFilter filterWithName:@"CIExposureAdjust"];
		exposureFilter.name = @"exposureFilter";
        gammaFilter = [CIFilter filterWithName:@"CIGammaAdjust"];
		gammaFilter.name = @"gammaFilter";
		unsharpMaskFilter = [CIFilter filterWithName:@"CIUnsharpMask"];
		unsharpMaskFilter.name = @"unsharpMaskFilter";
		sharpenFilter = [CIFilter filterWithName:@"CISharpenLuminance"];
		sharpenFilter.name = @"sharpenFilter";
        
        
        // Note: I'm currently (as of 10-10-2015) disabling both sharpening filters because they're preventing anything from showing up in the magnified
        // preview at all in OS X 10.11 (El Capitan). The whole preview just shows as white (except the crosshair/dot). These probably weren't too useful
        // anyway. I'll keep them in the code to see if things work again in later OS X versions, but for now it's not worth hunting down the bug.
        // I have also left intact but disabled (unchecked the "Enabled" box in interface builder) the preview panel controls for sharpening.
        // Everything pertaining to sharpening filters is also commented out farther down this file.
        
        [videoFilterContainerLayer setFilters:[NSArray arrayWithObjects:exposureFilter,gammaFilter,/*unsharpMaskFilter,sharpenFilter,*/nil]];
        [self updateFilterWithUserDefaultsKey:@"previewExposure" andLayerKeyPath:@"filters.exposureFilter.inputEV"];
		[self updateFilterWithUserDefaultsKey:@"previewGamma" andLayerKeyPath:@"filters.gammaFilter.inputPower"];
		//[self updateFilterWithUserDefaultsKey:@"previewUnsharpMaskRadius" andLayerKeyPath:@"filters.unsharpMaskFilter.inputRadius"];
		//[self updateFilterWithUserDefaultsKey:@"previewUnsharpMaskIntensity" andLayerKeyPath:@"filters.unsharpMaskFilter.inputIntensity"];
		//[self updateFilterWithUserDefaultsKey:@"previewSharpness" andLayerKeyPath:@"filters.sharpenFilter.inputSharpness"];
        
		[self setDocumentView:previewMovieView];
		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewMagnification" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewExposure" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewGamma" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewUnsharpMaskRadius" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewUnsharpMaskIntensity" options:0 context:NULL];
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewSharpness" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewDotSize" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewDotColor" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewReticleSize" options:0 context:NULL];		
		[[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forKeyPath:@"values.previewUseReticle" options:0 context:NULL];		

    }
    return self;
}

- (void) observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context {
	if ([keyPath isEqual: @"values.previewExposure"]) {
		[self updateFilterWithUserDefaultsKey:@"previewExposure" andLayerKeyPath:@"filters.exposureFilter.inputEV"];
	} else if ([keyPath isEqual: @"values.previewGamma"]) {		
		[self updateFilterWithUserDefaultsKey:@"previewGamma" andLayerKeyPath:@"filters.gammaFilter.inputPower"];
	} else if ([keyPath isEqual: @"values.previewUnsharpMaskRadius"]){
		//[self updateFilterWithUserDefaultsKey:@"previewUnsharpMaskRadius" andLayerKeyPath:@"filters.unsharpMaskFilter.inputRadius"];
	} else if ([keyPath isEqual: @"values.previewUnsharpMaskIntensity"]) {
		//[self updateFilterWithUserDefaultsKey:@"previewUnsharpMaskIntensity" andLayerKeyPath:@"filters.unsharpMaskFilter.inputIntensity"];
	} else if ([keyPath isEqual: @"values.previewSharpness"]){
		//[self updateFilterWithUserDefaultsKey:@"previewSharpness" andLayerKeyPath:@"filters.sharpenFilter.inputSharpness"];
	} else if ([keyPath isEqual: @"values.previewMagnification"]) {
        //NSLog(@"Should be updating preview magnification with item %@ to last mouse point (%1.3f,%1.3f) and layer %@",lastPlayerItem,lastMousePoint.x,lastMousePoint.y,previewMovieLayer);
		[self updatePreviewFrameFromPlayerItem:lastPlayerItem];
		[self setCenterPoint:lastMousePoint];
        [self setPlayerLayer:previewMovieLayer];
	} else if ([keyPath isEqual: @"values.previewDotSize"] || [keyPath isEqual: @"values.previewDotColor"] || [keyPath isEqual:@"values.previewUseReticle"] || [keyPath isEqual: @"values.previewReticleSize"]) {
        if ([[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"previewUseReticle"] floatValue] > 0.5) {
            [self setPreviewReticle];
            previewReticle.hidden = NO;
            previewDot.hidden = YES;
        } else {
            [self setPreviewDot];
            previewDot.hidden = NO;
            previewReticle.hidden = YES;
        }
	}
}

- (void) updateFilterWithUserDefaultsKey:(NSString *)defaultsKey andLayerKeyPath:(NSString *)layerKeyPath
{
	float floatValue = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:defaultsKey] floatValue];
	[videoFilterContainerLayer setValue:[NSNumber numberWithFloat:floatValue] forKeyPath:layerKeyPath];
}

- (void) setPlayerLayer:(AVPlayerLayer*)playerLayer
{
	if (![previewMovieLayer isEqualTo:playerLayer]) {
        previewMovieLayer = playerLayer;    // Necessary for checking whether we're already on the given layer (the above "if") and also for adjusting the magnified preview
        if ([[videoFilterContainerLayer sublayers] count] == 0) {
            [videoFilterContainerLayer addSublayer:previewMovieLayer];
        } else {
            [videoFilterContainerLayer replaceSublayer:[[videoFilterContainerLayer sublayers] objectAtIndex:0] with:previewMovieLayer];
        }
        [self updatePreviewFrameFromPlayerItem:playerLayer.player.currentItem];
	}
}

- (void) updatePreviewFrameFromPlayerItem:(AVPlayerItem*)playerItem
{
    CGSize movieSize = [[[playerItem.asset tracksWithMediaType:AVMediaTypeVideo] firstObject] naturalSize];
	float mag = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"previewMagnification"] floatValue];
	[previewMovieView setFrame:NSMakeRect(0.0,0.0,movieSize.width*mag,movieSize.height*mag)];
	previewMovieContainer.bounds = NSRectToCGRect([previewMovieView bounds]);
	previewMovieContainer.frame = NSRectToCGRect([previewMovieView frame]);
	videoFilterContainerLayer.bounds = NSRectToCGRect([previewMovieView bounds]);
	videoFilterContainerLayer.frame = NSRectToCGRect([previewMovieView frame]);
	previewMovieLayer.bounds = NSRectToCGRect([previewMovieView bounds]);
	previewMovieLayer.frame = NSRectToCGRect([previewMovieView frame]);
    if ([[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"previewUseReticle"] floatValue] > 0.5) {
        [self setPreviewReticle];
        previewReticle.hidden = NO;
        previewDot.hidden = YES;
    } else {
        [self setPreviewDot];
        previewDot.hidden = NO;
        previewReticle.hidden = YES;
    }
}

- (void) setPreviewReticle
{
	NSColor *previewDotColor = [UtilityFunctions userDefaultColorForKey:@"previewDotColor"];
	CGColorRef reticleColor = CGColorCreateGenericRGB([previewDotColor redComponent], [previewDotColor greenComponent], [previewDotColor blueComponent], [previewDotColor alphaComponent]);

    // c is the width & height of CALayer, which is by default centered on its anchor position (the one it's pointing to) already
    const CGFloat c = (CGFloat) [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"previewReticleSize"] floatValue];
    const CGFloat z = c/2.0f; // (z,z) is the "zero" position in the square coordinate system of the CAShapeLayer previewMovieCrosshairs
    const CGFloat Pi = (CGFloat) M_PI;
    const CGFloat halfArc = Pi/8.0f; // length of the arc in radians
    const CGFloat r1 = c/2;   // radius of the first set of arcs
    const CGFloat r2 = c/3;   // radius of the first set of arcs
    const CGFloat r3 = c/6;   // radius of the first set of arcs
    const CGFloat r4 = c/12;   // radius of the first set of arcs
    
    previewReticle.bounds = CGRectMake(0,0,c,c);
	previewReticle.frame = CGRectMake(0,0,c,c);	
    previewReticle.backgroundColor = CGColorGetConstantColor(kCGColorClear);
    previewReticle.strokeColor = reticleColor;
    previewReticle.fillColor = CGColorGetConstantColor(kCGColorClear);
    previewReticle.lineWidth = 1.2f;
    previewReticle.contentsGravity = kCAGravityCenter;
    previewReticle.shadowColor = [NSColor blackColor].CGColor;
    previewReticle.shadowRadius = 1.0;
    previewReticle.shadowOffset = CGSizeMake(0,0);
    previewReticle.shadowOpacity = 1.0;

    CGPoint crosshairsh[2] = {CGPointMake(z-c/25.0f,z),CGPointMake(z+c/25.0f,z)};
    CGPoint crosshairsv[2] = {CGPointMake(z,z-c/25.0f),CGPointMake(z,z+c/25.0f)};
    CGMutablePathRef path = CGPathCreateMutable();
    CGPathAddLines(path,NULL,crosshairsh,2);
    CGPathAddLines(path,NULL,crosshairsv,2);
    
    [MagnifiedPreviewView buildArcRingAtRadius:r1 withHalfArcRadians:halfArc inPath:path];
    [MagnifiedPreviewView buildArcRingAtRadius:r2 withHalfArcRadians:halfArc inPath:path];
    [MagnifiedPreviewView buildArcRingAtRadius:r3 withHalfArcRadians:halfArc inPath:path];
    [MagnifiedPreviewView buildArcRingAtRadius:r4 withHalfArcRadians:halfArc inPath:path];
    
    previewReticle.path = path;
    
    [previewReticle setNeedsDisplay];
	CGColorRelease(reticleColor);
    CGPathRelease(path);
}

+ (void) buildArcRingAtRadius:(CGFloat)r1 withHalfArcRadians:(CGFloat)halfArc inPath:(CGMutablePathRef)path
{
    // c is the width & height of CALayer, which is by default centered on its anchor position (the one it's pointing to) already
    const CGFloat c = (CGFloat) [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"previewReticleSize"] floatValue];
    const CGFloat z = c/2.0f; // (z,z) is the "zero" position in the square coordinate system of the CAShapeLayer previewMovieCrosshairs
    const CGFloat Pi = (CGFloat) M_PI;

    CGPathMoveToPoint(path,NULL,z-r1*cosf(-halfArc),z-r1*sinf(-halfArc));
    CGPathAddArc(path, NULL, z, z, r1, Pi-halfArc, Pi+halfArc, FALSE);      // left side
    CGPathMoveToPoint(path,NULL,z-r1*cosf(-halfArc),z-r1*sinf(-halfArc));
    CGPathCloseSubpath(path);
    
    CGPathMoveToPoint(path,NULL,z+r1*cosf(halfArc),z+r1*sinf(halfArc));
    CGPathAddArc(path, NULL, z, z, r1, halfArc, -halfArc, TRUE);            // right side
    CGPathMoveToPoint(path,NULL,z+r1*cosf(halfArc),z+r1*sinf(halfArc));
    CGPathCloseSubpath(path);
    
    CGPathMoveToPoint(path,NULL,z-r1*cosf(Pi/2-halfArc),z+r1*sinf(Pi/2-halfArc));
    CGPathAddArc(path, NULL, z, z, r1, Pi/2+halfArc, Pi/2-halfArc, TRUE);  // top
    CGPathMoveToPoint(path,NULL,z-r1*cosf(Pi/2-halfArc),z+r1*sinf(Pi/2-halfArc));
    CGPathCloseSubpath(path);    
    
    CGPathMoveToPoint(path,NULL,z-r1*cosf(-Pi/2-halfArc),z+r1*sinf(-Pi/2-halfArc));
    CGPathAddArc(path, NULL, z, z, r1, -Pi/2+halfArc, -Pi/2-halfArc, TRUE);  // bottom
    CGPathMoveToPoint(path,NULL,z-r1*cosf(-Pi/2-halfArc),z+r1*sinf(-Pi/2-halfArc));
    CGPathCloseSubpath(path); 
    
    CGPathMoveToPoint(path,NULL,z,z);    
}

- (void) setPreviewDot
{
	float previewDotSize = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"previewDotSize"] floatValue];
	NSColor *previewDotColor = [UtilityFunctions userDefaultColorForKey:@"previewDotColor"];
	CGColorRef crosshairsColor = CGColorCreateGenericRGB([previewDotColor redComponent], [previewDotColor greenComponent], [previewDotColor blueComponent], [previewDotColor alphaComponent]);
	previewDot.backgroundColor = crosshairsColor;
	CGColorRelease(crosshairsColor);
	previewDot.bounds = CGRectMake(0.0,0.0,previewDotSize,previewDotSize);
	previewDot.frame = CGRectMake(0.0,0.0,previewDotSize,previewDotSize);
    previewDot.shadowColor = [NSColor blackColor].CGColor;
    previewDot.shadowRadius = 1.0;
    previewDot.shadowOffset = CGSizeMake(0,0);
    previewDot.shadowOpacity = 1.0;
    [previewDot setNeedsDisplay];
}

- (void) setCenterPoint:(NSPoint)mousePoint
{
    // NSLog(@"Setting center point to %@",[NSValue valueWithPoint:mousePoint]);
	
    lastMousePoint = mousePoint;	// Used to call this function when the magnification slider is changed
	float mag = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"previewMagnification"] floatValue];
    
    // the problem is happening in both of these variables (previewCenterPoint and crosshairsCenterPoint because the preview is centered+crosshaired on the wrong position
    // yet the input mousePoint variable shows the right position
    // and it happens even when "mag" = 1 so that should have no effect
    // in other words I can't find a problem here... maybe the display of the layer itself is messed up?
    
	previewCenterPoint.x = mag * mousePoint.x - [self documentVisibleRect].size.width/2;
	previewCenterPoint.y = mag * mousePoint.y - [self documentVisibleRect].size.height/2;
	crosshairsCenterPoint.x = mag * mousePoint.x;// - previewMovieCrosshairs.frame.size.width/2;	not sure why I had to comment out this "correction" but it's actually right without it
	crosshairsCenterPoint.y = mag * mousePoint.y;// - previewMovieCrosshairs.frame.size.height/2;	as can be seen by making the previewDotSize huge; it still centers in the right spot
	previewReticle.position = crosshairsCenterPoint;
    previewDot.position = crosshairsCenterPoint;
	[self scrollToPoint:previewCenterPoint];
}

- (void) dealloc
{
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewMagnification"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewExposure"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewGamma"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewUnsharpMaskRadius"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewUnsharpMaskIntensity"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewSharpness"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewDotSize"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewDotColor"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewReticleSize"];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forKeyPath:@"values.previewUseReticle"];
}

@end
