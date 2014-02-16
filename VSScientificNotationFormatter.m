//
//  VSScientificNotationFormatter.m
//  VidSync
//
//  Created by Jason Neuswanger on 3/21/12.
//  Copyright (c) 2012 Jason Neuswanger. All rights reserved.
//

//  This is a scientific notation number formatter subclass, used currently only for displaying distortion parameters k1, k2, and k3

#import "VSScientificNotationFormatter.h"

@implementation VSScientificNotationFormatter

- (void) awakeFromNib
{
    [self setFormatterBehavior:NSNumberFormatterBehavior10_4];
    [self setNumberStyle:NSNumberFormatterScientificStyle];
    [self setUsesSignificantDigits:YES];
    [self setMaximumSignificantDigits:3];
    [self setMinimumSignificantDigits:3];
    [self setPositivePrefix:@" "];
}

@end
