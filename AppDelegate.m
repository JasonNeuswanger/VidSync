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


#import "AppDelegate.h"
#import "VSCrashReporter.h"

@implementation AppDelegate

+ (void)initialize
{
	// this is a very early place to do initialization, although not as early as in main() itself
	// I can't put the user defaults initial values here, because it happens after the main nib is loaded
}

// VidSync requires an existing project file — never open an untitled document on launch.
- (BOOL)applicationShouldOpenUntitledFile:(NSApplication *)sender { return NO; }

- (void) applicationDidFinishLaunching:(NSNotification *)notification
{
	// Crash handling first, so even a crash later in launch gets recorded; then the offer to email
	// any report the previous run left behind.
	[VSCrashReporter install];
	[VSCrashReporter offerToSendPendingReport];

	// The stock Window menu items get their glyphs from the system, so Tile Windows has to supply its
	// own to match them. Set here rather than in the nib because Interface Builder's symbol-image
	// markup is easy to lose, and because this can fall back if a symbol isn't available.
	NSMenuItem *tileWindowsItem = [AppDelegate menuItemWithAction:@selector(tileWindows:) inMenu:[NSApp mainMenu]];
	if (tileWindowsItem != nil && tileWindowsItem.image == nil) {
		NSImage *glyph = [NSImage imageWithSystemSymbolName:@"macwindow.on.rectangle" accessibilityDescription:@"Tile Windows"];
		if (glyph == nil) glyph = [NSImage imageWithSystemSymbolName:@"rectangle.3.group" accessibilityDescription:@"Tile Windows"];
		tileWindowsItem.image = glyph;
	}
}

+ (NSMenuItem *) menuItemWithAction:(SEL)action inMenu:(NSMenu *)menu
{
	for (NSMenuItem *item in [menu itemArray]) {
		if ([item action] == action) return item;
		if ([item hasSubmenu]) {
			NSMenuItem *itemInSubmenu = [AppDelegate menuItemWithAction:action inMenu:[item submenu]];
			if (itemInSubmenu != nil) return itemInSubmenu;
		}
	}
	return nil;
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
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor cyanColor] requiringSecureCoding:FALSE error:nil] forKey:@"previewDotColor"];

	// initial values for quadrat coordinate point/grid overlays
	[initialValueDict setObject:[NSNumber numberWithFloat:2.0] forKey:@"quadratGridOverlayLineThickness"];
	[initialValueDict setObject:[NSNumber numberWithFloat:0.1] forKey:@"quadratGridOverlayLineSpacing"];
	[initialValueDict setObject:[NSNumber numberWithFloat:18.0] forKey:@"quadratPointOverlayCircleDiameterFront"];
	[initialValueDict setObject:[NSNumber numberWithFloat:12.0] forKey:@"quadratPointOverlayCircleDiameterBack"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor cyanColor] requiringSecureCoding:FALSE error:nil] forKey:@"quadratOverlayColorFront"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor orangeColor] requiringSecureCoding:FALSE error:nil] forKey:@"quadratOverlayColorBack"];
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"quadratShowSurfaceGridOverlayFront"];
	[initialValueDict setObject:[NSNumber numberWithBool:NO] forKey:@"quadratShowSurfaceGridOverlayBack"];
	
	// initial values for distortion correction overlays
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showDistortionConnectingLines"];
	[initialValueDict setObject:[NSNumber numberWithBool:YES] forKey:@"showDistortionTipToTipLines"];
	[initialValueDict setObject:[NSNumber numberWithFloat:2.5] forKey:@"distortionPointSize"];
	[initialValueDict setObject:[NSNumber numberWithFloat:1.0] forKey:@"distortionLineThickness"];
	[initialValueDict setObject:[NSNumber numberWithInt:2] forKey:@"showDistortionLinesFromWhichTimecodes"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor greenColor] requiringSecureCoding:FALSE error:nil] forKey:@"distortionConnectingLinesColor"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor orangeColor] requiringSecureCoding:FALSE error:nil] forKey:@"distortionTipToTipLinesColor"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor magentaColor] requiringSecureCoding:FALSE error:nil] forKey:@"distortionCorrectedPointsColor"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor cyanColor] requiringSecureCoding:FALSE error:nil] forKey:@"distortionCorrectedLinesColor"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor yellowColor] requiringSecureCoding:FALSE error:nil] forKey:@"distortionCenterColor"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor redColor] requiringSecureCoding:FALSE error:nil] forKey:@"distortionPointsColor"];
	
	// initial values for automatic plumbline detection algorithm for distortion correction
	// "Lattice" = saddle-point detection with lattice assembly, the default, which takes no
	// settings. "Legacy" = the goodFeaturesToTrack and nearest-neighbor walk used since 2009,
	// kept selectable because it is what every calibration before this was built with. The
	// chessboardDetection* settings below apply only to Legacy.
	[initialValueDict setObject:@"Lattice" forKey:@"plumblineDetectionMethod"];
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
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor cyanColor] requiringSecureCoding:FALSE error:nil] forKey:@"pixelErrorLineColor"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor orangeColor] requiringSecureCoding:FALSE error:nil] forKey:@"pixelErrorPointColor"];
	
	// initial values for the appearance of the point selection indicator
	[initialValueDict setObject:[NSNumber numberWithFloat:20.0] forKey:@"pointSelectionIndicatorLineLength"];
	[initialValueDict setObject:[NSNumber numberWithFloat:3.0] forKey:@"pointSelectionIndicatorLineWidth"];
	[initialValueDict setObject:[NSNumber numberWithFloat:1.5] forKey:@"pointSelectionIndicatorSizeFactor"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor yellowColor] requiringSecureCoding:FALSE error:nil] forKey:@"pointSelectionIndicatorColor"];
	[initialValueDict setObject:[NSNumber numberWithFloat:0.3] forKey:@"selectedPointNudgeDistance"];
	
	// initial values for annotation visual settings
	
	[initialValueDict setObject:[NSNumber numberWithBool:FALSE] forKey:@"newAnnotationAppendTimer"];
	[initialValueDict setObject:[NSNumber numberWithInt:5] forKey:@"newAnnotationDuration"];
	[initialValueDict setObject:[NSNumber numberWithInt:3] forKey:@"newAnnotationFadeTime"];
	[initialValueDict setObject:[NSNumber numberWithInt:30] forKey:@"newAnnotationFontSize"];
	[initialValueDict setObject:[NSNumber numberWithInt:400] forKey:@"newAnnotationWidth"];
	[initialValueDict setObject:@"Arial" forKey:@"newAnnotationFontFace"];
	[initialValueDict setObject:[NSKeyedArchiver archivedDataWithRootObject:[NSColor orangeColor] requiringSecureCoding:FALSE error:nil] forKey:@"newAnnotationColor"];
	
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
	NSAlert *alert = [[NSAlert alloc] init];
	[alert setMessageText:@"Are ou sure?"];
	[alert setInformativeText:@"Are you sure you want to restore all preferences to their initial values?"];
	[alert addButtonWithTitle:@"Yes"];
	[alert addButtonWithTitle:@"No"];
	[alert setAlertStyle:NSAlertStyleWarning];
	NSModalResponse nudgeWarningResult = [alert runModal];
	if (nudgeWarningResult == NSAlertFirstButtonReturn) {
		[[NSUserDefaultsController sharedUserDefaultsController] revertToInitialValues:sender];
	}
}

@end
