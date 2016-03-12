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


#import "VidSyncDocument.h"

@implementation VidSyncDocument (DataExport)

- (IBAction) copyAll3DPointsToClipboard:(id)sender
{
    NSFetchRequest *fetchRequest = [[NSFetchRequest alloc] init];
    NSError *fetchError = nil;
    [fetchRequest setEntity:[NSEntityDescription entityForName:@"VSPoint" inManagedObjectContext:[self managedObjectContext]]];
    NSArray *fetchResults = [[self managedObjectContext] executeFetchRequest:fetchRequest error:&fetchError];
    if ((fetchResults != nil) && (fetchError == nil)) {
		NSMutableString *totalString = [NSMutableString new];
		for (VSPoint *point in fetchResults) {
            [totalString appendString:[point spreadsheetFormatted3DPoint:@"\t"]];
		}
		if (![totalString isEqualToString:@""]) {	// if there are some connecting lines to paste
			NSString *titleString = [NSString stringWithFormat:@"%@ 3D Points\n%@\t%@\t%@\t%@\t%@\t%@\t%@\t%@\t%@\t%@\t%@\n",
									 self.project.name,
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
                                     @"Screen coordinates (may be multiple columns)"
									 ];
			NSPasteboard *pb = [NSPasteboard generalPasteboard];
			[pb declareTypes:[NSArray arrayWithObjects:NSStringPboardType, nil] owner:self];
			[pb setString:[titleString stringByAppendingString:totalString] forType:NSStringPboardType];	
		}
	}	
	if (fetchResults == nil) NSRunAlertPanel(@"No points.",@"There are no 3D points yet, so you can't export them.",@"Ok",nil,nil); 
    if (fetchError != nil) [self presentError:fetchError];
}

- (IBAction) exportCSVFile:(id)sender
{
    NSFetchRequest *fetchRequest = [[NSFetchRequest alloc] init];
    NSError *fetchError = nil;
    [fetchRequest setEntity:[NSEntityDescription entityForName:@"VSPoint" inManagedObjectContext:[self managedObjectContext]]];
    NSArray *fetchResults = [[self managedObjectContext] executeFetchRequest:fetchRequest error:&fetchError];
    if ((fetchResults != nil) && (fetchError == nil)) {
		NSMutableString *totalString = [NSMutableString new];
		for (VSPoint *point in fetchResults) {
            [totalString appendString:[point spreadsheetFormatted3DPoint:@","]];
		}
		if (![totalString isEqualToString:@""]) {	// if there are some connecting lines to paste
			NSString *titleString = [NSString stringWithFormat:@"All measured points in VidSync project %@\n%@,%@,%@,%@,%@,%@,%@,%@,%@,%@,%@\n",
									 self.project.name,
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
                                     @"Screen coordinates (may be multiple columns)"
									 ];
            [totalString insertString:titleString atIndex:0];
            NSError *error;
            if ([totalString writeToFile:[self fileNameForExportedFile:@".csv"] atomically:YES encoding:NSUTF8StringEncoding error:&error]) {
                [shutterClick play];
            } else {
                NSRunAlertPanel(@"Error writing file.",@"This project's data could not be exported to an XML file for some reason.",@"Ok",nil,nil);
            }
        }
	}	
	if (fetchResults == nil) NSRunAlertPanel(@"No points.",@"There are no points yet, so you can't export them.",@"Ok",nil,nil); 
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
			NSString *titleString = [NSString stringWithFormat:@"%@ Connecting Line Lengths\n%@\t%@\t%@\t%@\n",
									 self.project.name,
									 @"Object",
									 @"Event",
									 @"Length",
                                     @"Speed"
									 ];
			NSPasteboard *pb = [NSPasteboard generalPasteboard];
			[pb declareTypes:[NSArray arrayWithObjects:NSStringPboardType, nil] owner:self];
			[pb setString:[titleString stringByAppendingString:totalString] forType:NSStringPboardType];	
		}
	}	
	if (fetchResults == nil) NSRunAlertPanel(@"No events.",@"There are no events yet, so you can't export their connecting lines.",@"Ok",nil,nil); 
    if (fetchError != nil) [self presentError:fetchError];
}

- (IBAction) exportXMLFile:(id)sender
{
	NSXMLElement *root = (NSXMLElement *) [NSXMLNode elementWithName:@"project"];
	NSXMLDocument *xmlDoc = [[NSXMLDocument alloc] initWithRootElement:root];
	[xmlDoc setVersion:@"1.0"];
	[xmlDoc setCharacterEncoding:@"UTF-8"];
    
    [root addAttribute:[NSXMLNode attributeWithName:@"name" stringValue:self.project.name]];
    [root addAttribute:[NSXMLNode attributeWithName:@"notes" stringValue:self.project.notes]];
    [root addAttribute:[NSXMLNode attributeWithName:@"calibrationTimecode" stringValue:self.project.calibrationTimecode]];
    [root addAttribute:[NSXMLNode attributeWithName:@"dateCreated" stringValue:self.project.dateCreated]];
    [root addAttribute:[NSXMLNode attributeWithName:@"dateLastSaved" stringValue:self.project.dateLastSaved]];
    
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
		[shutterClick play];
	} else {
		NSRunAlertPanel(@"Error writing file.",@"This project's data could not be exported to an XML file for some reason.",@"Ok",nil,nil);
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
    if (createFolderForProject) [filePath appendString:[NSString stringWithFormat:@"/%@",[UtilityFunctions sanitizeFileNameString:self.project.name]]];
	if (![fm fileExistsAtPath:filePath]) [fm createDirectoryAtPath:filePath withIntermediateDirectories:YES attributes:nil error:NULL];
	[filePath appendString:@"/"];
    NSDate *now = [NSDate dateWithTimeIntervalSinceNow:0.0];
    NSMutableArray *pathStrings = [NSMutableArray new];
    if (includeProjectName) [pathStrings addObject:[UtilityFunctions sanitizeFileNameString:self.project.name]];
    if (includeCurrentDate) [pathStrings addObject:[now descriptionWithCalendarFormat:@"%Y-%m-%d" timeZone:nil locale:[[NSUserDefaults standardUserDefaults] dictionaryRepresentation]]];
    if (includeCurrentTime) [pathStrings addObject:[now descriptionWithCalendarFormat:@"%H:%M:%S" timeZone:nil locale:[[NSUserDefaults standardUserDefaults] dictionaryRepresentation]]];
    if (![customText isEqualToString:@""]) [pathStrings addObject:customText];
    NSString *fileName = [pathStrings componentsJoinedByString:@" - "]; // doing this from an array avoids annoying trailing dashes etc
    if ([fileName isEqualToString:@""]) fileName = @"Untitled";	// give it a default if all naming values are turned off
    [filePath appendString:fileName];
    [filePath appendString:extension];
	return filePath;
}

@end
