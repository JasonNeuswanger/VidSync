//
//  VSVisibleItem.h
//  VidSync
//
//  Created by Jason Neuswanger on 11/20/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSVisibleItem : NSManagedObject {   
    
}

@property (strong) NSColor *color;
@property (strong) NSString *notes;
@property (strong) NSNumber *duration;
@property (strong) NSNumber *fadeTime;
@property (strong) NSString *shape;
@property (strong) NSNumber *size;

- (NSMutableDictionary *) contentsAsWriteableDictionary;
- (void) setVisibleItemPropertiesFromDictionary:(NSDictionary *)typeDictionary;

@end
