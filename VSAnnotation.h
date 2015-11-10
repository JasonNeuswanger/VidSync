//
//  VSAnnotation.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/30/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSAnnotation : VSVisibleItem {

	float tempOpacity;

}

@property (strong) VSVideoClip *videoClip;
@property (strong) NSString *observer;
@property (strong) NSNumber *screenX;
@property (strong) NSNumber *screenY;
@property (strong) NSString *startTimecode;
@property (strong) NSNumber *width;
@property (strong) NSNumber *appendsTimer;
@property (assign) float tempOpacity;


- (NSAttributedString *) tableGlyphForColor;

- (NSXMLNode *) representationAsXMLNode;

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath;

@end
