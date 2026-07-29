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

#import <Foundation/Foundation.h>

/*
 Which tab is showing, and which filter a table or overlay is using, is a property of one project
 window rather than of the application. These four settings were bound to the shared user defaults
 controller, which gave every open document a single shared value: switching a tab in one project
 switched it in the others, and worse, changing a filter in one project silently changed what the
 other project's events table and video overlays displayed.

 Each property here is seeded from the value the user last left behind and writes back there as it
 changes, so a newly opened document still starts where the previous one left off. Nothing reads
 back after initialization, so documents that are open at the same time stay independent.

 The defaults keys are unchanged, so existing preferences carry over. Settings that genuinely are
 application-wide -- the magnified preview appearance, the portrait browser zooms, hint lines, the
 plumbline detection method, chessboard parameters, export and capture naming -- deliberately stay
 bound to the shared controller.
 */

@interface VSDocumentViewState : NSObject

@property (strong) NSString *mainTabViewSelectedLabel;
@property (assign) NSInteger objectEditWindowSelectedTabIndex;
@property (strong) NSString *selectedEventsPointsTimeFilter;
@property (assign) NSInteger showDistortionLinesFromWhichTimecodes;

// Set once the document's nib has finished loading. Until then, changes stay in memory instead of
// being written back as the remembered value.
@property (assign) BOOL persistsChangesToUserDefaults;

@end
