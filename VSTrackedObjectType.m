/*********************************************************************************                                                                       
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2021 Jason Neuswanger
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


#import "VSTrackedObjectType.h"


@implementation VSTrackedObjectType

@dynamic name;
@dynamic project;
@dynamic trackedObjects;

- (void)awakeFromFetch
{
	// Observe the value of name, so the array controller can re-sort itself when a name is changed.
	[self addObserver:self forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	[super awakeFromFetch];
}

- (void)awakeFromInsert
{
	// Observe the value of name, so the array controller can re-sort itself when a name is changed.
	[self addObserver:self forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	[super awakeFromInsert];
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
	if ([keyPath isEqualToString:@"name"]) {
		[self.project.document.trackedObjectTypesController rearrangeObjects];
	}
}

+ (VSTrackedObjectType *) insertNewTypeFromLoadedDictionary:(NSDictionary *)objectTypeDictionary withName:(NSString *)name inProject:(VSProject *)project inManagedObjectContext:(NSManagedObjectContext *)moc
{
	VSTrackedObjectType *newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObjectType" inManagedObjectContext:moc];
	newType.project = project;
	newType.name = name;
	[newType updatePropertiesFromLoadedDictionary:objectTypeDictionary];
	return newType;
}

- (NSMutableDictionary *) contentsAsWriteableDictionary
{
	NSMutableDictionary *superDict = [super contentsAsWriteableDictionary];
	[superDict setObject:self.name forKey:@"name"];
	return superDict;
}

- (void) dealloc
{
	@try {
		[self removeObserver:self forKeyPath:@"name"];
	} @catch (id exception) {
	}
}

@end
