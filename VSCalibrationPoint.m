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


#import "VSCalibrationPoint.h"


@implementation VSCalibrationPoint

@dynamic screenX;
@dynamic screenY;
@dynamic worldHcoord;
@dynamic worldVcoord;
@dynamic index;
@dynamic calibration;

@synthesize apparentWorldHcoord;
@synthesize apparentWorldVcoord;

- (NSXMLNode *) representationAsXMLNode
{
	NSNumberFormatter *nf = self.calibration.videoClip.project.document.decimalFormatter;
    NSPoint screenPoint = NSMakePoint([self.screenX floatValue],[self.screenY floatValue]);
    NSPoint undistortedScreenPoint = [self.calibration undistortPoint:screenPoint];
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"screenpoint"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"x" stringValue:[nf stringFromNumber:self.screenX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"y" stringValue:[nf stringFromNumber:self.screenY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"xu" stringValue:[nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.x]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"yu" stringValue:[nf stringFromNumber:[NSNumber numberWithFloat:undistortedScreenPoint.y]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"worldHcoord" stringValue:[nf stringFromNumber:self.worldHcoord]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"worldVcoord" stringValue:[nf stringFromNumber:self.worldVcoord]]];    
	return mainElement;
}

@end
