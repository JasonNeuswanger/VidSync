//
//  VSTrackedObjectType.m
//  VidSync
//
//  Created by Jason Neuswanger on 11/20/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import "VSTrackedObjectType.h"


@implementation VSTrackedObjectType

@dynamic name;
@dynamic project;

- (void)awakeFromFetch
{
	// Observe the value of name, so the array controller can re-sort itself when a name is changed.
	[self addObserver:self forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	[super awakeFromFetch];
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
	if ([keyPath isEqualToString:@"name"]) {
		[self.project.document.trackedObjectTypesController rearrangeObjects];
	}
}
		 

+ (void) insertNewTypeFromLoadedDictionary:(NSDictionary *)objectTypeDictionary inProject:(VSProject *)project inManagedObjectContext:(NSManagedObjectContext *)moc
{
	VSTrackedObjectType *newType = nil;
	for (VSTrackedObjectType *oldType in project.trackedObjectTypes) {
		if ([oldType.name isEqualToString:[objectTypeDictionary objectForKey:@"name"]]) {		// If a type exists with the same name as the one being imported, overwrite it.
			newType = oldType;
		}
	}
	if (newType == nil) newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObjectType" inManagedObjectContext:moc];
	[newType addObserver:newType forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	newType.project = project;
	newType.name = [objectTypeDictionary objectForKey:@"name"];
	[newType setVisibleItemPropertiesFromDictionary:objectTypeDictionary];	
}

- (NSMutableDictionary *) contentsAsWriteableDictionary
{
	NSMutableDictionary *superDict = [super contentsAsWriteableDictionary];
	[superDict setObject:self.name forKey:@"name"];
	return superDict;
}



@end
