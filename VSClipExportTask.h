/*********************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2026 Jason Neuswanger
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
#import <AVFoundation/AVFoundation.h>

@class VSVideoClip;

// One queued video export: a single clip over the capture tab's time range, with or without
// overlays burned in. The descriptor deliberately carries everything the exporter needs as plain
// values (master time range, an optional crop rect) rather than reading them back from live UI
// state, so the execution engine never touches the interface mid-export.

typedef NS_ENUM(NSInteger, VSClipExportTaskType) {
	VSClipExportTaskTypePlainClip = 0,		// straight copy of the source video, no overlay (AVAssetExportSession)
	VSClipExportTaskTypeOverlayClip = 1,	// re-rendered frame by frame with the annotation overlay burned in
};

typedef NS_ENUM(NSInteger, VSClipExportTaskStatus) {
	VSClipExportTaskStatusQueued = 0,
	VSClipExportTaskStatusRunning,
	VSClipExportTaskStatusFinished,
	VSClipExportTaskStatusFailed,
	VSClipExportTaskStatusCancelled,
};

@interface VSClipExportTask : NSObject

@property (assign) VSClipExportTaskType type;
@property (weak) VSVideoClip *videoClip;
@property (copy) NSString *displayName;			// survives for the progress window even if the clip goes away
@property (copy) NSString *outputPath;
@property (assign) CMTime startMasterTime;
@property (assign) CMTime endMasterTime;
@property (assign) NSRect cropRect;				// in video pixels; NSZeroRect means the full frame (reserved for the future export window)

@property (assign) BOOL includeSound;
@property (assign) BOOL useHEVC;				// NO = H.264 (universal default)

@property (assign) VSClipExportTaskStatus status;	// main thread only
@property (copy) NSString *statusMessage;			// main thread only
@property (strong) NSError *error;					// main thread only
@property (assign) double progress;					// 0..1; atomic so the worker can set it and the UI timer can read it
@property (assign) BOOL cancelRequested;			// atomic; set from the UI, polled by the worker

+ (VSClipExportTask *) taskWithType:(VSClipExportTaskType)type
						  videoClip:(VSVideoClip *)videoClip
						 outputPath:(NSString *)outputPath
					startMasterTime:(CMTime)startMasterTime
					  endMasterTime:(CMTime)endMasterTime;

- (BOOL) isActive;		// queued or running
- (NSString *) localizedStatusDescription;

@end
