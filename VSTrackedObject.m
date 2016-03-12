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


#import "VSTrackedObject.h"


@implementation VSTrackedObject

@dynamic index;
@dynamic observer;
@dynamic name;
@dynamic type;
@dynamic project;
@dynamic trackedEvents;
@dynamic portraits;

+ (int) highestObjectIndexInProject:(VSProject *)project
{
	int highestIndex = 0;
	for (VSTrackedObject *object in project.trackedObjects) if ([object.index intValue] > highestIndex) highestIndex = [object.index intValue]; 
	return highestIndex;
}

- (void)awakeFromFetch
{
	[self addObserver:self forKeyPath:@"color" options:0 context:NULL];
	[super awakeFromFetch];
}

- (void)awakeFromInsert
{
	[self addObserver:self forKeyPath:@"color" options:0 context:NULL];
	[super awakeFromFetch];
}

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context
{
	if ([keyPath isEqualToString:@"color"]) {
        if (self.project.document != nil) [self.project.document refreshOverlaysOfAllClips:self];
	}
}

- (NSNumber *) numEvents
{
	return [NSNumber numberWithInt:[self.trackedEvents count]];
}

- (NSAttributedString *) tableGlyphForColor
{
    NSMutableAttributedString *glyph = [[NSMutableAttributedString alloc] initWithString:@"\uf0c8"];
    NSRange glyphRange = NSMakeRange(0, [glyph length]);
    [glyph addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:9.0f] range:glyphRange];
    return glyph;
}

- (NSAttributedString *) tableGlyphForPortrait
{
    NSMutableAttributedString *glyph;
    if ([self.portraits count] > 0) {
        glyph =  [[NSMutableAttributedString alloc] initWithString:@"\uf030"];
    } else {
        glyph =  [[NSMutableAttributedString alloc] initWithString:@" "];
    }
    
    NSRange glyphRange = NSMakeRange(0, [glyph length]);
    [glyph addAttribute:NSFontAttributeName value:[NSFont fontWithName:@"FontAwesome" size:9.0f] range:glyphRange];
    
    return glyph;
}

+ (NSSet *)keyPathsForValuesAffectingNumEvents
{
	return [NSSet setWithObjects:@"trackedEvents", nil];
}

- (void)prepareForDeletion
{
	for (VSTrackedEvent *event in self.trackedEvents) {
		if ([event.trackedObjects count] == 1) {
			[[self managedObjectContext] deleteObject:event];	// delete events that are associated with this object & not with any other objects
		}
	}
}

- (NSXMLNode *) representationAsXMLNode
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"object"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"type" stringValue:self.type.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"index" stringValue:[self.index stringValue]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"colorR" stringValue:[NSString stringWithFormat:@"%1.4f",[self.color redComponent]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"colorG" stringValue:[NSString stringWithFormat:@"%1.4f",[self.color greenComponent]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"colorB" stringValue:[NSString stringWithFormat:@"%1.4f",[self.color blueComponent]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"notes" stringValue:self.notes]];
    [mainElement addAttribute:[NSXMLNode attributeWithName:@"observer" stringValue:self.observer]];
	for (VSTrackedEvent *trackedEvent in self.trackedEvents) [mainElement addChild:[trackedEvent representationAsXMLNode]];
	return mainElement;
}

- (NSXMLNode *) representationAsXMLChildOfEvent
{
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"objectChildOfEvent"];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"type" stringValue:self.type.name]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"index" stringValue:[self.index stringValue]]];
	return mainElement;	
}

- (void) split	
{
	// splits the object's event around the current timecode, placing all events with a later timecode into a new and otherwise identical object
	// events that have no point with a timecode stay with the current object (e.g. they're ignored)
	// events with points on either side of the current timecode (a very rare case probably) get moved depending on what anyObject randomly chooses
	// if the point is right AT the current timecode, it stays with the original object
	
	VSTrackedObject *newObj = [NSEntityDescription insertNewObjectForEntityForName:@"VSTrackedObject" inManagedObjectContext:[self managedObjectContext]];	
	newObj.name = [NSString stringWithFormat:@"%@_split",self.name];
	newObj.type = self.type;
	newObj.color = self.color;
	newObj.index = [NSNumber numberWithInt:[VSTrackedObject highestObjectIndexInProject:self.project]+1];
    newObj.observer = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"currentObserverName"];
	
	
	NSMutableSet *eventsObjects;
	CMTime currentTime = [self.project.document currentMasterTime];
	CMTime eventTime;
	NSArray *allEvents = [self.trackedEvents allObjects];
	VSTrackedEvent *event;
	for (int i = 0; i < [allEvents count]; i++) {
		event = [allEvents objectAtIndex:i];
		if ([event.points count] > 0) {
			eventTime = [UtilityFunctions CMTimeFromString:[[event.points anyObject] timecode]];
			if (CMTimeCompare(eventTime,currentTime) == NSOrderedDescending) {
				eventsObjects = [NSMutableSet setWithSet:event.trackedObjects];
				[eventsObjects addObject:newObj];
				[eventsObjects removeObject:self];
				event.trackedObjects = eventsObjects;
			}
		}
	}
	
	newObj.project = self.project;
}

- (void) dealloc
{
    @try {
        [self removeObserver:self forKeyPath:@"color"];
    } @catch (id exception) {
    }
}

@end
