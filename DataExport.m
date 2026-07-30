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
static const NSInteger VSExportFormatVersion = 1;

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
	return [[columns componentsJoinedByString:separator] stringByAppendingString:@"\n"];
}

- (NSString *) exportProvenanceStringForExportDate:(NSDate *)exportDate
{
	// Appended to the title line of the spreadsheet exports, which is already not a data record, so anyone
	// parsing these files is already skipping it and the "skip one line" contract is unchanged.
	NSMutableString *provenance = [NSMutableString stringWithFormat:@"exportFormatVersion=%ld; exportDate=%@; appVersion=%@",
								   (long) VSExportFormatVersion,
								   [UtilityFunctions ISO8601StringFromDateTime:exportDate],
								   [UtilityFunctions appVersionString]];
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

- (IBAction) exportXMLFile:(id)sender
{
	NSXMLElement *root = (NSXMLElement *) [NSXMLNode elementWithName:@"project"];
	NSXMLDocument *xmlDoc = [[NSXMLDocument alloc] initWithRootElement:root];
	[xmlDoc setVersion:@"1.0"];
	[xmlDoc setCharacterEncoding:@"UTF-8"];
	
	NSDate *exportDate = [NSDate dateWithTimeIntervalSinceNow:0.0];

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
	
	NSData *xmlData = [xmlDoc XMLDataWithOptions:NSXMLNodePrettyPrint];
	if ([xmlData writeToFile:[self fileNameForExportedFile:@".xml"] atomically:YES]) {
		self.project.updatedSinceLastExport = [NSNumber numberWithBool:NO];
		self.project.dateLastExported = [UtilityFunctions ISO8601StringFromDateTime:exportDate];
		[shutterClick play];
	} else {
		[UtilityFunctions InformUser:@"This project's data could not be exported to an XML file for some reason." withTitle:@"Error writing file"];
	}
}

- (NSString *)fileNameForExportedFile:(NSString *)extension
{
	NSFileManager *fm = [NSFileManager defaultManager];	// file manager to create capture directory if it doesn't exist yet
	BOOL includeProjectName = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeProjectNameInExportedFileName"] boolValue];
	BOOL includeCurrentDate = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeCurrentDateInExportedFileName"] boolValue];
	BOOL includeCurrentTime = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeCurrentTimeInExportedFileName"] boolValue];
	BOOL createFolderForProject = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"createFolderForProjectExports"] boolValue];
	NSString *customText = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"exportedFileNameCustomText"];
	NSMutableString *filePath = [NSMutableString stringWithString:self.project.exportPathForData];
	if (createFolderForProject) [filePath appendString:[NSString stringWithFormat:@"/%@",[UtilityFunctions sanitizeFileNameString:self.project.name ?: @""]]];
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
