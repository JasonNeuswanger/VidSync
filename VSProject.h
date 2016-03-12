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
@class VidSyncDocument;

@interface VSProject : NSManagedObject {
    
	VidSyncDocument *__weak document;

}

@property (strong) NSString *name;
@property (strong) NSString *notes;
@property (strong) NSString *currentTimecode;
@property (strong) NSString *calibrationTimecode;
@property (strong) NSString *dateCreated;
@property (strong) NSString *dateLastSaved;
@property (strong) VSVideoClip *masterClip;
@property (strong) NSMutableSet *videoClips;

@property (strong) NSNumber *useIterativeTriangulation;

@property (strong) NSString *exportPathForData;
@property (strong) NSNumber *exportClipSelectedClipName;
@property (strong) NSString *capturePathForMovies;
@property (strong) NSString *capturePathForStills;
@property (strong) NSString *movieCaptureStartTime;
@property (strong) NSString *movieCaptureEndTime;
@property (strong) NSString *distortionDisplayMode;

@property (weak) VidSyncDocument *document;
@property (strong) NSMutableSet *trackedObjectTypes;
@property (strong) NSMutableSet *trackedEventTypes;
@property (strong) NSMutableSet *trackedObjects;
@property (strong) NSMutableSet *trackedEvents;

- (NSDate *) dateCreatedAsNSDate;
- (NSDate *) dateLastSavedAsNSDate;

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath;

@end
