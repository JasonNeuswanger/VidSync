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

@class VideoControlButton;
@class BookmarkControlButton;
@class PlayWhilePressedButton;
@class VidSyncDocument;

@interface SyncedPlaybackView : NSView {
    
    IBOutlet VideoControlButton __weak *playOrPauseButton;
    IBOutlet VideoControlButton __weak *stepForwardButton;
    IBOutlet VideoControlButton __weak *stepBackwardButton;
    IBOutlet VideoControlButton __weak *playBackwardButton;
    IBOutlet VideoControlButton __weak *bookmarkSetButton1;
    IBOutlet VideoControlButton __weak *bookmarkSetButton2;
    IBOutlet VideoControlButton __weak *bookmarkGoButton1;
    IBOutlet VideoControlButton __weak *bookmarkGoButton2;
    IBOutlet VideoControlButton __weak *instantReplayButton;
    
    IBOutlet VideoControlButton __weak *maximizeButton;

    IBOutlet PlayWhilePressedButton __weak *mainPlayForwardWhilePressedButton;
    IBOutlet PlayWhilePressedButton __weak *mainPlayBackwardWhilePressedButton;
    
    IBOutlet VidSyncDocument __weak *document;
    
}

@end
