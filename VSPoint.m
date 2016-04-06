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


#import "VSPoint.h"
#import "UtilityFunctions.h"
#import "gsl/gsl_multiroots.h"

double pointSolverCostFunction_f(const gsl_vector* x, void* params) {
    const VSPointSolverParams* p = (VSPointSolverParams *) params;
    VSLine3D lineToCamera;
    lineToCamera.front.x = gsl_vector_get(x, 0);    // this is the candidate 3D point
    lineToCamera.front.y = gsl_vector_get(x, 1);
    lineToCamera.front.z = gsl_vector_get(x, 2);
    double cost = 0.0;
    VSPoint3D frontQuadratPoint3D;
    NSPoint frontQuadratPoint2D,reprojectedScreenPoint;
    for (int i = 0; i < p->numCameras; i++) {  // Loop over all videos / camera views
        // Construct the camera side of the line from the candidate 3-D point through the camera
        lineToCamera.back.x = p->camPositions[i].x;
        lineToCamera.back.y = p->camPositions[i].y;
        lineToCamera.back.z = p->camPositions[i].z;
        // Calculate the 3-D point intersection of that line with the front quadrat plane, and express it as a 2-D point in that plane
        frontQuadratPoint3D = linePlaneIntersect(lineToCamera, p->frontFacePlanes[i]);                                      // function defined in this file, below
        frontQuadratPoint2D = quadratCoords2Dfrom3D(&frontQuadratPoint3D,p->axesHorizontal[i],p->axesVertical[i]);	// function defined in VSEventScreenPoint.h	
        // project the front quadrat point onto the undistorted screen
        reprojectedScreenPoint = project2DPoint(frontQuadratPoint2D, p->quadratFrontToScreenFCMMatrices[i]);
        // add the distance between the input screen point (already undistorted) and reprojected screen point (inherently undistorted) to the cost function
        cost += pow(reprojectedScreenPoint.x - p->undistortedScreenPoints[i].x, 2) + pow(reprojectedScreenPoint.y - p->undistortedScreenPoints[i].y, 2);
    }
    return cost;
}

VSPoint3D linePlaneIntersect(VSLine3D line, VSPoint3D pointsInPlane[3]){
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

NSPoint project2DPoint(NSPoint pt, double projectionMatrix[9])
{
	enum CBLAS_ORDER Order = CblasColMajor;			// passing the matrix A in the column-major form native to the Fortran function
	enum CBLAS_TRANSPOSE TransA = CblasNoTrans;		// don't do any transposing or anything with A
	int M = 3;						// rows in the matrix A
	int N = 3;						// columns in the matrix A
	double alpha = 1.0;				// scaler multiplier for A, set to 1.0 for no effect
	int lda = 3;					// the leading dimension of A
	double X[3] = {pt.x,pt.y,1.0};	// the screen coordinates x, expressed as homogeneous coordinates by adding the 3rd element 1.0
	int incX = 1;					// increment for X, should always be 0 in my case
	double beta = 0.0;				// scalar multiplier for y's initial value; set to 0 for this simple multiplication
	double Y[3];					// vector to hold the results of the computation
	int incY = 1;					// increment for Y, should always be 1 in my case
	cblas_dgemv(Order, TransA, M, N, alpha, projectionMatrix, lda, X, incX, beta, Y, incY);	// Compute the homogeneous 2D quadrat coordinates
	return NSMakePoint(Y[0]/Y[2],Y[1]/Y[2]);
}

@implementation VSPoint

@dynamic index;
@dynamic timecode;
@dynamic worldX;
@dynamic worldY;
@dynamic worldZ;
@dynamic meanPLD;
@dynamic screenPoints;
@dynamic reprojectionErrorNorm;
@dynamic nearestCameraDistance;
@dynamic trackedEvent;

#pragma mark

- (void) handleScreenPointChange
{
    for (VSPoint *point in self.trackedEvent.points) [point clearPointToPointDistanceCache];        // clear the distance cache for this point and others that may connect to it
	VidSyncDocument *doc = [[[self.trackedEvent.trackedObjects anyObject] project] document];
	[self calculate3DCoords];
	if ([self.screenPoints count] == 0) [[self managedObjectContext] deleteObject:self]; // if the point now has no screenpoints, delete it
	[doc.eventsPointsController.mainTableView setNeedsDisplay];	// refresh the point table
	[doc.trackedEventsController.mainTableView setNeedsDisplayInRect:[doc.trackedEventsController.mainTableView rectOfColumn:4]];	// refresh the event table's # Points column
}

- (void) clearPointToPointDistanceCache
{
	[pointToPointDistanceCache removeAllObjects];	// Clear the cache of point-to-point distances, so they'll be recalculated with the new coordinates when asked for.
}

- (NSSet *) calibratedScreenPoints  // Returns only screen points on clips with a valid calibration
{
    NSMutableSet *calibratedPoints = [NSMutableSet new];
    for (VSEventScreenPoint *screenPoint in self.screenPoints) {
        if ([screenPoint.videoClip.calibration.matrixQuadratFrontToScreen count] > 0 && [screenPoint.videoClip.calibration.matrixQuadratBackToScreen count] > 0) [calibratedPoints addObject:screenPoint];
    }
    return calibratedPoints;
}

- (void) calculate3DCoords
// This function begins by calculating estimated 3-D coordinates using the linear closest point of approach method.  From that starting point, it numerically
// searches for a 3-D position that minimizes the total squared reprojection (pixel) error over all video clips, which is a better 3-D position estimate than the linear one.
{
    NSSet *calibratedScreenPoints = [self calibratedScreenPoints];
 	size_t numLines = (size_t) [calibratedScreenPoints count];
	if (numLines > 1) {
        // Get a starting guess at the 3-D point position from the old linear "closest point of approach" method 
        VSPoint3D linearIntersectionPoint = [self calculate3DCoordsLinear];
        if ([((VSEventScreenPoint *)[[calibratedScreenPoints allObjects] objectAtIndex:0]).videoClip.project.useIterativeTriangulation boolValue]) {
            // Load up the parameter array for the nonlinear root solver with all the info it needs to calculate the pixel error cost function
            VSPointSolverParams params;
            params.numCameras = numLines;
            params.camPositions = (VSPoint3D *) malloc(numLines*sizeof(VSPoint3D));
            params.axesHorizontal = (char *) malloc(numLines*sizeof(char));
            params.axesVertical = (char *) malloc(numLines*sizeof(char));
            params.quadratFrontToScreenFCMMatrices = (double**) malloc(numLines*sizeof(double *));
            params.frontFacePlanes = (VSPoint3D**) malloc(numLines*sizeof(VSPoint3D *));
            params.undistortedScreenPoints = (NSPoint *) malloc(numLines*sizeof(NSPoint));
            VSEventScreenPoint *screenPoint;
            for (int i = 0; i < numLines; i++) {
                screenPoint = [[calibratedScreenPoints allObjects] objectAtIndex:i];
                params.camPositions[i].x = [screenPoint.videoClip.calibration.cameraX doubleValue];
                params.camPositions[i].y = [screenPoint.videoClip.calibration.cameraY doubleValue];
                params.camPositions[i].z = [screenPoint.videoClip.calibration.cameraZ doubleValue];
                params.quadratFrontToScreenFCMMatrices[i] = (double *) malloc(9*sizeof(double));
                [screenPoint.videoClip.calibration putQuadratFrontToScreenFCMMatrixInArray:params.quadratFrontToScreenFCMMatrices[i]];
                params.frontFacePlanes[i] = (VSPoint3D *) malloc(3*sizeof(VSPoint3D));
                [screenPoint putPointsInFrontQuadratPlaneIntoArray:params.frontFacePlanes[i]];
                params.axesHorizontal[i] = [screenPoint.videoClip.calibration.axisHorizontal characterAtIndex:0];
                params.axesVertical[i] = [screenPoint.videoClip.calibration.axisVertical characterAtIndex:0];
                params.undistortedScreenPoints[i] = [screenPoint undistortedCoords];
            }
            // Set up and perform the minimization
            const gsl_multimin_fminimizer_type *T = gsl_multimin_fminimizer_nmsimplex2;
            gsl_multimin_fminimizer *s = gsl_multimin_fminimizer_alloc(T, 3);
            gsl_multimin_function f = {&pointSolverCostFunction_f, 3, &params};
            // Starting point
            gsl_vector *x = gsl_vector_alloc(3);           
            gsl_vector_set(x, 0, linearIntersectionPoint.x);
            gsl_vector_set(x, 1, linearIntersectionPoint.y);
            gsl_vector_set(x, 2, linearIntersectionPoint.z);         
            // Set initial step sizes to 1
            gsl_vector *ss = gsl_vector_alloc(3);            // ss is short for "step sizes"
            gsl_vector_set_all(ss, 1);
            gsl_multimin_fminimizer_set(s, &f, x, ss);
            size_t iter = 0;
            int status;
            double size;
            do {
                iter++;
                status = gsl_multimin_fminimizer_iterate(s);
                if (status) break;
                size = gsl_multimin_fminimizer_size(s);
                status = gsl_multimin_test_size(size, 1e-6);                        // Here we set the minimum characteristic size of the simplex as a possible stopping criterion
                //NSLog(@"After %3d iterations with size %1.12f for point %@ in event %@, cost function with final 3D point of (%1.5f,%1.5f,%1.5f) was %1.5f.",(int) iter,size,[self index],[self.trackedEvent index],gsl_vector_get(s->x,0),gsl_vector_get(s->x,1),gsl_vector_get(s->x,2),s->fval);
            } while (status == GSL_CONTINUE && iter < 100);                         // Here we set the max # of iterations
            // Store the results
            self.worldX = [NSNumber numberWithDouble:gsl_vector_get(s->x, 0)];
            self.worldY = [NSNumber numberWithDouble:gsl_vector_get(s->x, 1)];
            self.worldZ = [NSNumber numberWithDouble:gsl_vector_get(s->x, 2)];
            self.reprojectionErrorNorm = [NSNumber numberWithDouble:sqrt(s->fval / numLines)];  // actually the RMS reprojection error
          // Useful diagnostic tool here highlights 
    //        if (iter > 300 || s->fval > 6.0) {
    //            NSLog(@"After %d iterations for point %@ in event %@, cost function with final 3D point of (%1.5f,%1.5f,%1.5f) was %1.5f.",(int) iter,[self index],[self.trackedEvent index],gsl_vector_get(s->x,0),gsl_vector_get(s->x,1),gsl_vector_get(s->x,2),s->fval);
    //        }
    //
            // Free up all the memory malloc'd above
            gsl_vector_free(x);
            gsl_vector_free(ss);
            gsl_multimin_fminimizer_free(s);
            free(params.camPositions);
            free(params.undistortedScreenPoints);
            for (int i = 0; i < numLines; i++) {
                free(params.quadratFrontToScreenFCMMatrices[i]);
                free(params.frontFacePlanes[i]);
            }
            free(params.quadratFrontToScreenFCMMatrices);
            // Calculate the hint lines
            for (VSEventScreenPoint *screenPoint in calibratedScreenPoints) [screenPoint calculateHintLines];
            // Calculate the new Mean PLD (point-line distance)        VSLine3D lines[numLines];
            VSLine3D lines[numLines];
            for (int i=0; i<numLines; i++) lines[i] = [[[calibratedScreenPoints allObjects] objectAtIndex:i] computeLine3D:YES];
            double PLD;
            [UtilityFunctions intersectionOfNumber:numLines of3DLines:lines meanPLD:&PLD];
            self.meanPLD = [NSNumber numberWithDouble:PLD];
        } else {    // if not using iterative intersections, just set the world coords to the linear result
            self.worldX = [NSNumber numberWithDouble:linearIntersectionPoint.x];
            self.worldY = [NSNumber numberWithDouble:linearIntersectionPoint.y];
            self.worldZ = [NSNumber numberWithDouble:linearIntersectionPoint.z];
        }

        // Now calculate the distance from the point to the nearest camera
        
        bool isFirstCameraDistance = YES;
        for (VSEventScreenPoint *screenPoint in calibratedScreenPoints) {
            VSPoint3D cameraPoint;
            cameraPoint.x = [screenPoint.videoClip.calibration.cameraX floatValue];
            cameraPoint.y = [screenPoint.videoClip.calibration.cameraY floatValue];
            cameraPoint.z = [screenPoint.videoClip.calibration.cameraZ floatValue];
            float lineDiff[3] = {[self.worldX floatValue]-cameraPoint.x,[self.worldY floatValue]-cameraPoint.y,[self.worldZ floatValue]-cameraPoint.z};
            float distance = cblas_snrm2(3, lineDiff, 1);
            if (isFirstCameraDistance || distance < [self.nearestCameraDistance floatValue]) {
                self.nearestCameraDistance = [NSNumber numberWithFloat:distance];
            }
            isFirstCameraDistance = NO;
        }
        
    } else {
		self.worldX = nil;
		self.worldY = nil;
		self.worldZ = nil;        
    }
    if ([self.screenPoints count] > 0) {                        // After updating a point (whether 3D or not) set the project file to know it was updated sinece last export.
        VSEventScreenPoint *pt = [self.screenPoints anyObject]; // The purpose of this is for my code that reads VidSync Document files directly to check progress of analysis by colleagues in a whole folder.
        pt.videoClip.project.updatedSinceLastExport = [NSNumber numberWithBool:NO];
    }
}


/*
 
 I should also add the camera Mean PLD and the linear method preference to the core data model.
 
 */

- (VSPoint3D) calculate3DCoordsLinear
{
 	int numLines = [self.screenPoints count];
    VSLine3D lines[numLines];
    for (int i=0; i<numLines; i++) lines[i] = [[[self.screenPoints allObjects] objectAtIndex:i] computeLine3D:NO];
    double PLD;
    VSPoint3D intersection = [UtilityFunctions intersectionOfNumber:numLines of3DLines:lines meanPLD:&PLD];
    self.meanPLD = [NSNumber numberWithDouble:PLD];
    return intersection;
}


#pragma mark
#pragma mark Quick formatted information "accessors"

- (NSString *) screenPointsString	// Displays the screenPoints as "videoName: {x1,y1}  videoName1: {x2,y2}  etc..."
{
	NSMutableString *pointsStr = [NSMutableString stringWithString:@""];
	// Sort VSEventScreenPoints alphabetically by videoClip.clipName
	NSSortDescriptor *alphabeticalByClipName = [NSSortDescriptor sortDescriptorWithKey:@"videoClip.clipName" ascending:YES];
	NSArray *sortableScreenPoints = [self.screenPoints allObjects];
	NSArray *sortedScreenPoints = [sortableScreenPoints sortedArrayUsingDescriptors:[NSArray arrayWithObject:alphabeticalByClipName]];
	// Format and add all point to the string and return
	for (VSEventScreenPoint *screenPoint in sortedScreenPoints) {
		[pointsStr appendFormat:@"%@: {%1.2f,%1.2f}   ",screenPoint.videoClip.clipName,[screenPoint.screenX floatValue],[screenPoint.screenY floatValue]];
	}
	return pointsStr;
}

- (NSString *) calibrationFramePointsString // Displays as "videoName1 front: {h1f,v1f}  videoName1: {h1b,h2b} videoName2 front...
{
	NSMutableString *pointsStr = [NSMutableString stringWithString:@""];
	// Sort VSEventScreenPoints alphabetically by videoClip.clipName
	NSSortDescriptor *alphabeticalByClipName = [NSSortDescriptor sortDescriptorWithKey:@"videoClip.clipName" ascending:YES];
	NSArray *sortableScreenPoints = [self.screenPoints allObjects];
	NSArray *sortedScreenPoints = [sortableScreenPoints sortedArrayUsingDescriptors:[NSArray arrayWithObject:alphabeticalByClipName]];
	// Format and add all point to the string and return
	for (VSEventScreenPoint *screenPoint in sortedScreenPoints) {
        if (screenPoint.videoClip.calibration.frontIsCalibrated) {
            [pointsStr appendFormat:@"%@Front: {%1.4f,%1.4f}   ",screenPoint.videoClip.clipName,[screenPoint.frontFrameWorldH floatValue],[screenPoint.frontFrameWorldV floatValue]];
        }
        if (screenPoint.videoClip.calibration.backIsCalibrated) {
            [pointsStr appendFormat:@"%@Back: {%1.4f,%1.4f}   ",screenPoint.videoClip.clipName,[screenPoint.backFrameWorldH floatValue],[screenPoint.backFrameWorldV floatValue]];
        }
	}
	return pointsStr;
}

- (BOOL) has3Dcoords
{
	return ([self.worldX floatValue] != 0.0 || [self.worldX floatValue] != 0.0 || [self.worldX floatValue] != 0.0);
}

- (VSEventScreenPoint *) screenPointForVideoClip:(VSVideoClip *)videoClip;
{
	for (VSEventScreenPoint *screenPoint in self.screenPoints) if ([screenPoint.videoClip isEqualTo:videoClip]) return screenPoint;
	return nil;
}

- (NSNumber *) distanceToVSPoint:(VSPoint *)otherPoint
{
	if (!pointToPointDistanceCache) {	// If there is no cache for point-to-point distances, create one.  
		pointToPointDistanceCache = [NSMapTable strongToStrongObjectsMapTable];	// The Objects are the NSNumbers returned from this function; the keys are the otherPoints.
		// Will put the NSNumber resulting from the current calculation into this cache at the end of the function.
	} else {							// Otherwise, look for a distance from this point to otherPoint in the cache; and return it if it exists
		NSNumber *existingResult = [pointToPointDistanceCache objectForKey:otherPoint];
		if (existingResult != nil) return existingResult;
	}
	// If there's no existing result, go ahead with calculating the point-to-point distance.
	
	float lineDiff[3] = {[self.worldX floatValue]-[otherPoint.worldX floatValue],[self.worldY floatValue]-[otherPoint.worldY floatValue],[self.worldZ floatValue]-[otherPoint.worldZ floatValue]};
	float distance = cblas_snrm2(3, lineDiff, 1);
    [pointToPointDistanceCache setObject:[NSNumber numberWithFloat:distance] forKey:otherPoint];  
	return [NSNumber numberWithFloat:distance];
}

- (NSNumber *) speedToVSPoint:(VSPoint *)otherPoint // magnitude of the velocity vector from this point to the otherPoint
{
    float distance = [[self distanceToVSPoint:otherPoint] floatValue];
    float thisTime = (float) CMTimeGetSeconds([UtilityFunctions CMTimeFromString:self.timecode]);
    float otherTime = (float) CMTimeGetSeconds([UtilityFunctions CMTimeFromString:otherPoint.timecode]);
    NSNumber *speed;
    if (thisTime == otherTime) {
        speed = [NSDecimalNumber notANumber];
    } else {
        speed = [NSNumber numberWithFloat:distance/fabs(thisTime - otherTime)];
    }
    return speed;
}

- (NSString *) spreadsheetFormatted3DPoint:(NSString *)separator
{	
	BOOL includeScreenCoords = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeScreenCoordsInExports"] boolValue];
	NSMutableString *objectsString = [NSMutableString new];
    
    NSTimeInterval time;	// is a double
    time = CMTimeGetSeconds([UtilityFunctions CMTimeFromString:self.timecode]);
    
	int objectCount = 1;
	for (VSTrackedObject *trackedObject in self.trackedEvent.trackedObjects) {
		if (objectCount > 1) [objectsString appendString:@", "];
		if ([trackedObject.name isEqualToString:@""] || trackedObject.name == nil) {
			[objectsString appendFormat:@"%@ %@",trackedObject.type.name,trackedObject.index];
		} else {
			[objectsString appendFormat:@"%@ %@ (%@)",trackedObject.type.name,trackedObject.index,trackedObject.name];				
		}
		objectCount += 1;
	}
	NSString *eventString;
	if ([self.trackedEvent.name isEqualToString:@""] || self.trackedEvent.name == nil) {
		eventString = [NSString stringWithFormat:@"%@ %@",self.trackedEvent.type.name,self.trackedEvent.index];
	} else {
		eventString = [NSString stringWithFormat:@"%@ %@ (%@) (Notes: %@)",self.trackedEvent.type.name,self.trackedEvent.index,self.trackedEvent.name,self.trackedEvent.notes];
	}
    
    NSMutableString *screenCoordsString = [NSMutableString stringWithString:@""];
    if (includeScreenCoords) {
        [screenCoordsString appendString:separator];
        for (VSEventScreenPoint *point in self.screenPoints) [screenCoordsString appendString:[point spreadsheetFormattedScreenPoint]];
    }
    
	return [NSString stringWithFormat:@"%@%@%@%@%@%@%f%@%f%@%f%@%f%@%f%@%f%@%f%@\n",
									  objectsString,separator,
									  eventString,separator,
                                      self.timecode,separator,
                                      [[NSNumber numberWithDouble:time] floatValue],separator,
									  [[self worldX] floatValue],separator,
									  [[self worldY] floatValue],separator,
									  [[self worldZ] floatValue],separator,
									  [[self meanPLD] floatValue],separator,
                                      [[self reprojectionErrorNorm] floatValue],separator,
                                      [[self nearestCameraDistance] floatValue],
                                      screenCoordsString
	
        ];
}

- (NSXMLNode *) representationAsXMLNode
{
	BOOL includeScreenCoords = [[[[NSUserDefaultsController sharedUserDefaultsController] values] valueForKey:@"includeScreenCoordsInExports"] boolValue];
	NSXMLElement *mainElement = [[NSXMLElement alloc] initWithName:@"point"];
	NSTimeInterval time;	// is a double
	time = CMTimeGetSeconds([UtilityFunctions CMTimeFromString:self.timecode]);
    
	NSNumberFormatter *nf = self.trackedEvent.type.project.document.decimalFormatter;
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"index" stringValue:[self.index stringValue]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"x" stringValue:[nf stringFromNumber:self.worldX]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"y" stringValue:[nf stringFromNumber:self.worldY]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"z" stringValue:[nf stringFromNumber:self.worldZ]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"timecode" stringValue:self.timecode]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"time" stringValue:[nf stringFromNumber:[NSNumber numberWithDouble:time]]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"meanPLD" stringValue:[nf stringFromNumber:self.meanPLD]]];
	[mainElement addAttribute:[NSXMLNode attributeWithName:@"reprojectionErrorNorm" stringValue:[nf stringFromNumber:self.reprojectionErrorNorm]]];
    [mainElement addAttribute:[NSXMLNode attributeWithName:@"nearestCameraDistance" stringValue:[nf stringFromNumber:self.nearestCameraDistance]]];
	if (includeScreenCoords) for (VSEventScreenPoint *point in self.screenPoints) [mainElement addChild:[point representationAsXMLNode]];
	return mainElement;		
}

@end
