//
//  MyApplicationDelegate.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/29/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "VidSyncDocument.h"

@implementation VidSyncDocument (NSApplicationDelegate)

+ (void)initialize
{
	// this is a very early place to do initialization, although not as early as in main() itself
	// I can't put the user defaults initial values here, because it happens after the main nib is loaded
}



+ (void) setUserDefaultsInitialValues {
	NSMutableDictionary *initialValueDict = [NSMutableDictionary new];
    	
	// miscellaneous initial values
	
	[initialValueDict setObject:@"Project" forKey:@"latestMainTabViewSelectedLabel"];
	[initialValueDict setObject:[NSHomeDirectory() stringByAppendingPathComponent:@"Documents"] forKey:@"masterCaptureFolder"];
	[initialValueDict setObject:@"Unpaired" forKey:@"hintLinesSetting"];
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showWorldCoordinatesNextToQuadratPoints"];	
	[initialValueDict setObject:@"All Frames" forKey:@"selectedEventsPointsTimeFilter"];
	[initialValueDict setObject:[NSNumber numberWithFloat:0.05] forKey:@"calibrationRefinementIgnoresHighestPercent"];	
	[initialValueDict setObject:[NSNumber numberWithFloat:20.0] forKey:@"hintLineDrawInterval"];
    [initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showScreenItemDropShadows"];
    [initialValueDict setObject:[NSNumber numberWithBool:1.0] forKey:@"screenItemDropShadowBlurRadius"];
    
	// initial values for advanced playback controls
	
	[initialValueDict setObject:[NSNumber numberWithInt:3] forKey:@"advancedPlaybackStepFrames"];
	[initialValueDict setObject:[NSNumber numberWithFloat:0.33] forKey:@"advancedPlaybackRate1"];
	[initialValueDict setObject:[NSNumber numberWithFloat:2.0] forKey:@"advancedPlaybackRate2"];
	[initialValueDict setObject:[NSNumber numberWithInt:0] forKey:@"advancedPlaybackMode1"];
	[initialValueDict setObject:[NSNumber numberWithFloat:5.0] forKey:@"advancedPlaybackExactDuration1"];
	[initialValueDict setObject:[NSNumber numberWithFloat:2.0] forKey:@"advancedPlaybackMinRandomDuration1"];
	[initialValueDict setObject:[NSNumber numberWithFloat:10.0] forKey:@"advancedPlaybackMaxRandomDuration1"];
    [initialValueDict setObject:[NSNumber numberWithInt:0] forKey:@"advancedPlaybackMode2"];
	[initialValueDict setObject:[NSNumber numberWithFloat:5.0] forKey:@"advancedPlaybackExactDuration2"];
	[initialValueDict setObject:[NSNumber numberWithFloat:2.0] forKey:@"advancedPlaybackMinRandomDuration2"];
	[initialValueDict setObject:[NSNumber numberWithFloat:10.0] forKey:@"advancedPlaybackMaxRandomDuration2"];
	
	// initial values for the magnified preview settings
	[initialValueDict setObject:[NSNumber numberWithFloat:3.5] forKey:@"previewMagnification"];		
	[initialValueDict setObject:[NSNumber numberWithFloat:0.0] forKey:@"previewUnsharpMaskRadius"];		
	[initialValueDict setObject:[NSNumber numberWithFloat:0.0] forKey:@"previewUnsharpMaskIntensity"];			
	[initialValueDict setObject:[NSNumber numberWithFloat:0.0] forKey:@"previewExposure"];		
	[initialValueDict setObject:[NSNumber numberWithFloat:1.0] forKey:@"previewGamma"];	
	[initialValueDict setObject:[NSNumber numberWithFloat:0.0] forKey:@"previewSharpness"];
	[initialValueDict setObject:[NSNumber numberWithFloat:3.0] forKey:@"previewDotSize"];
	[initialValueDict setObject:[NSNumber numberWithFloat:100.0] forKey:@"previewReticleSize"];
	[initialValueDict setObject:[NSNumber numberWithFloat:1.0] forKey:@"previewUseReticle"];    
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor cyanColor]] forKey:@"previewDotColor"];
	
	// initial values for quadrat coordinate point/grid overlays
	[initialValueDict setObject:[NSNumber numberWithFloat:2.0] forKey:@"quadratGridOverlayLineThickness"];
	[initialValueDict setObject:[NSNumber numberWithFloat:0.1] forKey:@"quadratGridOverlayLineSpacing"];
	[initialValueDict setObject:[NSNumber numberWithFloat:18.0] forKey:@"quadratPointOverlayCircleDiameterFront"];
	[initialValueDict setObject:[NSNumber numberWithFloat:12.0] forKey:@"quadratPointOverlayCircleDiameterBack"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor cyanColor]] forKey:@"quadratOverlayColorFront"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor orangeColor]] forKey:@"quadratOverlayColorBack"];
	[initialValueDict setObject:[NSNumber numberWithInt:0] forKey:@"quadratShowSurfaceGridOverlayFront"];
	[initialValueDict setObject:[NSNumber numberWithInt:0] forKey:@"quadratShowSurfaceGridOverlayBack"];
	
	// initial values for distortion correction overlays
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"showDistortionOverlay"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showDistortionConnectingLines"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showDistortionTipToTipLines"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showDistortionCorrectedPoints"];
	[initialValueDict setObject:[NSNumber numberWithFloat:2.5] forKey:@"distortionPointSize"];
	[initialValueDict setObject:[NSNumber numberWithFloat:1.0] forKey:@"distortionLineThickness"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor greenColor]] forKey:@"distortionConnectingLinesColor"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor orangeColor]] forKey:@"distortionTipToTipLinesColor"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor magentaColor]] forKey:@"distortionCorrectedPointsColor"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor cyanColor]] forKey:@"distortionCorrectedLinesColor"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor yellowColor]] forKey:@"distortionCenterColor"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor redColor]] forKey:@"distortionPointsColor"];	
	
	// initial values for automatic plumbline detection algorithm for distortion correction
    [initialValueDict setObject:[NSNumber numberWithBool:FALSE] forKey:@"showDirectOpenCVOutputWindow"];
	[initialValueDict setObject:[NSNumber numberWithDouble:0.2] forKey:@"chessboardDetectionCandidateDistanceTolerance"];
	[initialValueDict setObject:[NSNumber numberWithInt:2000] forKey:@"chessboardDetectionMaxNumCorners"];
	[initialValueDict setObject:[NSNumber numberWithDouble:30.0] forKey:@"chessboardDetectionMinDistance"];
	[initialValueDict setObject:[NSNumber numberWithDouble:0.01] forKey:@"chessboardDetectionQualityLevel"];
	[initialValueDict setObject:[NSNumber numberWithInt:4] forKey:@"chessboardDetectionMinLineLength"];
	[initialValueDict setObject:[NSNumber numberWithInt:15] forKey:@"chessboardDetectionCornerSubPixwindowSize"];
	
	// initial values for the pixel error overlay
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"showPixelErrorOverlay"];	
	[initialValueDict setObject:[NSNumber numberWithFloat:3.0] forKey:@"pixelErrorDotSize"];
	[initialValueDict setObject:[NSNumber numberWithFloat:2.0] forKey:@"pixelErrorLineWidth"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor cyanColor]] forKey:@"pixelErrorLineColor"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor orangeColor]] forKey:@"pixelErrorPointColor"];
	
	// initial values for the appearance of the point selection indicator
	[initialValueDict setObject:[NSNumber numberWithFloat:20.0] forKey:@"pointSelectionIndicatorLineLength"];
	[initialValueDict setObject:[NSNumber numberWithFloat:3.0] forKey:@"pointSelectionIndicatorLineWidth"];
	[initialValueDict setObject:[NSNumber numberWithFloat:1.5] forKey:@"pointSelectionIndicatorSizeFactor"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor yellowColor]] forKey:@"pointSelectionIndicatorColor"];
	[initialValueDict setObject:[NSNumber numberWithFloat:0.3] forKey:@"selectedPointNudgeDistance"];
		
	// initial values for annotation visual settings
	
	[initialValueDict setObject:[NSNumber numberWithInt:5] forKey:@"newAnnotationDuration"];	
	[initialValueDict setObject:[NSNumber numberWithInt:3] forKey:@"newAnnotationFadeTime"];	
	[initialValueDict setObject:[NSNumber numberWithInt:24] forKey:@"newAnnotationFontSize"];
	[initialValueDict setObject:@"Helvetica" forKey:@"newAnnotationFontFace"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor orangeColor]] forKey:@"newAnnotationColor"];
	
	// initial values for capture settings
	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeOverlaysInExportedFiles"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeProjectNameInCapturedFileName"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeMasterTimecodeInCapturedFileName"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeClipNameInCapturedFileName"];	
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"separateClipsByFolder"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"createFolderForProjectCaptures"];	
	[initialValueDict setObject:@"" forKey:@"capturedFileNameCustomText"];	

	// initial values for data export settings
	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeProjectNameInExportedFileName"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeCurrentDateInExportedFileName"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeCurrentTimeInExportedFileName"];	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"createFolderForProjectExports"];	
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"includeScreenCoordsInExports"];	
	[initialValueDict setObject:@"" forKey:@"exportedFileNameCustomText"];	
	
    // initial values for portrait browser zoom sliders
    
    [initialValueDict setObject:[NSNumber numberWithFloat:1.0] forKey:@"allPortraitsBrowserZoom"];
    [initialValueDict setObject:[NSNumber numberWithFloat:1.0] forKey:@"objectsPortraitsBrowserZoom"];
	
	[[NSUserDefaultsController sharedUserDefaultsController] setInitialValues:initialValueDict];

	// The line below is an example of how to correctly access one of the colors from the sharedUserDefaultsController.  It's picky about this.
	// NSColor *theColor = [NSUnarchiver unarchiveObjectWithData:[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"newAnnotationColor"]];

}

@end
