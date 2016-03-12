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


#import "VSTrackedObjectPortrait.h"

@implementation VSTrackedObjectPortrait

@dynamic timecode;
@dynamic imageData;
@dynamic trackedObject;
@dynamic sourceVideoClip;
@dynamic frameString;

- (void) setImage:(NSImage *)imageSource
{
    self.imageData = [imageSource TIFFRepresentationUsingCompression:NSTIFFCompressionJPEG factor:0.6f];
}

#pragma mark
#pragma mark IKImageBrowserItem informal protocol conformation methods
// Note: IKImageBrowserItem is an INFORMAL protocol, not defined in any headers, so I don't have to declare this class as conforming to the protocol

- (NSString *) imageUID
{
    return [NSString stringWithFormat:@"Object %@ portrait from %@ in %@ at %@",self.trackedObject.index,self.sourceVideoClip.clipName,self.frameString,self.timecode];
}

- (NSString *) imageTitle
{
    return [self imageUID];
}

- (NSString *) imageRepresentationType
{
    return IKImageBrowserNSImageRepresentationType;
}

- (id) imageRepresentation
{
    if (image == nil) {
        image = [[NSImage alloc] initWithData:self.imageData];
        return image;
        
    } else {
        return image;
    }
}

- (BOOL) isSelectable
{
    return YES;
}

@end
