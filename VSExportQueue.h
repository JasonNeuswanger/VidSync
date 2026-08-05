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
#import "VSClipExportTask.h"

@class VidSyncDocument;
@class VSExportQueueWindowController;

// The document's video export queue. Tasks can be enqueued at any time, including while others are
// running; they execute one at a time so a long overlay render doesn't fight a second export for
// decode bandwidth. All exports run without blocking the main thread or program use:
//
//   - Plain (no-overlay) exports use AVAssetExportSession's own asynchronous machinery.
//   - Overlay exports decode the source sequentially with an AVAssetReader on a background queue,
//     hop briefly to the main thread once per frame to render the annotation overlay offscreen at
//     the export timecode (the video windows never move), then composite and encode back on the
//     background queue through an AVAssetWriter. The source's audio (if any) rides along on its own
//     queue, passed through untouched when MP4 can hold it or re-encoded as AAC when it can't.
//
// The queue owns the progress window (one row and progress bar per task). Everything here that
// touches a task's status/statusMessage or the tasks array happens on the main thread; workers
// communicate through the atomic progress/cancelRequested properties and main-queue dispatches.

@interface VSExportQueue : NSObject

@property (weak, readonly) VidSyncDocument *document;
@property (strong, readonly) NSMutableArray *tasks;   // VSClipExportTask, in enqueue order; main thread only
@property (strong, readonly) VSExportQueueWindowController *windowController;

- (instancetype) initWithDocument:(VidSyncDocument *)document;

- (void) enqueueTask:(VSClipExportTask *)task;	// shows the progress window and starts the task when its turn comes
- (void) cancelTask:(VSClipExportTask *)task;
- (void) cancelAllActiveTasks;					// used when the document is closing with exports still queued or running
- (void) clearInactiveTasks;
- (void) showWindow;
- (BOOL) hasActiveTasks;

// Rotation-flagged source video (vertical phone clips, 180-degree mounts): both frame pipelines
// decode storage-orientation buffers and must normalize them to display orientation before
// compositing. Shared by the overlay pipeline here and the advanced pipeline in its category.
// Returns a vImage rotate constant (kRotate0/90/180/270DegreesClockwise), or 255 for a transform
// that isn't a pure 90-degree-multiple rotation (flips/skews), which the pipelines refuse cleanly.
+ (uint8_t) rotationConstantForPreferredTransform:(CGAffineTransform)transform;
// Rotates source into destination (both 32BGRA, both already locked, destination sized for the
// rotated output). Returns NO on a vImage error.
+ (BOOL) rotatePixelBuffer:(CVPixelBufferRef)source into:(CVPixelBufferRef)destination withRotationConstant:(uint8_t)rotationConstant;

// For the export pipelines only (including the advanced pipeline in its category file), not for
// callers: every started task must funnel through exactly one of these, on the main thread.
- (void) finishTask:(VSClipExportTask *)task withStatus:(VSClipExportTaskStatus)status error:(NSError *)error;
- (void) failTask:(VSClipExportTask *)task withMessage:(NSString *)message;

@end

