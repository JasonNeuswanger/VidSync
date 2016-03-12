/*********************************************************************************                                                                       
 * The MIT License (MIT)
 * 
 * Copyright (c) 2009-2016 Jason Neuswanger
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


#import "TypesArrayController.h"


@implementation TypesArrayController

- (IBAction) add:(id)sender
{
	if ([sender tag] == 1) {		// It's a new object type.
		VSTrackedObjectType *newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObjectType" inManagedObjectContext:[self managedObjectContext]];	
		newType.name = [newTypeName stringValue];
		newType.notes = [newTypeDescription stringValue];
		[self addObject:newType];	// Adds the object type to the project
		[newType addObserver:newType forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	} else {						// It's a new event type.
		VSTrackedEventType *newType = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedEventType" inManagedObjectContext:[self managedObjectContext]];	
		newType.name = [newTypeName stringValue];
		newType.notes = [newTypeDescription stringValue];
		[self addObject:newType];	// Adds the event type to the project
		[newType addObserver:newType forKeyPath:@"name" options:NSKeyValueObservingOptionNew context:NULL];
	}
	[self rearrangeObjects];
	[inputPanel performClose:self];
	[newTypeName setStringValue:@""];
	[newTypeDescription setStringValue:@""];
}

- (void) rearrangeObjects
{
	[super rearrangeObjects];
}

@end
