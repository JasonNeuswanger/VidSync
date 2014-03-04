//
//  VSAnnotationArrayController.h
//  VidSync
//
//  Created by Jason Neuswanger on 4/1/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSAnnotationArrayController : VSVisibleItemArrayController
{

	IBOutlet VidSyncDocument *__weak document;
	
}

- (IBAction) goToAnnotation:(id)sender;

- (IBAction) mirrorSelectedAnnotation:(id)sender;

@end
