/*
 *  UnusedCode.c
 *  VidSync
 *
 *  Created by Jason Neuswanger on 11/17/09.
 *  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
 *
 *	This file is designed to hold code that was tricky to get working and might be useful for future reference, but isn't currently used.
 *	Everything in it should be commented out.
 *
 */

/* pile of unused stuff, saving before changing
 
- (void) drawQuadratCoordinateGrids
{
	BOOL shouldDrawFront = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratShowSurfaceGridOverlayFront"] boolValue];
	BOOL shouldDrawBack = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratShowSurfaceGridOverlayBack"] boolValue];
	NSColor *frontColor = [UtilityFunctions unarchiveColorFromData:[[NSUserDefaults standardUserDefaults] dataForKey:@"quadratOverlayColorFront"]];
	NSColor *backColor = [UtilityFunctions unarchiveColorFromData:[[NSUserDefaults standardUserDefaults] dataForKey:@"quadratOverlayColorBack"]];
	if ((shouldDrawFront || shouldDrawBack) && quadratCoordinateGrids == nil) {	// quadratCoordinateGrids holds a multidimensional array of NSBezierPaths representing all the grid lines
		[self calculateQuadratCoordinateGrids];
	}
	if (shouldDrawFront) {
		[frontColor setStroke];
		for (NSArray *directionArray in [quadratCoordinateGrids objectAtIndex:0]) {
			[directionArray enumerateObjectsWithOptions:NSEnumerationConcurrent usingBlock:^(id obj, NSUInteger idx, BOOL *stop) {	// parallel loop over all the front surface NSBezierPaths
			 [obj stroke];
			 }];			
		}
	}
	if (shouldDrawBack) {
		[backColor setStroke];
		for (NSArray *directionArray in [quadratCoordinateGrids objectAtIndex:1]) {
			[directionArray enumerateObjectsWithOptions:NSEnumerationConcurrent usingBlock:^(id obj, NSUInteger idx, BOOL *stop) {  // parallel loop over all the back surface NSBezierPaths
			 [obj stroke];
			 }];
		}
	}		
}

- (void) calculateQuadratCoordinateGrids
{
	quadratCoordinateGrids = [NSArray arrayWithObjects:
							  [NSArray arrayWithObjects:
							   [self createQuadratCoordinateGridSectionForSurface:@"Front" axis:0 direction:1],
							   [self createQuadratCoordinateGridSectionForSurface:@"Front" axis:0 direction:-1],
							   [self createQuadratCoordinateGridSectionForSurface:@"Front" axis:1 direction:1],
							   [self createQuadratCoordinateGridSectionForSurface:@"Front" axis:1 direction:-1],
							   nil],
							  [NSArray arrayWithObjects:
							   [self createQuadratCoordinateGridSectionForSurface:@"Back" axis:0 direction:1],
							   [self createQuadratCoordinateGridSectionForSurface:@"Back" axis:0 direction:-1],
							   [self createQuadratCoordinateGridSectionForSurface:@"Back" axis:1 direction:1],
							   [self createQuadratCoordinateGridSectionForSurface:@"Back" axis:1 direction:-1],
							   nil],
							  nil];	
}

- (NSArray *) createQuadratCoordinateGridSectionForSurface:(NSString *)surface axis:(int)axis direction:(int)dir
{
	// Returns an NSArray of NSBezierPaths representing all the grid lines for the appropriate axis & direction.
	NSArray *outPathsArray = [NSArray array];
	float gridSpacing = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratGridOverlayLineSpacing"] floatValue];
	float lineWidth = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"quadratGridOverlayLineThickness"] floatValue];
	VSPointPair2D lineTips;
	VSPointPair2D pt;
	NSPoint p1q,p2q;
	VideoWindowController *vwc = delegate;	
	NSArray *projectionMatrix;
	if ([surface isEqualToString:@"Front"]) {
		projectionMatrix = vwc.videoClip.calibration.matrixQuadratFrontToScreen;
	} else {	// surface must be @"Back"
		projectionMatrix = vwc.videoClip.calibration.matrixQuadratBackToScreen;
	}
	bool didFit = true;
	float i = 0.0;
	while (didFit) {
		// Create a line segment in quadrat coordinates with the correct direction and position along the axis.
		if (axis == 0) {			// pass axis = 0 to move along the x axis, creating lines in the y direction
			p1q = NSMakePoint(i,0.0);
			p2q = NSMakePoint(i,0.1);
		} else {					// pass axis = 1 to move along the y axis, creating lines in the x direction 
			p1q = NSMakePoint(0.0,i);
			p2q = NSMakePoint(0.1,i);
		}
		// Convert the line segment from quadrat coordinates into screen coordinates, extend it to fill the frame, and increment i for the next segment
		pt.p1 = [UtilityFunctions project2DPoint:p1q usingMatrix:projectionMatrix];	// convert pt from quadrat coordinates
		pt.p2 = [UtilityFunctions project2DPoint:p2q usingMatrix:projectionMatrix];	// into screen coordinates
		lineTips = [UtilityFunctions extendLine:pt toFillFrameOfClip:vwc.videoClip didFitInFrame:&didFit];		
		if (didFit) {	// if the current line crosses into the video screen, draw it
			NSPoint line[2];
			line[0] = [vwc convertVideoToOverlayCoords:lineTips.p1];
			line[1] = [vwc convertVideoToOverlayCoords:lineTips.p2];
			NSBezierPath *path = [NSBezierPath bezierPath];	
			[path appendBezierPathWithPoints:line count:2];
			if (i == 0.0) {
				if (dir == 1) {	// doing this so I don't waste resources drawing the axis lines twice
					[path setLineWidth:lineWidth*2.0];
					outPathsArray = [outPathsArray arrayByAddingObject:path];
				}
			} else {
				[path setLineWidth:lineWidth];
				outPathsArray = [outPathsArray arrayByAddingObject:path];
			}
			
		}
		i += dir*gridSpacing;	// pass dir = 1 to move in a positive direction, dir = -1 to move in a negative direction
	}
	return outPathsArray;
}


*/

/*
 + (void) FillMatrixOfCArrays:(double[3][3])outArr FromNSArray:(NSArray *)ns		// Used for retrieving stored projection matrices from Core Data.
 {
 outArr[0][0] = [[[ns objectAtIndex:0] objectAtIndex:0] doubleValue];
 outArr[0][1] = [[[ns objectAtIndex:0] objectAtIndex:1] doubleValue];
 outArr[0][2] = [[[ns objectAtIndex:0] objectAtIndex:2] doubleValue];
 outArr[1][0] = [[[ns objectAtIndex:1] objectAtIndex:0] doubleValue];
 outArr[1][1] = [[[ns objectAtIndex:1] objectAtIndex:1] doubleValue];
 outArr[1][2] = [[[ns objectAtIndex:1] objectAtIndex:2] doubleValue];
 outArr[2][0] = [[[ns objectAtIndex:2] objectAtIndex:0] doubleValue];
 outArr[2][1] = [[[ns objectAtIndex:2] objectAtIndex:1] doubleValue];
 outArr[2][2] = [[[ns objectAtIndex:2] objectAtIndex:2] doubleValue];
 }
 */


/*
 
 void VSCreateMatrixOfCArraysFromNSArray(NSArray *ns, double out[3][3])
 {
 out[0][0] = [[[ns objectAtIndex:0] objectAtIndex:0] doubleValue];
 out[0][1] = [[[ns objectAtIndex:0] objectAtIndex:1] doubleValue];
 out[0][2] = [[[ns objectAtIndex:0] objectAtIndex:2] doubleValue];
 out[1][0] = [[[ns objectAtIndex:1] objectAtIndex:0] doubleValue];
 out[1][1] = [[[ns objectAtIndex:1] objectAtIndex:1] doubleValue];
 out[1][2] = [[[ns objectAtIndex:1] objectAtIndex:2] doubleValue];
 out[2][0] = [[[ns objectAtIndex:2] objectAtIndex:0] doubleValue];
 out[2][1] = [[[ns objectAtIndex:2] objectAtIndex:1] doubleValue];
 out[2][2] = [[[ns objectAtIndex:2] objectAtIndex:2] doubleValue];
 }
 
 NSArray * VSCreateMatrixOfNSArraysFromCMatrix(double m[3][3])
 {
 return [NSArray arrayWithObjects:
 [NSArray arrayWithObjects:
 [NSNumber numberWithDouble:m[0][0]],
 [NSNumber numberWithDouble:m[0][1]],
 [NSNumber numberWithDouble:m[0][2]],nil
 ],
 [NSArray arrayWithObjects:
 [NSNumber numberWithDouble:m[1][0]],
 [NSNumber numberWithDouble:m[1][1]],
 [NSNumber numberWithDouble:m[1][2]],nil
 ],
 [NSArray arrayWithObjects:
 [NSNumber numberWithDouble:m[2][0]],
 [NSNumber numberWithDouble:m[2][1]],
 [NSNumber numberWithDouble:m[2][2]],nil
 ],nil];	
 }
 
 */

/* Just a trivial working BLAS example
 
 float x[3] = {3.0,4.0,5.0};
 float y[3] = {10.0,10.0,10.0};
 float result;
 result = cblas_sdot(3,x,1,y,1);
 NSLog(@"result is %f",result);
 
 */

/*
 
 // Use BLAS function cblas_sgemm to calculate ATA, which is Transpose(A) * A.	This function works, but Lapack's functionality made it unnecessary.
 
 float ATA[9][9] = {0.0};
 cblas_sgemm(CblasRowMajor,CblasTrans,CblasNoTrans,9,9,numRows,1.0f, (float *) A,9, (float *) A,9,0.0f, (float *) ATA,9);
 //	for (int k = 0; k < 9; k++) {
 //		NSLog(@"%1.2f %1.2f %1.2f %1.2f %1.2f %1.2f %1.2f %1.2f %1.2f",ATA[k][0],ATA[k][1],ATA[k][2],ATA[k][3],ATA[k][4],ATA[k][5],ATA[k][6],ATA[k][7],ATA[k][8],ATA[k][9]);
 //	}
 
 */
/*
- (void) calculateDistortionCorrectionOld
{
	// I sort the lines so I can assign each one the correct lambda after doing the calculation, and see which lines might have produced outlier lambdas
	NSArray *plumbLines = [self.distortionLines allObjects];
	int numLines = [plumbLines count];	// later, filter it out to the ones with at least 3 points first, and run an alert/return if there still aren't enough
	double ABCs[numLines][3];			// store them row-major	
	int numPointsInLine;
	NSPoint currentPoint;
	double MTMInv[9];	// Inverse of Transpose(M)*M							use DGEMM for Transpose(M)*M, then invert3x3Matrix wrapper to clapack's dgetrf_ and dgetri_
	double MTb[3];		// Transpose(M)*b										use DGEMV
	double ABC[3];		// Inverse(Transpose(M) * M) * Transpose(M) * b			use DGEMV
	
	for (int j = 0; j < numLines; j++) {		// pointArray is an NSArray of NSPoints defining one line that should be straight in the corrected coordinates		
		NSArray *pointsInLine = [[[plumbLines objectAtIndex:j] distortionPoints] allObjects];
		numPointsInLine = [pointsInLine count];
		double M[numPointsInLine * 3];
		double b[numPointsInLine];
		for (int i = 0; i < numPointsInLine; i++) {
			currentPoint = NSMakePoint([[[pointsInLine objectAtIndex:i] screenX] floatValue],[[[pointsInLine objectAtIndex:i] screenY] floatValue]);
			M[i] = currentPoint.x;
			M[i+numPointsInLine] = currentPoint.y;
			M[i+2*numPointsInLine] = 1;
			b[i] = -(currentPoint.x*currentPoint.x + currentPoint.y*currentPoint.y);
		}		
		
		// The next four lines calculate equation (16)			
		cblas_dgemm(CblasColMajor,CblasTrans,CblasNoTrans, 3, 3, numPointsInLine, 1.0, M, numPointsInLine, M, numPointsInLine, 0.0, MTMInv, 3);	// after this, MTMInv contains 3x3 matrix Transpose(M)*M						
		[VSCalibration invert3x3Matrix:MTMInv];														// now MTMInv contains the 3x3 matrix Inverse(Transpose(M)*M)		
		cblas_dgemv(CblasColMajor,CblasTrans, numPointsInLine, 3, 1.0, M, numPointsInLine, b, 1, 0.0, MTb, 1);	// after this, MTb contains 3-element vector Transpose(M)*b
		cblas_dgemv(CblasColMajor,CblasNoTrans, 3, 3, 1.0, MTMInv, 3, MTb, 1, 0.0, ABC, 1);			// after this, 3-element vector ABC contains the parameters A, B, and C for the circle fit
		
		// store the circle-fit coefficients A, B, and C for later use
		ABCs[j][0] = ABC[0];
		ABCs[j][1] = ABC[1];
		ABCs[j][2] = ABC[2];
	}
    
	// Let N be the number of unique pairwise comparisons of the straightlines.  We loop over all of them to solve by Ax=b by least squares, where x is {x0,x1}, the center of distortion
	// Construct the linear system Ax=b, where A is an Nx2 matrix with entries (Ai - Aj     Bi - Bj) and b is an Nx1 vector (Cj - Ci)
	// First, I have to figure out N in order to size my arrays, so I do this by looping over the same indices quick and counting up the entries.
	int N = 0;
	for (int i = 0; i < numLines-1; i++) {
		for (int j = i+1; j < numLines; j++) {
			N++;
		}
	}	
	__CLPK_doublereal A[N*2];
	__CLPK_doublereal b[N];
	int k = 0;
	for (int i = 0; i < numLines-1; i++) {
		for (int j = i+1; j < numLines; j++) {
			A[k] = ABCs[i][0] - ABCs[j][0];
			A[N+k] = ABCs[i][1] - ABCs[j][1];
			b[k] = ABCs[j][2] - ABCs[i][2];
			k++;
		}
	}
    
	char trans = 'N';
	__CLPK_integer m = N;		// rows in A
	__CLPK_integer n = 2;		// cols in A
    __CLPK_integer nrhs = 1;	// columns on right hand side
	__CLPK_integer lda = m; 
	__CLPK_integer ldb = m;
	__CLPK_integer lwork = -1;
	__CLPK_doublereal *work = (__CLPK_doublereal*)malloc(sizeof(__CLPK_doublereal));        // Array with room for 1 item, for the workspace query answer
	__CLPK_integer info;
    dgels_(&trans, &m, &n, &nrhs, A, &lda, b, &ldb, work, &lwork, &info);                   // workspace query, places ideal workspace size in work[0]
	__CLPK_integer idealWorkLength = work[0];
    __CLPK_doublereal *idealWork = (__CLPK_doublereal*)malloc(idealWorkLength*sizeof(__CLPK_doublereal));
    dgels_(&trans, &m, &n, &nrhs, A, &lda, b, &ldb, idealWork, &idealWorkLength, &info);	// solve overdermined Ax=b by least squares
    
	double x0 = b[0];
	double y0 = b[1];
	double lambdas[numLines];
	for (int i=0; i < numLines; i++) {
		lambdas[i] = 1.0 / ( x0*x0 + y0*y0 + ABCs[i][0]*x0 + ABCs[i][1]*y0 + ABCs[i][2]);
		[[plumbLines objectAtIndex:i] setLambda:[NSNumber numberWithDouble:lambdas[i]]];
	}
    
	double meanLambda = 0.0;
	for (int i = 0; i < numLines; i ++) meanLambda += lambdas[i] / numLines;
        
        // I could make these precision and increments configurable by the user, but I think it would just be confusing and useless.  Starting out with increments of 
        // 1.0e-7 can find any refined lambda within 1.0e-6 of meanLambda, which should always include the correct value.  Really, an increment of 1.0e-7 should include the 
        // correct value, but it doesn't cost much to expand the search by an order of magnitude (and one function iteration) out of caution.  Likewise, the precision I've set
        // goes out to 3 significant digits on my lambdas in the 10e-8 range, which is more than what makes any kind of practical difference.  Going to a pointlessly higher
        // precision just makes the algorithm take longer to run and has no important effect.
        self.distortionCenterX = [NSNumber numberWithDouble:x0];
        self.distortionCenterY = [NSNumber numberWithDouble:y0];
        self.distortionLambda = [NSNumber numberWithDouble:meanLambda];
        double refinedLambda = [self refinedLambdaStartingFrom:meanLambda toPrecision:1.0e-10 usingIncrements:1.0e-7];    
        self.distortionLambda = [NSNumber numberWithDouble:refinedLambda];	
        
        [self.videoClip.project.document refreshOverlaysOfAllClips:self];
}

- (NSArray *) straightLinesFromQuadratSurface:(NSString *)whichSurface		// need to do these separately for each surface, then combine the two
{
	NSSet *points;
	if ([whichSurface isEqualToString:@"Front"]) {
		points = self.pointsFront;
	} else {
		points = self.pointsBack;
	}
	
	NSMutableDictionary *hDict = [NSMutableDictionary new];		// dictionary to hold vertical lines, specified as those with a constant horizontal real-world quadrat coordinate
	NSMutableDictionary *vDict = [NSMutableDictionary new];		// holds horizontal lines, defined by constant vertical coordinates
    
	NSValue *pointValue;
	for (VSCalibrationPoint *point in points) {
		
		if ([hDict objectForKey:point.worldHcoord] != nil) {										// if there is an existing real-world vertical line for h = worldHcoord, use it
			pointValue = [NSValue valueWithPoint:NSMakePoint([point.screenX floatValue],[point.screenY floatValue])];
			[[hDict objectForKey:point.worldHcoord] addObject:pointValue];							// and add the point to the array for an existing current vertical line
		} else {
			pointValue = [NSValue valueWithPoint:NSMakePoint([point.screenX floatValue],[point.screenY floatValue])];
			[hDict setObject:[NSMutableArray arrayWithObject:pointValue] forKey:point.worldHcoord];		// otherwise, create an array in the dictionary for a new vertical line
		}
		
		if ([vDict objectForKey:point.worldVcoord] != nil) {										// if there is an existing real-world vertical line for h = worldHcoord, use it
			pointValue = [NSValue valueWithPoint:NSMakePoint([point.screenX floatValue],[point.screenY floatValue])];
			[[vDict objectForKey:point.worldVcoord] addObject:pointValue];							// and add the point to the array for an existing current vertical line
		} else {
			pointValue = [NSValue valueWithPoint:NSMakePoint([point.screenX floatValue],[point.screenY floatValue])];
			[vDict setObject:[NSMutableArray arrayWithObject:pointValue] forKey:point.worldVcoord];		// otherwise, create an array in the dictionary for a new vertical line
		}
		
	}
	
	// After constructing the array, the dictionary and keys are no longer needed, so discard them and flatten the H and V collection into a single NSArray of NSArrays of NSValues holding points
	// Also here, filter out those line arrays that contain less than 3 points and are therefore useless for distortion correction.
	
	NSMutableArray *allLines = [NSMutableArray new];
	NSEnumerator *hEnumerator = [hDict objectEnumerator];
	NSEnumerator *vEnumerator = [vDict objectEnumerator];
	NSArray *lineArray;
	while (lineArray = [hEnumerator nextObject]) if ([lineArray count] > 2) [allLines addObject:lineArray];
	while (lineArray = [vEnumerator nextObject]) if ([lineArray count] > 2) [allLines addObject:lineArray];
	return allLines;		
}
*/

/*	

 // Use Lapack's sgelss function to minimize the 2-norm of ||b-A*x|| (although in this case b is all zeros)
 // The problem with this approach is that with b = {0,0,0,...} it gives the trivial solution x = {0,0,0...}
 // However, the right answer is contained in the ninth right-singular vector, which is overwritten into A,
 // so this code's output DOES contain the correct projection matrix.  It just doesn't do it as smoothly as the 
 // dedicated SVD function sgesvd that I'm actually using in VSCalibration.m
 
 __CLPK_integer m = numRows;					// rows in the matrix
 __CLPK_integer n = 9;						// columns in the matrix
 __CLPK_integer nrhs = 1;					// number of columns on the right-hand side (in this case, just one column of 9 zeros)
 __CLPK_real *a;								// contains the m x n matrix A on input; on output, overwritten with right-singular vectors stored row-wise
 __CLPK_integer lda = numRows;				// the first dimension of A
 __CLPK_real *b;								// contains the m x nrhs matrix b on input; on output, overwritten by n x nrhs solution matrix x
 __CLPK_integer ldb = numRows;				// the first dimension of B
 __CLPK_real *s;								// output parameter: matrix for the singular values of A
 __CLPK_real rcond = 0.0000001;				// determines effective rank of A; singular values smaller than rcond are treated as 0
 __CLPK_integer rank;						// output parameter: rank of the matrix A
 __CLPK_real *work;							// workspace array; I'm not sure what it's used for
 __CLPK_integer lwork = 32*numRows*9;		// length of the work array; value of -1 means "a workspace query is assumed" -- some sort of automatic value?
 __CLPK_integer info;						// output parameter: if 0, execution successful; if -i, the ith param was illegal; if i, failed to converge 
 a = malloc( 9 * numRows * sizeof(__CLPK_real) );
 b = malloc( numRows * sizeof(__CLPK_real) );
 s = malloc( 9 * sizeof(__CLPK_real) );
 work = malloc( lwork*sizeof(__CLPK_real) );
 // Put the values from A into a stupid Fortran one-dimensional column-major form for the clapack function.  Also initialize b to a vector of zeros.
 for (int v=0; v < 9; v++) {
 for (int u=0; u < numRows; u++) {
 a[v*numRows+u] = A[u][v];
 }
 }
 for (int j = 0; j < numRows; j++) b[j] = 0.0;
 sgelss_(&m, &n, &nrhs, a, &lda, b, &ldb, s, &rcond, &rank, work, &lwork, &info);
 NSLog(@"Completed sgelss_ with info %i.",info);
 NSLog(@"Singular values: %1.3f   %1.3f   %1.3f   %1.3f   %1.3f   %1.3f   %1.3f   %1.3f   %1.3f",s[0],s[1],s[2],s[3],s[4],s[5],s[6],s[7],s[8]);
 NSLog(@"%1.3f   %1.3f   %1.3f",b[0],b[1],b[2]);
 NSLog(@"%1.3f   %1.3f   %1.3f",b[3],b[4],b[5]);
 NSLog(@"%1.3f   %1.3f   %1.3f",b[6],b[7],b[8]);	
 for (int z = 0; z < 9; z++) NSLog(@"%1.7f %1.7f %1.7f %1.7f %1.7f %1.7f %1.7f %1.7f %1.7f",a[z+0],a[z+numRows],a[z+2*numRows],a[z+3*numRows],a[z+4*numRows],a[z+5*numRows],a[z+6*numRows],a[z+7*numRows],a[z+8*numRows]);
 free(a);
 free(b);
 free(s);
 free(work);
 
 */

/* Here I'm commenting out a version of autodetectChessboardPlumblines that works well for a complete, properly sized board, with the recommeded white border, so that I can
 experiment more with the new version of the function below looking for something that works across the screen.
 
 - (void) autodetectChessboardPlumblines
 {
 NSLog(@"Autodetecting chessboard plumblines.");
 //NSImage *videoFrameNS = [self.videoClip.project.document stillNSImageFromVSVideoClip:self.videoClip atMasterTime:[self.videoClip.project.document currentMasterTime]];
 
 //NSString* imageName = [[NSBundle mainBundle] pathForResource:@"2010-09-15-2 - Chessboard - Left Camera" ofType:@"jpg"];
 NSString* imageName = [[NSBundle mainBundle] pathForResource:@"MyFixedChessboard_28x13" ofType:@"jpg"];
 NSImage* videoFrameNS = [[NSImage alloc] initWithContentsOfFile:imageName];
 
 // My process here of converting Video -> NSImage -> CGImage -> IplImage -> CGImage -> NSImage messes with the colors, but that probably doesn't matter for this purpose.
 CGImageSourceRef source;
 source = CGImageSourceCreateWithData((CFDataRef)[videoFrameNS TIFFRepresentation], NULL);
 CGImageRef videoFrameCG =  CGImageSourceCreateImageAtIndex(source, 0, NULL);
 IplImage *videoFrameIpl = (IplImage *) [UtilityFunctions CreateIplImageFromCGImage:videoFrameCG];
 
 IplImage* videoFrameSingleChannelIpl = cvCreateImage(cvGetSize(videoFrameIpl), videoFrameIpl->depth, 1);
 cvSetImageCOI(videoFrameIpl, 1);
 cvCopy(videoFrameIpl, videoFrameSingleChannelIpl);
 
 int width=26;
 int height=11;
 CvSize sz = cvSize(width,height); // (chessboard corners per row, corners per column)
 
 // Okay, now it works pretty well with a clear chessboard and correct corners.  If I tell it to expect one extra row, it fails in the same way it has when I try
 // an unedited full-screen chessboard.  I could fix this by recompiling my own custom version of OpenCV, or using the old version from CVOCV.
 // One weird thing is that found = 0, even when the function is working.
 // First, see if the subpixel corners function improves things much, if it really is run internally.
 // I could try using some other corner detection methods here, too... look inside the cvFindChessboardCorners function to see what they use, and see here for some 
 // separate recommendations: http://www.aishack.in/2010/05/subpixel-corners-in-opencv/
 // 
 
 int chessboardStatus = cvCheckChessboard(videoFrameSingleChannelIpl, sz);
 NSLog(@"Chessboard status is %d.",chessboardStatus);    // Should be -1 for errors; 0 for no chessboard detected; 1 for chessboard detected
 
 if (chessboardStatus == 1) {
 CvPoint2D32f *foundCorners = (CvPoint2D32f*)malloc((width*height + 1) * sizeof(CvPoint2D32f)); 
 int numFoundCorners = 0;
 int flags = CV_CALIB_CB_ADAPTIVE_THRESH | CV_CALIB_CB_NORMALIZE_IMAGE;
 int found = cvFindChessboardCorners(videoFrameSingleChannelIpl, sz, foundCorners, &numFoundCorners, flags);
 
 NSLog(@"Variable found is %d, corner count is %d corners.  Refining subpixels...",found,numFoundCorners);
 
 // Running cvFindCornerSubPix with a high window size like (15,15) corrected some severe mislocations around one of my squares that (5,5) did not.
 cvFindCornerSubPix(videoFrameSingleChannelIpl, foundCorners, numFoundCorners, cvSize(15,15), cvSize(-1,-1), cvTermCriteria( CV_TERMCRIT_ITER | CV_TERMCRIT_EPS, 20, 0.01 ));
 
 NSLog(@"First corner found is %1.5f,%1.5f",foundCorners[0].x,foundCorners[0].y);
 NSLog(@"Second corner found is %1.5f,%1.5f",foundCorners[1].x,foundCorners[1].y);
 NSLog(@"Third corner found is %1.5f,%1.5f",foundCorners[2].x,foundCorners[2].y);
 
 
 cvDrawChessboardCorners(videoFrameIpl, sz, foundCorners, numFoundCorners, found);        
 
 }
 
 CGImageRef videoFrameResultCG = [UtilityFunctions CGImageFromIplImage:videoFrameIpl];
 NSImage *videoFrameResultNS = [[NSImage alloc] initWithCGImage:videoFrameResultCG size:NSMakeSize(1920.,1080.)];
 [self.videoClip.project.document.tempOpenCVView setImage:videoFrameResultNS];
 } */
