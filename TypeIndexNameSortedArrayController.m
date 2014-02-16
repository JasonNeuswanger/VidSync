//
//  TypeIndexNameSortedArrayController.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/5/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

#import "TypeIndexNameSortedArrayController.h"


@implementation TypeIndexNameSortedArrayController

- (void) awakeFromNib
{
	NSSortDescriptor *typeDescriptor = [[NSSortDescriptor alloc] initWithKey:@"type.name" ascending:YES];
	NSSortDescriptor *indexDescriptor = [[NSSortDescriptor alloc] initWithKey:@"index" ascending:YES];
	NSSortDescriptor *nameDescriptor = [[NSSortDescriptor alloc] initWithKey:@"name" ascending:YES];
	[self setSortDescriptors:[NSArray arrayWithObjects:typeDescriptor,indexDescriptor,nameDescriptor,nil]];
	[super awakeFromNib];
}


- (IBAction) reSort:(id)sender
{
	[self rearrangeObjects];
}

@end
