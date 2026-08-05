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

#import "VSClipExportTask.h"
#import "VidSyncDocument.h"

@implementation VSClipExportTask

+ (VSClipExportTask *) taskWithType:(VSClipExportTaskType)type
						  videoClip:(VSVideoClip *)videoClip
						 outputPath:(NSString *)outputPath
					startMasterTime:(CMTime)startMasterTime
					  endMasterTime:(CMTime)endMasterTime
{
	VSClipExportTask *task = [VSClipExportTask new];
	task.type = type;
	task.videoClip = videoClip;
	task.displayName = videoClip.clipName;
	task.outputPath = outputPath;
	task.startMasterTime = startMasterTime;
	task.endMasterTime = endMasterTime;
	task.cropRect = NSZeroRect;
	task.status = VSClipExportTaskStatusQueued;
	task.statusMessage = @"Waiting in queue";
	task.progress = 0.0;
	return task;
}

- (BOOL) isActive
{
	return (self.status == VSClipExportTaskStatusQueued || self.status == VSClipExportTaskStatusRunning);
}

- (NSString *) localizedStatusDescription
{
	switch (self.status) {
		case VSClipExportTaskStatusQueued:		return @"Queued";
		case VSClipExportTaskStatusRunning:		return @"Exporting";
		case VSClipExportTaskStatusFinished:	return @"Finished";
		case VSClipExportTaskStatusFailed:		return @"Failed";
		case VSClipExportTaskStatusCancelled:	return @"Cancelled";
	}
	return @"";
}

@end
