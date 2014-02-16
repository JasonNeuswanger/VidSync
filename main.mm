//
//  main.m
//  VidSync
//
//  Created by Jason Neuswanger on 10/22/09.
//  Copyright University of Alaska Fairbanks 2009 . All rights reserved.
//

#import <Cocoa/Cocoa.h>

int main(int argc, char *argv[])
{
	
    @autoreleasepool {
        [VidSyncDocument setUserDefaultsInitialValues];	// placed the call here, based on this: http://www.cocoabuilder.com/archive/cocoa/181530-dumb-bindings-user-defaults-question.html        
    }
	
    int retVal = 0;
    @try {
        retVal = NSApplicationMain(argc, (const char **) argv);
    }
    @catch (NSException *exception) {
        NSLog(@"Exception in main.mm: %@",[exception description]);
        exit(EXIT_FAILURE);
    }
    return retVal;
}
