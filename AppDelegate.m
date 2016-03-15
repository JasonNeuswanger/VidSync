/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
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


#import "AppDelegate.h"

@implementation AppDelegate

+ (void)initialize
{
	// this is a very early place to do initialization, although not as early as in main() itself
	// I can't put the user defaults initial values here, because it happens after the main nib is loaded
}

- (NSError*) application:(NSApplication*)application willPresentError:(NSError*)error
{
    if (error)
    {
        NSDictionary* userInfo = [error userInfo];
        NSLog (@"User encountered the following error: %@", userInfo);
    }
    return error;
}


+ (void) setUserDefaultsInitialValues {
    [[NSUserDefaultsController sharedUserDefaultsController] setInitialValues:[AppDelegate userDefaultsInitialValues]];
}

+ (NSMutableDictionary *) userDefaultsInitialValues {
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
    [initialValueDict setObject:@"Floating" forKey:@"unsyncedAVPlayerViewControlsStyle"];
    [initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"showAdvancedControlsWithOnlyMasterClip"];
    [initialValueDict setObject:NSUserName() forKey:@"currentObserverName"];
    
	// initial values for advanced playback controls
	
	[initialValueDict setObject:[NSNumber numberWithDouble:10] forKey:@"advancedPlaybackStepAmount"];
	[initialValueDict setObject:@"frames" forKey:@"advancedPlaybackStepUnits"];
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
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"quadratShowSurfaceGridOverlayFront"];
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"quadratShowSurfaceGridOverlayBack"];
	
	// initial values for distortion correction overlays
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showDistortionConnectingLines"];
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showDistortionTipToTipLines"];
	[initialValueDict setObject:[NSNumber numberWithFloat:2.5] forKey:@"distortionPointSize"];
	[initialValueDict setObject:[NSNumber numberWithFloat:1.0] forKey:@"distortionLineThickness"];
    [initialValueDict setObject:[NSNumber numberWithInt:2] forKey:@"showDistortionLinesFromWhichTimecodes"];
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
	
	[initialValueDict setObject:[NSNumber numberWithBool:FALSE] forKey:@"newAnnotationAppendTimer"];
	[initialValueDict setObject:[NSNumber numberWithInt:5] forKey:@"newAnnotationDuration"];
	[initialValueDict setObject:[NSNumber numberWithInt:3] forKey:@"newAnnotationFadeTime"];
	[initialValueDict setObject:[NSNumber numberWithInt:30] forKey:@"newAnnotationFontSize"];
	[initialValueDict setObject:[NSNumber numberWithInt:400] forKey:@"newAnnotationWidth"];
	[initialValueDict setObject:@"Arial" forKey:@"newAnnotationFontFace"];
	[initialValueDict setObject:[NSArchiver archivedDataWithRootObject:[NSColor orangeColor]] forKey:@"newAnnotationColor"];
	
	// initial values for capture settings
	
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeOverlaysInExportedFiles"];
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeProjectNameInCapturedFileName"];
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeMasterTimecodeInCapturedFileName"];
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"includeClipNameInCapturedFileName"];
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"separateClipsByFolder"];
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"createFolderForProjectCaptures"];
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
    
    // initial values for open/save directories
    
    [initialValueDict setObject:@"~/" forKey:@"movieOpenDirectory"];
    [initialValueDict setObject:@"~/" forKey:@"mainFileSaveDirectory"];
    
    return initialValueDict;
    
}

- (IBAction)revertToInitialValues:(id)sender
{
    NSInteger alertResult = NSRunAlertPanel(@"Are you sure?",@"Are you sure you want to restore all preferences to their initial values?",@"Yes",@"No",nil);
    if (alertResult == 1) {
        [[NSUserDefaultsController sharedUserDefaultsController] revertToInitialValues:sender];
    }
}

@end
