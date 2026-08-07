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


#import "opencv2/opencv.hpp"

#import "UtilityFunctions.h"

@implementation UtilityFunctions

+ (NSColor *) userDefaultColorForKey:(NSString *)key
{
	NSColor *color;
	NSData *colorData = [[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:key];
	if (colorData != nil) {
		NSError *err = nil;
		color = [NSKeyedUnarchiver unarchivedObjectOfClass:[NSColor class] fromData:colorData error:&err];
		if (color == nil) {
			// Stored data that won't decode, which the modern unarchiver reports by returning nil rather than
			// throwing. Callers assume they got a color back; one of them writes it straight into a new
			// annotation's Core Data attribute, so returning nil would persist the failure rather than show it.
			NSLog(@"Color data for key %@ could not be decoded (%@), using red instead.",key,[err localizedDescription]);
			color = [NSColor redColor];
		}
	} else {
		NSLog(@"Color data was nil for key %@ (not found in user's defaults or in initial default values), using red instead.",key);
		color = [NSColor redColor];
	}
	return color;
}

+ (BOOL) ConfirmAction:(NSString *)userMessage withTitle:(NSString *)title
{
	NSAlert *confirmationAlert = [NSAlert new];
	if (title == nil) {
		[confirmationAlert setMessageText:@"Are you sure?"];
	} else {
		[confirmationAlert setMessageText:title];
	}
	[confirmationAlert setInformativeText:userMessage];
	[confirmationAlert addButtonWithTitle:@"No"];
	[confirmationAlert addButtonWithTitle:@"Yes"];
	[confirmationAlert setAlertStyle:NSAlertStyleWarning];
	NSInteger alertResult = [confirmationAlert runModal];
	return (alertResult == NSAlertSecondButtonReturn);
}

+ (void) InformUser:(NSString *)userMessage withTitle:(NSString *)title
{
	NSAlert *alert = [NSAlert new];
	if (title == nil) {
		[alert setMessageText:@"Important Information"];
	} else {
		[alert setMessageText:title];
	}
	[alert setInformativeText:userMessage];
	[alert addButtonWithTitle:@"Ok"];
	[alert setAlertStyle:NSAlertStyleInformational];
	[alert runModal];
}

+ (NSString *) stringFromDateTime:(NSDate *)dateTime format:(NSString *)format
{
	NSDateFormatter *df = [[NSDateFormatter alloc] init];
	[df setTimeZone:[NSTimeZone systemTimeZone]];
	[df setLocale:[NSLocale currentLocale]];
	[df setDateFormat:format];
	[df setFormatterBehavior:NSDateFormatterBehaviorDefault];
	return [df stringFromDate:dateTime];
}

+ (NSDate *) dateTimeFromString:(NSString *)dateTimeString  format:(NSString *)format
{
	NSDateFormatter *df = [[NSDateFormatter alloc] init];
	[df setTimeZone:[NSTimeZone systemTimeZone]];
	[df setLocale:[NSLocale currentLocale]];
	[df setDateFormat:format];
	[df setFormatterBehavior:NSDateFormatterBehaviorDefault];
	[df setLenient:YES];
	return [df dateFromString:dateTimeString];
}

+ (NSString *) ISO8601StringFromDateTime:(NSDate *)dateTime
{
	// Used for the two dates added for provenance (dateLastExported and the exported files' export date).
	// The older dateCreated and dateLastSaved keep their hand-rolled format, because existing documents
	// contain strings written in it and dateCreatedAsNSDate parses with that same literal pattern.
	if (dateTime == nil) return @"";
	NSDateFormatter *df = [[NSDateFormatter alloc] init];
	[df setTimeZone:[NSTimeZone systemTimeZone]];
	[df setLocale:[NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"]];	// ISO 8601 needs the Gregorian calendar and ASCII digits regardless of the user's locale
	[df setDateFormat:@"yyyy-MM-dd'T'HH:mm:ssZZZZZ"];
	return [df stringFromDate:dateTime];
}

+ (NSString *) appVersionString
{
	// CFBundleVersion has been hardcoded to 1 since the beginning, so the short version string (which resolves
	// to MARKETING_VERSION) is the only meaningful version number to record.
	return [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"";
}

+ (NSArray *) objectsFromSet:(id)set sortedByKey:(NSString *)key
{
	// Every to-many relationship in this model is an unordered set, so anything that walks one and writes the result
	// to a file produces an order Core Data never promised and does not repeat. Two exports of an unchanged project
	// could therefore differ in element order, which makes them impossible to diff and means the XML and JSON
	// exports, built by separate button presses, need not list the same things in the same order.
	return [[set allObjects] sortedArrayUsingDescriptors:[NSArray arrayWithObject:[NSSortDescriptor sortDescriptorWithKey:key ascending:YES]]];
}

+ (NSArray *) XMLElementsSortedByContent:(NSArray *)elements
{
	// For the collections whose members carry no index or name to sort on -- distortion lines and annotations. Their
	// generated XML is sorted instead, which needs no knowledge of what they contain and is a total order as long as
	// no two members are identical, in which case the order between them cannot matter.
	return [elements sortedArrayUsingComparator:^NSComparisonResult(NSXMLNode *a, NSXMLNode *b) {
		return [[a XMLString] compare:[b XMLString]];
	}];
}

+ (NSData *) XMLDataFromDocument:(NSXMLDocument *)xmlDoc
{
	// NSXMLDocument writes a newline, carriage return or tab inside an attribute value as itself, and the XML
	// specification then requires every conforming parser to turn it into a space on the way back in. A note typed on
	// several lines therefore leaves VidSync as one run-on line, silently, in every reader. The framework will not
	// emit the character references that would survive: handing it "&#10;" produces "&amp;#10;", and
	// NSXMLNodePreserveCharacterReferences does not change that. So they are put in here, after serializing.
	//
	// This is a two-state scan rather than a search and replace, because a double quote means different things in
	// different places: inside a tag it delimits an attribute value, but in text content it is an ordinary character
	// that NSXMLDocument leaves unescaped, so splitting the document on quotes would lose track of where it was.
	// Everything else that could confuse the scan is already escaped by the serializer -- <, & , > and " within
	// attribute values, and < and & within text -- so the only raw < opens a tag and the only raw > inside a tag
	// closes it. Text content, including the calibration frame node lists, is left exactly as it was: newlines are
	// preserved there by the specification and need no help.
	//
	// It runs over bytes rather than characters because no byte of a multi-byte UTF-8 sequence is ever an ASCII
	// byte, so the three characters being looked for cannot appear inside one.
	NSData *xmlData = [xmlDoc XMLDataWithOptions:NSXMLNodePrettyPrint];
	const uint8_t *bytes = (const uint8_t *)[xmlData bytes];
	NSUInteger length = [xmlData length];
	NSMutableData *result = [NSMutableData dataWithCapacity:length];
	BOOL insideTag = NO, insideAttributeValue = NO;
	NSUInteger runStart = 0;
	for (NSUInteger i = 0; i < length; i++) {
		uint8_t b = bytes[i];
		if (insideTag && insideAttributeValue && (b == '\n' || b == '\r' || b == '\t')) {
			const char *reference = (b == '\n') ? "&#10;" : ((b == '\r') ? "&#13;" : "&#9;");
			[result appendBytes:(bytes + runStart) length:(i - runStart)];
			[result appendBytes:reference length:strlen(reference)];
			runStart = i + 1;
			continue;
		}
		if (!insideTag) {
			if (b == '<') insideTag = YES;
		} else if (b == '"') {
			insideAttributeValue = !insideAttributeValue;
		} else if (!insideAttributeValue && b == '>') {
			insideTag = NO;
		}
	}
	[result appendBytes:(bytes + runStart) length:(length - runStart)];
	return result;
}

+ (NSString *) escapeSpreadsheetField:(NSString *)field forSeparator:(NSString *)separator
{
	// Quotes a field only when it actually needs quoting, so clean fields (the vast majority, and all of the
	// numeric columns) come out byte-identical to the unescaped output this replaced.
	if (field == nil) return @"";
	BOOL needsQuoting = ([field rangeOfString:@"\""].location != NSNotFound
						 || [field rangeOfString:@"\n"].location != NSNotFound
						 || [field rangeOfString:@"\r"].location != NSNotFound
						 || ([separator length] > 0 && [field rangeOfString:separator].location != NSNotFound));
	if (!needsQuoting) return field;
	return [NSString stringWithFormat:@"\"%@\"",[field stringByReplacingOccurrencesOfString:@"\"" withString:@"\"\""]];
}

+ (void) delayCallback:(void(^)(void))callback forTotalSeconds:(double)delayInSeconds
{
	// Takes a block of code as the parameter and runs it after a given delay in seconds
	// Borrowed from https://stackoverflow.com/questions/15413014/objective-c-delay-action-with-blocks/15413063
	dispatch_time_t popTime = dispatch_time(DISPATCH_TIME_NOW, delayInSeconds * NSEC_PER_SEC);
	dispatch_after(popTime, dispatch_get_main_queue(), ^(void){
		 if(callback){
			 callback();
		 }
	 });
}

+ (BOOL) timeString:(NSString *)timeString1 isEqualToTimeString:(NSString *)timeString2
{
	// This is just a string version of the function below
	CMTime time1 = [UtilityFunctions CMTimeFromString:timeString1];
	CMTime time2 = [UtilityFunctions CMTimeFromString:timeString2];
	return [UtilityFunctions time:time1 isEqualToTime:time2];
}

+ (BOOL) time:(CMTime)time1 isEqualToTime:(CMTime)time2
{
	// This function allows comparing the "equality" of times on different time scales, when the times are effectively the same but not actually equal because of rounding differences in the timescales
	// This is mainly useful for supporting compatibility with older files in which some points were recorded on strange timescales, not the master clip's native time scale
	Float64 cmTime1seconds = CMTimeGetSeconds(time1);
	Float64 cmTime2seconds = CMTimeGetSeconds(time2);
	Float64 timeDifference = fabs(cmTime1seconds - cmTime2seconds);
	return timeDifference < 0.004f;    // a realistic difference for me was 0.0016; the value of 0.004 should support detecting real differences at 240 fps or less and ignoring smaller rounding errors
}

+ (NSString *) CMStringFromTime:(CMTime)time onScale:(int32_t)timeScale
{
	CMTime scaledTime = CMTimeConvertScale(time, timeScale, kCMTimeRoundingMethod_RoundHalfAwayFromZero);
	//    int64_t scaledTimeValue = scaledTime.value;
	//    QTTime qtTime = QTMakeTime(scaledTimeValue,timeScale);
	//    return QTStringFromTime(qtTime);
	if (timeScale == 0) {
		return @"0:00:00:00.0/0";
	} else {
		return [UtilityFunctions CMStringFromTime:scaledTime];
	}
}

+ (NSString *) CMStringFromTime:(CMTime)time
{
	static NSDateFormatter *dateFormatter = [[NSDateFormatter alloc] init];
	[dateFormatter setTimeZone:[NSTimeZone timeZoneWithName:@"UTC"]];
	[dateFormatter setDateFormat:@"HH:mm:ss"];
	if (time.value == 0 && time.timescale == 0) {
		return @"0:00:00:00.0/0"; // added this 1-31-2021 because I was getting divide by zero errors
	}
	int8_t sign = (time.value > 0) ? 1 : -1;
	int64_t time_value_positive = llabs(time.value);
	int32_t subseconds = time_value_positive % time.timescale;
	int64_t seconds = time_value_positive / time.timescale;
	int64_t day = seconds / 86400; // result rounds down to nearest int, typically 0
	seconds -= day * 86400;
	NSDate* date = [NSDate dateWithTimeIntervalSince1970:seconds];
	NSString *sign_string = (sign > 0) ? @"" : @"-";
	NSString *result = [NSString stringWithFormat:@"%@%lld:%@.%d/%d", sign_string, day, [dateFormatter stringFromDate:date], subseconds, time.timescale];
	// NSLog(@"Returning CMStringFromTime value of %@ based on sign=%d, time_value_positive=%lld, seconds=%lld, subseconds=%ld, day=%lld.", result, sign, time_value_positive, seconds, subseconds, day);
	return result;
}

+ (CMTime) CMTimeFromString:(NSString *)timeString;
{
	// Time strings from QTMakeTime anyway are of the form 0:00:15:14.29/30
	// A nil string has to be caught here rather than left to the @catch below: messaging nil
	// never raises, so every parse step silently yielded zero and the method returned
	// CMTimeMake(0,0), which is an *invalid* CMTime rather than a zero one. That invalid value
	// then poisoned CMTimeSubtract(masterTime, offset) wherever a clip's syncOffset had never
	// been written, and AVAssetImageGenerator answers an invalid time with a NULL image and a
	// bare -11800. That NULL was what reached OpenCV and aborted the app during plumbline
	// detection. Any clip that has not been synced yet has a nil syncOffset, so this was
	// reachable in every project.
	if (timeString == nil) return kCMTimeZero;
	@try {
		if ([timeString isEqualToString:@"0:00:00:00.0/0"]) {
			return kCMTimeZero;
		}
		int8_t sign = ([timeString characterAtIndex:0] == '-') ? -1 : 1;
		if (sign < 0) {
			timeString = [timeString substringFromIndex:1];
		}
		NSArray *parts1 = [timeString componentsSeparatedByString:@":"];
		int32_t days = [[parts1 objectAtIndex:0] intValue];
		int32_t hours = [[parts1 objectAtIndex:1] intValue];
		int32_t minutes = [[parts1 objectAtIndex:2] intValue];
		NSArray *parts2 = [[parts1 objectAtIndex:3] componentsSeparatedByString:@"."];
		int32_t seconds = [[parts2 objectAtIndex:0] intValue];
		NSArray *parts3 = [[parts2 objectAtIndex:1] componentsSeparatedByString:@"/"];
		int32_t subseconds = [[parts3 objectAtIndex:0] intValue];
		int32_t timescale = [[parts3 objectAtIndex:1] intValue];
		int64_t totaltime = (int64_t)timescale * (86400*days + 3600*hours + 60*minutes + seconds) + subseconds;
		//NSLog(@"For time %@, totaltime was %llu and timescale was %d.", timeString, totaltime, timescale);
		// CMTimeMake with a non-positive timescale returns an invalid CMTime, which propagates
		// through every later CMTime operation and is only noticed somewhere far away. A string
		// that parses to no timescale carries no time, so answer with zero rather than poison.
		if (timescale <= 0) return kCMTimeZero;
		return CMTimeMake(sign * totaltime, timescale);
	} @catch (id exception) {
		NSLog(@"Exception in CMTimeFromString processing string %@", timeString);
		return kCMTimeZero;
	}
	//    QTTime rawTime = QTTimeFromString(timeString);
	//    if ([timeString characterAtIndex:0] == '-') {
	//        QTTime zero = QTMakeTime(0,rawTime.timeScale);
	//        NSComparisonResult rawTimeComparedWithZero = QTTimeCompare(rawTime,zero);
	//        if (rawTimeComparedWithZero == NSOrderedDescending) {    // if QTTimeFromString returned a positive time from a negative string, fix it and return it.
	//            QTTime decrementedTime = QTTimeDecrement(zero,rawTime);
	//            return CMTimeMake((int64_t) decrementedTime.timeValue, (int32_t) decrementedTime.timeScale);
	//        }
	//    }
	//    return CMTimeMake((int64_t) rawTime.timeValue, (int32_t) rawTime.timeScale);
}

+ (NSPoint) project2DPoint:(NSPoint)pt usingMatrix:(double[9])A
{
	CBLAS_ORDER Order = CblasColMajor;			// passing the matrix A in the column-major form native to the Fortran function
	CBLAS_TRANSPOSE TransA = CblasNoTrans;		// don't do any transposing or anything with A
	int M = 3;						// rows in the matrix A
	int N = 3;						// columns in the matrix A
	double alpha = 1.0;				// scaler multiplier for A, set to 1.0 for no effect
	int lda = 3;					// the leading dimension of A
	double X[3] = {pt.x,pt.y,1.0};	// the screen coordinates x, expressed as homogeneous coordinates by adding the 3rd element 1.0
	int incX = 1;					// increment for X, should always be 0 in my case
	double beta = 0.0;				// scalar multiplier for y's initial value; set to 0 for this simple multiplication
	double Y[3];					// vector to hold the results of the computation
	int incY = 1;					// increment for Y, should always be 1 in my case
	cblas_dgemv(Order, TransA, M, N, alpha, A, lda, X, incX, beta, Y, incY);	// Compute the homogeneous 2D quadrat coordinates
	return NSMakePoint(Y[0]/Y[2],Y[1]/Y[2]);
}

+ (VSPoint3D) intersectionOfLine:(VSLine3D)line withPlaneDefinedByPoints:(VSPoint3D[3])pointsInPlane
{
	// Finds the point at which the given line in 3D space intersects the plane defined by the 3 3D points given in pointsInPlane
	// Set up the system of equations Ax=b described for the Parametric form on the Wikipedia page for "Line-plane intersection"
	// Source for the math:  http://en.wikipedia.org/wiki/Line-plane_intersection
	
	__CLPK_doublereal b[3] = {line.front.x - pointsInPlane[0].x,line.front.y - pointsInPlane[0].y,line.front.z - pointsInPlane[0].z};
	__CLPK_doublereal A[9];	// Elements of the matrix A, being filled in in Fortran column-major form
	A[0] = line.front.x - line.back.x;
	A[1] = line.front.y - line.back.y;
	A[2] = line.front.z - line.back.z;
	A[3] = pointsInPlane[1].x - pointsInPlane[0].x;
	A[4] = pointsInPlane[1].y - pointsInPlane[0].y;
	A[5] = pointsInPlane[1].z - pointsInPlane[0].z;
	A[6] = pointsInPlane[2].x - pointsInPlane[0].x;
	A[7] = pointsInPlane[2].y - pointsInPlane[0].y;
	A[8] = pointsInPlane[2].z - pointsInPlane[0].z;
	
	// Use Lapack's dgesv routine to solve the system Ax=b for x.
	
	__CLPK_integer n = 3;								// Number of linearly independent rows in the matrix A
	__CLPK_integer nrhs = 1;							// Number of columns of the matrix b (1, of course)
	__CLPK_integer lda = 3;								// Leading dimension of the matrix A
	__CLPK_integer ipiv[3];								// Output parameter, the pivot indices of the permutation matrix used for the solution
	__CLPK_integer ldb = 3;								// Leading dimension of the matrix b
	__CLPK_integer info;								// Output parameter: if 0, success; if -i, ith argument had illegal value; if >0, solution not computable
	dgesv_(&n, &nrhs, A, &lda, ipiv, b, &ldb, &info);	// On output, the variable b contains the solution x.
	
	double t = b[0];	// The first element of b should be the scaling parameter t for t he parametric equation
	
	VSPoint3D intersection;
	intersection.x = line.front.x + (line.back.x - line.front.x) * t;
	intersection.y = line.front.y + (line.back.y - line.front.y) * t;
	intersection.z = line.front.z + (line.back.z - line.front.z) * t;
	return intersection;
}


+ (VSPoint3D) intersectionOfNumber:(size_t)numLines of3DLines:(VSLine3D[])lines meanPLD:(double *)meanPLD
{
	// This calculates the closest point of approach of an arbitrary number of 3D lines.  The formula comes from Wikipedia.
	// It's the last formula on this page: http://en.wikipedia.org/wiki/Line-line_intersection

	if (numLines < 2) {  // fewer than 2 lines cannot define an intersection; matrix would be singular or zero
		*meanPLD = 0.0;
		VSPoint3D zero = {0.0, 0.0, 0.0};
		return zero;
	}

	// I need to first loop through and calculate the CPA.
	// Then, I can loop through the lines one by one and calculate their distances from the CPA, and average those to get the error index.

	double I_vvt[9] = {0,0,0,0,0,0,0,0,0};      // 3x3 matrix (as a row-by-row 9 vector) holding the running total of I_3x3 - v_i * Transpose(v_i)
	double I_vvtp[3] = {0,0,0};                 // 3-vector holding the running total of (I_3x3 - v_i * Transpose(v_i)).p
	double p[3];
	double v[3],d[3],dnorm;
	double A[9];
	double CPAvect[3];                          // Holds the answer to the closest point of approach (CPA), our estimate of the lines' intersection.
	VSPoint3D CPA;                              // Holds the answer as above but in a VSPoint3D struct
	
	// This loops over all lines keeping a running total of I - vvT, and (I - vvT)p and adds to them for every line.
	
	for (int i=0; i<numLines; i++) {
		d[0] = lines[i].back.x - lines[i].front.x;  // d is a vector along the ith line
		d[1] = lines[i].back.y - lines[i].front.y;
		d[2] = lines[i].back.z - lines[i].front.z;
		dnorm = cblas_dnrm2(3,d,1);
		v[0] = d[0]/dnorm;                          // v is a unit vector along the ith line
		v[1] = d[1]/dnorm;
		v[2] = d[2]/dnorm;
		A[0] = 1;                                   // reset A to the identity matrix each time; it will be overwritten with the result of the calculation
		A[1] = 0;
		A[2] = 0;
		A[3] = 0;
		A[4] = 1;
		A[5] = 0;
		A[6] = 0;
		A[7] = 0;
		A[8] = 1;
		
		cblas_dger(CblasColMajor,3,3,-1.0,v,1,v,1,A,3);
		
		for (int j=0; j<9; j++) {
			I_vvt[j] += A[j];                     // add the result of the calculation for I - v*Transpose(v) into the overall storage array before repeating the loop for other lines
		}
		p[0] = lines[i].front.x;
		p[1] = lines[i].front.y;
		p[2] = lines[i].front.z;
		
		cblas_dgemv(CblasColMajor, CblasNoTrans, 3, 3, 1.0, A, 3, p, 1, 1.0, I_vvtp, 1);	// This one line this line's values to the total of (I_3x3 - v_i * Transpose(v_i)).p
		
	}
	
	[VSCalibration invert3x3Matrix:I_vvt];  // Overwrites I_vvt with its inverse, using Lapack's dgetrf and dgetri functions.
	
	cblas_dgemv(CblasColMajor, CblasNoTrans, 3, 3, 1.0, I_vvt, 3, I_vvtp, 1, 0, CPAvect, 1);	// Multiplies the 3-vector I_vvtp by the 3x3 inverse of I_vvt to store the final result in CPAvect
	
	CPA.x = CPAvect[0];
	CPA.y = CPAvect[1];
	CPA.z = CPAvect[2];
	
	// Now the CPA calculation is completed; time to calculate the error estimate.
	
	double totalPLD = 0.0;  // Holds total point-line distance (PLD) from all the lines to their CPA
	for (int i=0; i<numLines; i++) {
		totalPLD += [UtilityFunctions distanceOfPoint:CPA fromLine:lines[i]];
	}
	*meanPLD = totalPLD / numLines;
	
	return CPA;
}

+ (double) distanceOfPoint:(VSPoint3D)point fromLine:(VSLine3D)line;
{
	// This function calculates the distance between a 3-D line and a 3-D point, using equation (6) from Mathworld's Point-Line Distance 3D page,
	// which is located here:  http://mathworld.wolfram.com/Point-LineDistance3-Dimensional.html
	// I use that equation rather than the shorter-form last one (equation 11) because there's no BLAS or Lapack function for the vector cross product.
	
	double x1_x0[3] = {line.front.x - point.x, line.front.y - point.y, line.front.z - point.z};
	double x2_x1[3] = {line.back.x - line.front.x, line.back.y - line.front.y, line.back.z - line.front.z};
	double x1_x0_nrm = cblas_dnrm2(3,x1_x0,1);
	double x2_x1_nrm = cblas_dnrm2(3,x2_x1,1);
	if (x2_x1_nrm == 0.0) return 0.0;  // degenerate zero-length line; distance is undefined, return 0
	double dotprod = cblas_ddot(3, x1_x0, 1, x2_x1, 1);
	double dsquared = (x1_x0_nrm * x1_x0_nrm * x2_x1_nrm * x2_x1_nrm - dotprod*dotprod) / (x2_x1_nrm*x2_x1_nrm);
	return sqrt(fmax(0.0, dsquared));  // fmax guards against small negative values from floating-point rounding
}


+ (VSPointPair2D) extendLine:(VSPointPair2D)lineSegment toFillFrameOfClip:(VSVideoClip *)videoClip didFitInFrame:(bool *)didFit;
{ 
	// Extends the line by putting it in slope-intercept form y = mx + b and solving for intersections with the video edges
	// It won't work if any of the lines being extended are 100% parallel to the video edges, but that shouldn't come up in practice in this program.
	NSSize movieSize = videoClip.windowController.movieSize;
	NSPoint p1 = lineSegment.p1;
	NSPoint p2 = lineSegment.p2;
	double m = (p2.y - p1.y) / (p2.x - p1.x);
	double b = p1.y - m * p1.x;
	// Find the four crossing points at which the line being extended should cross the lines including and extending from the movie edges.
	NSPoint c1 = NSMakePoint(movieSize.width,m*movieSize.width+b);
	NSPoint c2 = NSMakePoint(0.0,b);
	NSPoint c3 = NSMakePoint((movieSize.height-b)/m,movieSize.height);
	NSPoint c4 = NSMakePoint(-b/m,0.0);
	// Only two of those crossings should be within the boundary of the movie rectangle.  Find those two and add them to an array.
	NSPoint c[2];
	int i = 0;
	if (c1.y >= 0 && c1.y <= movieSize.height) {c[i] = c1; i += 1;};
	if (c2.y >= 0 && c2.y <= movieSize.height) {c[i] = c2; i += 1;};
	if (c3.x >= 0 && c3.x <= movieSize.width) {c[i] = c3; i += 1;};
	if (c4.x >= 0 && c4.x <= movieSize.width) {c[i] = c4; i += 1;};
	if (i == 2) {														// If we found exactly 2 crossings, all is good; format and return result.
		*didFit = YES;
		VSPointPair2D newLineSegment;
		newLineSegment.p1 = c[0];
		newLineSegment.p2 = c[1];
		return newLineSegment;
	} else {	// If the line segment doesn't cross into the clip's frame at all, just return the segment
		*didFit = NO;
		return lineSegment;
	}
}

+ (float) randomFloatBetween:(float)float1 and:(float)float2
{
	double arc4random_max = 0x100000000;
	return ((float) arc4random() / (float) arc4random_max) * (float2 - float1) + float1;
}

+ (NSString *)stringFromMatrix:(double[])M withRows:(int)numRows andCols:(int)numCols
{
	// Prints a matrix in normal readable 2D row-major form, based on the input matrix represented in the 1D column-major form used for blas and lapack
	NSMutableString *str = [NSMutableString stringWithString:@"\n"];
	for (int i=0; i<numRows; i++) {
		for (int j=0; j<numCols; j++) {
			[str appendFormat:@"%1.4f   ",M[j*numRows+i]];
		}
		[str appendString:@"\n"];
	}
	return str;
}

+ (NSString *)sanitizeFileNameString:(NSString *)fileName {
	NSCharacterSet* illegalFileNameCharacters = [NSCharacterSet characterSetWithCharactersInString:@"/\\?%*|\"<>"];
	return [[fileName componentsSeparatedByCharactersInSet:illegalFileNameCharacters] componentsJoinedByString:@""];
}

#pragma mark Clone an NSManagedObject
#pragma mark

// Modified from http://stackoverflow.com/questions/2730832/how-can-i-duplicate-or-copy-a-core-data-managed-object
// added a "deep" boolean parameter which says whether or not to also copy child objects and parent relationships

+(NSManagedObject *) Clone:(NSManagedObject *)source inContext:(NSManagedObjectContext *)context deep:(BOOL)deep
{
	NSString *entityName = [[source entity] name];
	NSManagedObject *cloned = [NSEntityDescription insertNewObjectForEntityForName:entityName inManagedObjectContext:context];
	NSDictionary *attributes = [[NSEntityDescription entityForName:entityName inManagedObjectContext:context] attributesByName];
	for (NSString *attr in attributes) [cloned setValue:[source valueForKey:attr] forKey:attr];
	if (deep) {
		//Loop through all relationships, and clone them.
		NSDictionary *relationships = [[NSEntityDescription entityForName:entityName inManagedObjectContext:context] relationshipsByName];
		for (NSRelationshipDescription *rel in relationships){
			NSString *keyName = [NSString stringWithFormat:@"%@",rel];
			//get a set of all objects in the relationship
			NSMutableSet *sourceSet = [source mutableSetValueForKey:keyName];
			NSMutableSet *clonedSet = [cloned mutableSetValueForKey:keyName];
			NSEnumerator *e = [sourceSet objectEnumerator];
			NSManagedObject *relatedObject;
			while ( relatedObject = [e nextObject]){
				//Clone it, and add clone to set
				NSManagedObject *clonedRelatedObject = [UtilityFunctions Clone:relatedObject inContext:context deep:deep];
				[clonedSet addObject:clonedRelatedObject];
			}
		}
	}
	
	return cloned;
}

@end
