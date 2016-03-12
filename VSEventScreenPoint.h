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


#import <Cocoa/Cocoa.h>
@class VSVideoClip;
@class VSPoint;

NSPoint quadratCoords2Dfrom3D(const VSPoint3D *quadratCoords3D, const char axisHorizontal, const char axisVertical);

@interface VSEventScreenPoint : NSManagedObject {
    
    CMTimeRange totalTimeRange, fadingTimeRange;
    CMTime fadingStartTime, fadingDuration;
	
}

@property (strong) NSNumber *screenX;
@property (strong) NSNumber *screenY;
@property (strong) NSNumber *frontFrameWorldH;
@property (strong) NSNumber *frontFrameWorldV;
@property (strong) NSNumber *backFrameWorldH;
@property (strong) NSNumber *backFrameWorldV;
@property (strong) VSVideoClip *videoClip;
@property (strong) VSPoint *point;
@property (strong) NSSet *screenPoints;
@property (strong) NSSet *hintLinesOut;
@property (assign) float tempOpacity;
@property (assign) CMTimeRange totalTimeRange;
@property (assign) CMTimeRange fadingTimeRange;
@property (assign) CMTime fadingStartTime;
@property (assign) CMTime fadingDuration;

- (void) updateVisibleTimeRange;
- (void) updateCalibrationFrameCoords;
- (VSLine3D) computeLine3D:(BOOL)useReprojectedPoints;
- (void) calculateHintLines;
- (void) putPointsInFrontQuadratPlaneIntoArray:(VSPoint3D[3])quadratPlanePoints;
- (NSPoint) reprojectedScreenPoint:(bool)shouldRedistort;
- (NSString *) spreadsheetFormattedScreenPoint;
- (NSXMLNode *) representationAsXMLNode;
- (NSPoint) undistortedCoords;
- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath;

@end
