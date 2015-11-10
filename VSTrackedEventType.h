//
//  VSTrackedEventType.h
//  VidSync
//
//  Created by Jason Neuswanger on 11/20/09.
//  Copyright 2009 University of Alaska Fairbanks. All rights reserved.
//

#import <Cocoa/Cocoa.h>


@interface VSTrackedEventType : VSVisibleItem {

}


@property (strong) NSString *name;
@property (strong) NSNumber *maxNumPoints;
@property (strong) NSNumber *requiresSameTimecode;

@property (strong) NSString *connectingLineType;
@property (strong) NSNumber *connectingLineLengthLabeled;
@property (strong) NSNumber *connectingLineThickness;
@property (strong) NSNumber *connectingLineLengthLabelFontSize;
@property (strong) NSNumber *connectingLineLengthLabelFractionDigits;
@property (strong) NSNumber *connectingLineLengthLabelUnitMultiplier;
@property (strong) NSString *connectingLineLengthLabelUnits;
@property (strong) NSNumber *connectingLineLabelShowLength;
@property (strong) NSNumber *connectingLineLabelShowSpeed;

@property (strong) NSSet *trackedEvents;

@property (strong) VSProject *project;

- (void) addObservers;

- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context;

+ (void) insertNewTypeFromLoadedDictionary:(NSDictionary *)objectTypeDictionary inProject:(VSProject *)project inManagedObjectContext:(NSManagedObjectContext *)moc;

- (void) carefullyRemoveObserver:(NSObject *)observer forKeyPath:(NSString *)keyPath;

@end
