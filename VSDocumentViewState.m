/*********************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2026 Jason Neuswanger
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

#import "VSDocumentViewState.h"

// The keys these settings were bound to before they became per-document, kept as they were so that
// preferences saved by earlier versions carry over.
static NSString * const VSMainTabViewSelectedLabelKey = @"latestMainTabViewSelectedLabel";
static NSString * const VSObjectEditWindowSelectedTabIndexKey = @"ObjectEditWindowSelectedTabIndex";
static NSString * const VSSelectedEventsPointsTimeFilterKey = @"selectedEventsPointsTimeFilter";
static NSString * const VSShowDistortionLinesFromWhichTimecodesKey = @"showDistortionLinesFromWhichTimecodes";

@implementation VSDocumentViewState

- (instancetype) init
{
	self = [super init];
	if (self != nil) {
		// Read through the shared controller rather than NSUserDefaults directly. AppDelegate registers
		// the app's starting values as the controller's initialValues, which NSUserDefaults itself never
		// sees, so a key the user has never touched reads as nil straight from the defaults.
		id defaultValues = [[NSUserDefaultsController sharedUserDefaultsController] values];
		_mainTabViewSelectedLabel = [defaultValues valueForKey:VSMainTabViewSelectedLabelKey];
		_objectEditWindowSelectedTabIndex = [[defaultValues valueForKey:VSObjectEditWindowSelectedTabIndexKey] integerValue];
		_selectedEventsPointsTimeFilter = [defaultValues valueForKey:VSSelectedEventsPointsTimeFilterKey];
		_showDistortionLinesFromWhichTimecodes = [[defaultValues valueForKey:VSShowDistortionLinesFromWhichTimecodesKey] integerValue];
	}
	return self;
}

- (void) rememberValue:(id)value forKey:(NSString *)key
{
	if (!self.persistsChangesToUserDefaults || value == nil) return;
	[[[NSUserDefaultsController sharedUserDefaultsController] values] setValue:value forKey:key];
}

- (void) setMainTabViewSelectedLabel:(NSString *)mainTabViewSelectedLabel
{
	_mainTabViewSelectedLabel = mainTabViewSelectedLabel;
	[self rememberValue:mainTabViewSelectedLabel forKey:VSMainTabViewSelectedLabelKey];
}

- (void) setObjectEditWindowSelectedTabIndex:(NSInteger)objectEditWindowSelectedTabIndex
{
	_objectEditWindowSelectedTabIndex = objectEditWindowSelectedTabIndex;
	[self rememberValue:[NSNumber numberWithInteger:objectEditWindowSelectedTabIndex] forKey:VSObjectEditWindowSelectedTabIndexKey];
}

- (void) setSelectedEventsPointsTimeFilter:(NSString *)selectedEventsPointsTimeFilter
{
	_selectedEventsPointsTimeFilter = selectedEventsPointsTimeFilter;
	[self rememberValue:selectedEventsPointsTimeFilter forKey:VSSelectedEventsPointsTimeFilterKey];
}

- (void) setShowDistortionLinesFromWhichTimecodes:(NSInteger)showDistortionLinesFromWhichTimecodes
{
	_showDistortionLinesFromWhichTimecodes = showDistortionLinesFromWhichTimecodes;
	[self rememberValue:[NSNumber numberWithInteger:showDistortionLinesFromWhichTimecodes] forKey:VSShowDistortionLinesFromWhichTimecodesKey];
}

@end
