//
//  VSTrackedObjectType.h
//  VidSync
//
//  Created by Jason Neuswanger on 11/20/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSTrackedObjectType : VSVisibleItem {
	
}

@property (strong) NSString *name;
@property (strong) VSProject *project;

+ (void) insertNewTypeFromLoadedDictionary:(NSDictionary *)objectTypeDictionary inProject:(VSProject *)project inManagedObjectContext:(NSManagedObjectContext *)moc;

- (void)awakeFromFetch;

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context;

@end
