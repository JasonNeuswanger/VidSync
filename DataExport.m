//
//  DataExport.m
//  VidSync
//
//  Created by Jason Neuswanger on 4/7/10.
//  Copyright 2010 University of Alaska Fairbanks. All rights reserved.
//

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
			[totalString appendString:[point spreadsheetFormatted3DPoint]];
		}
		if (![totalString isEqualToString:@""]) {	// if there are some connecting lines to paste
			NSString *titleString = [NSString stringWithFormat:@"%@ 3D Points\n%@\t%@\t%@\t%@\t%@\t%@\t%@\n",
									 self.project.name,
									 @"Object(s)",
									 @"Event",
									 @"X",
									 @"Y",
									 @"Z",
									 @"PLD Error",
									 @"Timecode"
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
			[totalString appendString:[point spreadsheetFormatted3DPoint]];
		}
		if (![totalString isEqualToString:@""]) {	// if there are some connecting lines to paste
			NSString *titleString = [NSString stringWithFormat:@"All measured points in VidSync project %@\n%@,%@,%@,%@,%@,%@,%@,%@,%@\n",
									 self.project.name,
									 @"Object(s)",
									 @"Event",
                                     @"Timecode",
									 @"X",
									 @"Y",
									 @"Z",
									 @"PLD Error",
                                     @"Re-projection Error Norm",
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
			NSString *titleString = [NSString stringWithFormat:@"%@ Connecting Line Lengths\n%@\t%@\t%@\n",
									 self.project.name,
									 @"Object",
									 @"Event",
									 @"Length"
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
	NSXMLElement *root = (NSXMLElement *) [NSXMLNode elementWithName:@"objects"];
	NSXMLDocument *xmlDoc = [[NSXMLDocument alloc] initWithRootElement:root];
	[xmlDoc setVersion:@"1.0"];
	[xmlDoc setCharacterEncoding:@"UTF-8"];
	for (VSTrackedObject *trackedObject in self.project.trackedObjects) {
		[root addChild:[trackedObject representationAsXMLNode]];
	}
	for (VSVideoClip *videoClip in self.project.videoClips) {
		[root addChild:[videoClip representationAsXMLNode]];
	}	
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
	if (createFolderForProject) [filePath appendString:[NSString stringWithFormat:@"/%@",self.project.name]];
	if (![fm fileExistsAtPath:filePath]) [fm createDirectoryAtPath:filePath withIntermediateDirectories:YES attributes:nil error:NULL];
	[filePath appendString:@"/"];
	if (includeProjectName) [filePath appendString:[NSString stringWithFormat:@"%@ - ",self.project.name]];
	NSDate *now = [NSDate dateWithTimeIntervalSinceNow:0.0];
	if (includeCurrentDate) {
		NSString *currentDate = [now descriptionWithCalendarFormat:@"%Y-%m-%d - " timeZone:nil locale:[[NSUserDefaults standardUserDefaults] dictionaryRepresentation]];
		[filePath appendString:currentDate];
	}
	if (includeCurrentTime) {
		NSString *currentTime = [now descriptionWithCalendarFormat:@"%H:%M:%S - " timeZone:nil locale:[[NSUserDefaults standardUserDefaults] dictionaryRepresentation]];
		[filePath appendString:currentTime];
	}
	if (![customText isEqualToString:@""]) [filePath appendString:customText];
	if ([filePath isEqualToString:@""]) [filePath appendString:@"Untitled"];	// give it a default if all naming values are turned off
	[filePath appendString:extension];
	return filePath;
}

@end
