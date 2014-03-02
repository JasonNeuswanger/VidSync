//
//  AppDelegate.h
//  VidSync
//
//  Created by Jason Neuswanger on 3/1/14.
//  Copyright (c) 2014 Jason Neuswanger. All rights reserved.
//

#import <Foundation/Foundation.h>

@interface AppDelegate : NSObject {
    
}

+ (void)initialize;
+ (NSMutableDictionary *) userDefaultsInitialValues;
+ (void) setUserDefaultsInitialValues;

- (NSError*) application:(NSApplication*)application willPresentError:(NSError*)error;

@end
