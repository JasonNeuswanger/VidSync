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


#import "VidSyncDocument.h"

// Version of the structure of the exported files, recorded in every export so a consumer can tell which
// generation of the format it is reading. Bump this on any structural change: a new or removed column,
// a renamed or removed XML attribute or element, or a change in what an existing field means.
static const NSInteger VSExportFormatVersion = 3;

#pragma mark - JSON, derived from the XML

// The JSON export is not a second serializer. It is a mechanical transform of the very same NSXMLDocument the XML
// export writes, so the two cannot describe different things and adding an attribute to the XML adds it to the JSON
// with no second edit. Nothing here knows the name of any element: the whole converter is the four rules below.
//
//   1. An element becomes an object. The document becomes {"project": {...}}, so the root tag is not lost.
//   2. Attributes become keys of that object.
//   3. Child elements are grouped by tag name into arrays -- always arrays, even for a single child. This is the rule
//      that does the real work. A consumer never has to handle "an object, or a list of objects, depending on the
//      data", which is the classic trap in XML-derived JSON, and it means an element that happens to occur once in
//      one project and twice in another does not change the shape of the document.
//   4. An element with text and no child elements puts its text under "text". Only the calibration frame node lists use this.
//
// Values are typed by the table below, keyed on attribute name. An empty string becomes null, so "not computed" is
// explicit rather than an empty string that a consumer has to recognize. An attribute missing from the table is
// carried through as a string and logged: a new attribute can therefore be untyped in the JSON, but it can never be
// silently absent from it.
//
// One deliberate limitation: numbers become JSON numbers, which every JSON stack in practice reads as doubles, while
// the XML strings keep every digit VidSync wrote -- and the calibration formatter writes fifty fraction digits so
// that the higher-order distortion terms survive. Beyond about seventeen significant digits the JSON is therefore the
// lossier of the two files. Anyone who needs those digits exactly wants the XML.

typedef NS_ENUM(NSInteger, VSExportValueType) {
	VSExportValueTypeString,
	VSExportValueTypeNumber,
	VSExportValueTypeBool,
	VSExportValueTypeMatrix
};

@interface VSExportJSON : NSObject
+ (NSDictionary *) JSONObjectFromXMLDocument:(NSXMLDocument *)xmlDoc;
@end

@implementation VSExportJSON

+ (NSDictionary *) attributeTypes
{
	// Keyed on attribute name alone rather than element-and-attribute, because no name in this format means two
	// different things in two elements: index is a number everywhere, name and type are strings everywhere, and the
	// videoClip attribute of a screen point is a clip name. If that ever stops being true, this table has to grow a
	// level. Anything not listed is a string.
	static NSDictionary *types = nil;
	static dispatch_once_t onceToken;
	dispatch_once(&onceToken, ^{
		NSArray *numbers = @[@"index", @"colorR", @"colorG", @"colorB",
							 @"x", @"y", @"z", @"xu", @"yu", @"time",
							 @"screenX", @"screenY",
							 @"meanPLD", @"reprojectionErrorNorm", @"nearestCameraDistance", @"numViews",
							 @"frameFrontH", @"frameFrontV", @"frameBackH", @"frameBackV",
							 @"reprojectedX", @"reprojectedY", @"residualPixels",
							 @"worldHcoord", @"worldVcoord",
							 @"timeScale", @"frameRate", @"clipWidth", @"clipHeight",
							 @"cameraX", @"cameraY", @"cameraZ", @"cameraMeanPLD",
							 @"distortionCenterX", @"distortionCenterY",
							 @"distortionK1", @"distortionK2", @"distortionK3", @"distortionK4",
							 @"distortionK5", @"distortionK6", @"distortionK7",
							 @"distortionP1", @"distortionP2", @"distortionP3", @"distortionP4",
							 @"distortionReductionAchieved", @"distortionRemainingPerPoint",
							 @"residualFrontLeastSquares", @"residualBackLeastSquares",
							 @"residualFrontPixel", @"residualBackPixel",
							 @"residualFrontWorld", @"residualBackWorld",
							 @"planeCoordFront", @"planeCoordBack",
							 @"frontCalibrationFrameSurfaceThickness", @"frontCalibrationFrameSurfaceRefractiveIndex",
							 @"mediumRefractiveIndex", @"lambda", @"exportFormatVersion"];
		NSArray *booleans = @[@"useIterativeTriangulation", @"syncIsLocked", @"isMasterClip", @"muted",
							  @"frontIsCalibrated", @"backIsCalibrated", @"shouldCorrectRefraction"];
		NSArray *matrices = @[@"matrixScreenToCalibrationFrameFront", @"matrixScreenToCalibrationFrameBack",
							  @"matrixCalibrationFrameFrontToScreen", @"matrixCalibrationFrameBackToScreen"];
		// The strings are listed rather than left to the default so that the warning below means what it says: an
		// attribute reaching it is one nobody has classified, not merely one that happens to be text.
		NSArray *strings = @[@"name", @"type", @"notes", @"observer", @"timecode",
							 @"calibrationTimecode", @"dateCreated", @"dateLastSaved",
							 @"dateCreatedISO", @"dateLastSavedISO", @"dateLastExported", @"exportDate",
							 @"appVersion", @"appVersionCreated", @"appVersionLastSaved",
							 @"videoClip", @"videoClipName", @"fileName", @"syncOffset", @"clipLength",
							 @"axisHorizontal", @"axisVertical", @"axisFrontToBack"];
		NSMutableDictionary *table = [NSMutableDictionary new];
		for (NSString *name in strings) table[name] = [NSNumber numberWithInteger:VSExportValueTypeString];
		for (NSString *name in numbers) table[name] = [NSNumber numberWithInteger:VSExportValueTypeNumber];
		for (NSString *name in booleans) table[name] = [NSNumber numberWithInteger:VSExportValueTypeBool];
		for (NSString *name in matrices) table[name] = [NSNumber numberWithInteger:VSExportValueTypeMatrix];
		types = [table copy];
	});
	return types;
}

+ (id) valueForAttributeNamed:(NSString *)name stringValue:(NSString *)stringValue
{
	if ([stringValue length] == 0) return [NSNull null];	// the export's sentinel for "no value", made explicit
	NSNumber *typeNumber = [[self attributeTypes] objectForKey:name];
	if (typeNumber == nil) {
		NSLog(@"JSON export: attribute \"%@\" is not in the type table, so it is being exported as a string. Add it to +attributeTypes in DataExport.m.",name);
		return stringValue;
	}
	switch ((VSExportValueType) [typeNumber integerValue]) {
		case VSExportValueTypeNumber:
			return [NSNumber numberWithDouble:[stringValue doubleValue]];
		case VSExportValueTypeBool:
			return [NSNumber numberWithBool:[stringValue isEqualToString:@"YES"]];
		case VSExportValueTypeMatrix: {
			// {{a,b,c},{d,e,f},{g,h,i}} into nested arrays. Anything that doesn't yield exactly nine numbers -- an
			// uncalibrated clip writes an empty string, which is caught above -- becomes null rather than a guess.
			NSMutableArray *values = [NSMutableArray new];
			NSScanner *scanner = [NSScanner scannerWithString:stringValue];
			[scanner setCharactersToBeSkipped:[NSCharacterSet characterSetWithCharactersInString:@"{}, \t\n"]];
			double value;
			while ([scanner scanDouble:&value]) [values addObject:[NSNumber numberWithDouble:value]];
			if ([values count] != 9) return [NSNull null];
			NSMutableArray *rows = [NSMutableArray new];
			for (NSUInteger row = 0; row < 3; row++) [rows addObject:[values subarrayWithRange:NSMakeRange(3*row,3)]];
			return rows;
		}
		case VSExportValueTypeString:
			break;
	}
	return stringValue;
}

+ (NSDictionary *) JSONObjectFromXMLElement:(NSXMLElement *)element
{
	NSMutableDictionary *result = [NSMutableDictionary new];
	for (NSXMLNode *attribute in [element attributes]) {
		result[[attribute name]] = [self valueForAttributeNamed:[attribute name] stringValue:[attribute stringValue]];
	}
	NSMutableDictionary *childrenByName = [NSMutableDictionary new];
	for (NSXMLNode *child in [element children]) {
		if ([child kind] != NSXMLElementKind) continue;
		NSMutableArray *group = childrenByName[[child name]];
		if (group == nil) {
			group = [NSMutableArray new];
			childrenByName[[child name]] = group;
		}
		[group addObject:[self JSONObjectFromXMLElement:(NSXMLElement *)child]];
	}
	if ([childrenByName count] == 0 && [[element stringValue] length] > 0) {
		result[@"text"] = [element stringValue];
	}
	for (NSString *childName in childrenByName) {
		// An element carrying both an attribute and a child element of the same name would be ambiguous. Nothing in
		// this format does, but rather than let a future one overwrite the attribute silently, the children go to a
		// suffixed key and say so, which loses nothing and is visible in the file.
		NSString *key = childName;
		if (result[key] != nil) {
			key = [childName stringByAppendingString:@"Elements"];
			NSLog(@"JSON export: element <%@> has both an attribute and child elements named \"%@\"; the children are under \"%@\".",[element name],childName,key);
		}
		result[key] = childrenByName[childName];
	}
	return result;
}

+ (NSDictionary *) JSONObjectFromXMLDocument:(NSXMLDocument *)xmlDoc
{
	NSXMLElement *root = [xmlDoc rootElement];
	return [NSDictionary dictionaryWithObject:[self JSONObjectFromXMLElement:root] forKey:[root name]];
}

@end

#pragma mark - Exports

@implementation VidSyncDocument (DataExport)

- (NSArray *) sortedAll3DPoints:(NSError **)fetchError
{
	// Points are sorted by event and then by point index, which both makes the exported row order deterministic
	// (an unsorted fetch has no promised order at all) and matches the order the XML export emits them in.
	NSFetchRequest *fetchRequest = [[NSFetchRequest alloc] init];
	[fetchRequest setEntity:[NSEntityDescription entityForName:@"VSPoint" inManagedObjectContext:[self managedObjectContext]]];
	NSArray *fetchResults = [[self managedObjectContext] executeFetchRequest:fetchRequest error:fetchError];
	// Sorted after the fetch rather than by the fetch request, because the event index is across a relationship.
	return [fetchResults sortedArrayUsingDescriptors:[NSArray arrayWithObjects:
													 [NSSortDescriptor sortDescriptorWithKey:@"trackedEvent.index" ascending:YES],
													 [NSSortDescriptor sortDescriptorWithKey:@"index" ascending:YES],
													 nil]];
}

- (NSString *) pointsSpreadsheetHeader:(NSString *)separator
{
	// The Screen Coordinates column exists only when the rows carry it. This header used to be duplicated
	// between the CSV and clipboard exports, which is how the two drifted apart in the first place.
	BOOL includeScreenCoords = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeScreenCoordsInExports"] boolValue];
	NSMutableArray *columns = [NSMutableArray arrayWithObjects:
							   @"Object(s)",
							   @"Event",
							   @"Timecode",
							   @"Time",
							   @"X",
							   @"Y",
							   @"Z",
							   @"PLD Error",
							   @"Re-projection Error",
							   @"Nearest Camera Distance",
							   @"Point Index",
							   @"Event Notes",
							   nil];
	if (includeScreenCoords) [columns addObject:@"Screen Coordinates"];
	// Appended after the conditional Screen Coordinates column rather than before it, so that no pre-existing column
	// ever changes position regardless of how that preference is set. Event Index is project-unique and is the key to
	// deduplicate on when an event shared by several objects appears once per object; Event Type and Event Name are
	// the other two components of the composite Event column, which previously had to be parsed back apart; Object
	// Indices is the machine-readable form of the Object(s) column, which joins human-readable descriptions.
	[columns addObject:@"Event Index"];
	[columns addObject:@"Event Type"];
	[columns addObject:@"Event Name"];
	[columns addObject:@"Object Indices"];
	return [[columns componentsJoinedByString:separator] stringByAppendingString:@"\n"];
}

- (NSString *) exportProvenanceStringForExportDate:(NSDate *)exportDate
{
	// Appended to the title line of the spreadsheet exports, which is already not a data record, so anyone
	// parsing these files is already skipping it and the "skip one line" contract is unchanged.
	// The two settings ride here rather than in columns of their own, because they are identical in every row of the
	// file. Between them they say what the coordinates mean: which triangulation method produced them, and whether
	// the screen coordinates column is present at all.
	BOOL includeScreenCoords = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeScreenCoordsInExports"] boolValue];
	NSMutableString *provenance = [NSMutableString stringWithFormat:@"exportFormatVersion=%ld; exportDate=%@; appVersion=%@; useIterativeTriangulation=%@; includeScreenCoordsInExports=%@",
								   (long) VSExportFormatVersion,
								   [UtilityFunctions ISO8601StringFromDateTime:exportDate],
								   [UtilityFunctions appVersionString],
								   [self.project.useIterativeTriangulation boolValue] ? @"YES" : @"NO",
								   includeScreenCoords ? @"YES" : @"NO"];
	if ([self.project.dateCreated length] > 0) [provenance appendFormat:@"; projectCreated=%@",self.project.dateCreated];
	if ([self.project.appVersionCreated length] > 0) [provenance appendFormat:@"; projectCreatedWithAppVersion=%@",self.project.appVersionCreated];
	if ([self.project.dateLastSaved length] > 0) [provenance appendFormat:@"; projectLastSaved=%@",self.project.dateLastSaved];
	if ([self.project.appVersionLastSaved length] > 0) [provenance appendFormat:@"; projectLastSavedWithAppVersion=%@",self.project.appVersionLastSaved];
	return provenance;
}

- (IBAction) copyAll3DPointsToClipboard:(id)sender
{
	NSError *fetchError = nil;
	NSArray *fetchResults = [self sortedAll3DPoints:&fetchError];
	if ((fetchResults != nil) && (fetchError == nil)) {
		if ([fetchResults count] == 0) {	// a successful fetch that found nothing is just as much a reason to speak up as a failed one
			[UtilityFunctions InformUser:@"There are no 3D points yet, so you can't export them." withTitle:@"No points."];
			return;
		}
		NSMutableString *totalString = [NSMutableString new];
		for (VSPoint *point in fetchResults) {
			[totalString appendString:[point spreadsheetFormatted3DPoint:@"\t"]];
		}
		if (![totalString isEqualToString:@""]) {	// if there are some connecting lines to paste
			NSString *titleString = [NSString stringWithFormat:@"%@ 3D Points\t%@\n%@",
								self.project.name ?: @"",
								[self exportProvenanceStringForExportDate:[NSDate dateWithTimeIntervalSinceNow:0.0]],
								[self pointsSpreadsheetHeader:@"\t"]
								];
			NSPasteboard *pb = [NSPasteboard generalPasteboard];
			[pb declareTypes:[NSArray arrayWithObjects:NSPasteboardTypeString, nil] owner:self];
			[pb setString:[titleString stringByAppendingString:totalString] forType:NSPasteboardTypeString];
		}
	} else {
		[UtilityFunctions InformUser:@"There are no 3D points yet, so you can't export them." withTitle:@"No points."];
		if (fetchError != nil) [self presentError:fetchError];
	}
}

- (IBAction) exportCSVFile:(id)sender
{
	NSError *fetchError = nil;
	NSArray *fetchResults = [self sortedAll3DPoints:&fetchError];
	if ((fetchResults != nil) && (fetchError == nil) && ([fetchResults count] > 0)) {
		NSDate *exportDate = [NSDate dateWithTimeIntervalSinceNow:0.0];
		NSMutableString *totalString = [NSMutableString new];
		for (VSPoint *point in fetchResults) {
			[totalString appendString:[point spreadsheetFormatted3DPoint:@","]];
		}
		if (![totalString isEqualToString:@""]) {	// if there are some connecting lines to paste
			NSString *titleString = [NSString stringWithFormat:@"All measured points in VidSync project %@,%@\n%@",
								self.project.name ?: @"",
								[self exportProvenanceStringForExportDate:exportDate],
								[self pointsSpreadsheetHeader:@","]
								];
			[totalString insertString:titleString atIndex:0];
			NSError *error;
			if ([totalString writeToFile:[self fileNameForExportedFile:@".csv"] atomically:YES encoding:NSUTF8StringEncoding error:&error]) {
				self.project.updatedSinceLastExport = [NSNumber numberWithBool:NO];
				self.project.dateLastExported = [UtilityFunctions ISO8601StringFromDateTime:exportDate];
				[shutterClick play];
			} else {
				[UtilityFunctions InformUser:@"This project's data could not be exported to a CSV file for some reason." withTitle:@"Error writing file"];
			}
		}
	}
	if (fetchResults == nil || [fetchResults count] == 0) [UtilityFunctions InformUser:@"There are no points yet, so you can't export them." withTitle:@"No points"];
	if (fetchError != nil) [self presentError:fetchError];
}

- (IBAction) copyAllConnectingLinesToClipboard:(id)sender
{
	// Copies to clipboard the connecting line lengths and confidence intervals for all events whose type has "connectingLineLengthLabeled" set to yes.
	// Columns are delineated by tabs \t, and new lines by newline characters \n.  This works fine for Excel 2008 for Mac, at least.
	NSFetchRequest *fetchRequest = [[NSFetchRequest alloc] init];
	NSError *fetchError = nil;
	[fetchRequest setEntity:[NSEntityDescription entityForName:@"VSTrackedEvent" inManagedObjectContext:[self managedObjectContext]]];
	NSArray *fetchResults = [[self managedObjectContext] executeFetchRequest:fetchRequest error:&fetchError];
	if ((fetchResults != nil) && (fetchError == nil)) {
		NSArray *connectingLines;
		NSMutableString *totalString = [NSMutableString new];
		for (VSTrackedEvent *event in fetchResults) {
			connectingLines = [event spreadsheetFormattedConnectingLines];
			for (NSString *lineInfo in connectingLines) {
				[totalString appendString:lineInfo];
			}
		}
		if (![totalString isEqualToString:@""]) {	// if there are some connecting lines to paste
			NSString *titleString = [NSString stringWithFormat:@"%@ Connecting Line Lengths\t%@\n%@\t%@\t%@\t%@\n",
								self.project.name ?: @"",
								[self exportProvenanceStringForExportDate:[NSDate dateWithTimeIntervalSinceNow:0.0]],
								@"Object",
								@"Event",
								@"Length",
								@"Speed"
								];
			NSPasteboard *pb = [NSPasteboard generalPasteboard];
			[pb declareTypes:[NSArray arrayWithObjects:NSPasteboardTypeString, nil] owner:self];
			[pb setString:[titleString stringByAppendingString:totalString] forType:NSPasteboardTypeString];
		}
	}
	if (fetchResults == nil || [fetchResults count] == 0) [UtilityFunctions InformUser:@"There are no events yet, so you can't export their connecting lines." withTitle:@"No events"];
	if (fetchError != nil) [self presentError:fetchError];
}

- (NSXMLDocument *) projectAsXMLDocumentForExportDate:(NSDate *)exportDate
{
	// The one description of a project, built once and rendered two ways. The XML export writes this document; the
	// JSON export converts this same document. Neither format can therefore say something the other doesn't.
	NSXMLElement *root = (NSXMLElement *) [NSXMLNode elementWithName:@"project"];
	NSXMLDocument *xmlDoc = [[NSXMLDocument alloc] initWithRootElement:root];
	[xmlDoc setVersion:@"1.0"];
	[xmlDoc setCharacterEncoding:@"UTF-8"];

	// The ?: @"" fallbacks match the idiom every child element already uses, and are reachable: name and notes
	// are never initialized, and dateLastSaved is nil until the document is first saved.
	[root addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.project.name ?: @""]];
	[root addAttribute:[NSXMLNode attributeWithName:@"notes" stringValue:self.project.notes ?: @""]];
	[root addAttribute:[NSXMLNode attributeWithName:@"calibrationTimecode" stringValue:self.project.calibrationTimecode ?: @""]];
	[root addAttribute:[NSXMLNode attributeWithName:@"dateCreated" stringValue:self.project.dateCreated ?: @""]];
	[root addAttribute:[NSXMLNode attributeWithName:@"dateLastSaved" stringValue:self.project.dateLastSaved ?: @""]];

	// Provenance. All new attributes on an existing element, so no existing consumer is affected. dateCreated and
	// dateLastSaved keep their original hand-rolled format above; the ISO 8601 versions are alongside them for
	// parsers that won't take it.
	[root addAttribute:[NSXMLNode attributeWithName:@"exportFormatVersion" stringValue:[NSString stringWithFormat:@"%ld",(long) VSExportFormatVersion]]];
	[root addAttribute:[NSXMLNode attributeWithName:@"exportDate" stringValue:[UtilityFunctions ISO8601StringFromDateTime:exportDate]]];
	[root addAttribute:[NSXMLNode attributeWithName:@"appVersion" stringValue:[UtilityFunctions appVersionString]]];
	[root addAttribute:[NSXMLNode attributeWithName:@"appVersionCreated" stringValue:self.project.appVersionCreated ?: @""]];
	[root addAttribute:[NSXMLNode attributeWithName:@"appVersionLastSaved" stringValue:self.project.appVersionLastSaved ?: @""]];
	[root addAttribute:[NSXMLNode attributeWithName:@"dateLastExported" stringValue:self.project.dateLastExported ?: @""]];	// the export before this one; this one is exportDate
	NSString *dateCreatedISO = ([self.project.dateCreated length] > 0) ? [UtilityFunctions ISO8601StringFromDateTime:[self.project dateCreatedAsNSDate]] : @"";
	NSString *dateLastSavedISO = ([self.project.dateLastSaved length] > 0) ? [UtilityFunctions ISO8601StringFromDateTime:[self.project dateLastSavedAsNSDate]] : @"";
	[root addAttribute:[NSXMLNode attributeWithName:@"dateCreatedISO" stringValue:dateCreatedISO]];
	[root addAttribute:[NSXMLNode attributeWithName:@"dateLastSavedISO" stringValue:dateLastSavedISO]];

	// Which triangulation method produced every coordinate in this file. On the linear path the coordinates are the
	// closest-point-of-approach solution and reprojectionErrorNorm is deliberately left empty; on the iterative path
	// they minimize pixel error. Without this, an empty reprojectionErrorNorm was ambiguous between "linear method"
	// and "too few views to solve at all".
	[root addAttribute:[NSXMLNode attributeWithName:@"useIterativeTriangulation" stringValue:[self.project.useIterativeTriangulation boolValue] ? @"YES" : @"NO"]];

	// An event belonging to several objects is emitted in full under each of them, so a consumer that flattens the
	// objects tree into a list of measurements will count those points once per owning object. Event index is unique
	// across the project (see +highestEventIndexInProject:), so it is the key to deduplicate on. This is documented
	// rather than restructured because restructuring would move elements that consumers already read.
	NSXMLElement *trackedObjects = (NSXMLElement *) [NSXMLNode elementWithName:@"objects"];
	for (VSTrackedObject *trackedObject in self.project.trackedObjects) {
		[trackedObjects addChild:[trackedObject representationAsXMLNode]];
	}
	[root addChild:trackedObjects];
	
	NSXMLElement *videoClips = (NSXMLElement *) [NSXMLNode elementWithName:@"videoClips"];
	for (VSVideoClip *videoClip in self.project.videoClips) {
		[videoClips addChild:[videoClip representationAsXMLNode]];
	}
	[root addChild:videoClips];

	return xmlDoc;
}

- (IBAction) exportXMLFile:(id)sender
{
	NSDate *exportDate = [NSDate dateWithTimeIntervalSinceNow:0.0];
	NSXMLDocument *xmlDoc = [self projectAsXMLDocumentForExportDate:exportDate];
	NSData *xmlData = [xmlDoc XMLDataWithOptions:NSXMLNodePrettyPrint];
	if ([xmlData writeToFile:[self fileNameForExportedFile:@".xml"] atomically:YES]) {
		self.project.updatedSinceLastExport = [NSNumber numberWithBool:NO];
		self.project.dateLastExported = [UtilityFunctions ISO8601StringFromDateTime:exportDate];
		[shutterClick play];
	} else {
		[UtilityFunctions InformUser:@"This project's data could not be exported to an XML file for some reason." withTitle:@"Error writing file"];
	}
}

- (IBAction) exportJSONFile:(id)sender
{
	NSDate *exportDate = [NSDate dateWithTimeIntervalSinceNow:0.0];
	NSXMLDocument *xmlDoc = [self projectAsXMLDocumentForExportDate:exportDate];
	NSDictionary *JSONObject = [VSExportJSON JSONObjectFromXMLDocument:xmlDoc];
	NSError *error = nil;
	// Sorted keys because an unordered dictionary would otherwise shuffle the file's key order from one export to the
	// next, which makes two exports of the same project impossible to diff.
	NSData *JSONData = [NSJSONSerialization dataWithJSONObject:JSONObject
													  options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys
														error:&error];
	if (JSONData != nil && [JSONData writeToFile:[self fileNameForExportedFile:@".json"] atomically:YES]) {
		self.project.updatedSinceLastExport = [NSNumber numberWithBool:NO];
		self.project.dateLastExported = [UtilityFunctions ISO8601StringFromDateTime:exportDate];
		[shutterClick play];
	} else {
		[UtilityFunctions InformUser:@"This project's data could not be exported to a JSON file for some reason." withTitle:@"Error writing file"];
		if (error != nil) [self presentError:error];
	}
}

- (NSString *)folderForExportedFiles
{
	// The one place that decides which folder exported files land in, so the "Open in Finder" button on the Export
	// Data tab can ask the exporter instead of rebuilding the path with its own idea of how a project name becomes
	// a folder name. The two had drifted apart: this one strips the characters a file name can't contain, while the
	// button replaced colons and slashes with other characters, so for some project names the button created and
	// revealed a folder that no export was ever written into.
	BOOL createFolderForProject = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"createFolderForProjectExports"] boolValue];
	NSString *folder = self.project.exportPathForData ?: @"";
	NSString *projectFolderName = [UtilityFunctions sanitizeFileNameString:self.project.name ?: @""];
	// An unnamed project (name is never initialized, so this is the state of a project that has never been named)
	// gets no subfolder at all, rather than one named after nothing, matching what the file naming below does.
	if (createFolderForProject && [projectFolderName length] > 0) folder = [folder stringByAppendingPathComponent:projectFolderName];
	return [folder stringByStandardizingPath];	// collapses the double slash that an export path stored with a trailing slash used to produce
}

- (NSString *)fileNameForExportedFile:(NSString *)extension
{
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create capture directory if it doesn't exist yet
	BOOL includeProjectName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeProjectNameInExportedFileName"] boolValue];
	BOOL includeCurrentDate = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeCurrentDateInExportedFileName"] boolValue];
	BOOL includeCurrentTime = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeCurrentTimeInExportedFileName"] boolValue];
	NSString *customText = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"exportedFileNameCustomText"];
	NSMutableString *filePath = [NSMutableString stringWithString:[self folderForExportedFiles]];
	if (![fm fileExistsAtPath:filePath]) [fm createDirectoryAtPath:filePath withIntermediateDirectories:YES attributes:nil error:NULL];
	[filePath appendString:@"/"];
	NSDate *now = [NSDate dateWithTimeIntervalSinceNow:0.0];
	NSMutableArray *pathStrings = [NSMutableArray new];
	NSString *sanitizedProjectName = [UtilityFunctions sanitizeFileNameString:self.project.name ?: @""];
	if (includeProjectName && ![sanitizedProjectName isEqualToString:@""]) [pathStrings addObject:sanitizedProjectName];	// an empty name would otherwise leave a stray " - " in the file name
	if (includeCurrentDate) [pathStrings addObject:[UtilityFunctions stringFromDateTime:now format:@"yyy-MM-dd"]];
	if (includeCurrentTime) [pathStrings addObject:[UtilityFunctions stringFromDateTime:now format:@"HH:mm:ss"]];
	if (customText != nil && ![customText isEqualToString:@""]) [pathStrings addObject:customText];
	NSString *fileName = [pathStrings componentsJoinedByString:@" - "]; // doing this from an array avoids annoying trailing dashes etc
	if ([fileName isEqualToString:@""]) fileName = @"Untitled";	// give it a default if all naming values are turned off
	[filePath appendString:fileName];
	[filePath appendString:extension];
	return filePath;
}

@end
