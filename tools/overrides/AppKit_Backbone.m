#import <Foundation/Foundation.h>
#ifndef PORT0R_BACKBONE_TEST
#import <UIKit/UIKit.h>
#endif
#import <GameController/GameController.h>

// Never own pressedChangedHandler: SDL installs/replaces these during device open.
// Read GameController's current state at the native SDL_GetButton polling boundary.
// Use the proven keyboard Coin path only when Select belongs solely to Coin.
static BOOL CoinOnlySelection(NSString *text) {
    NSMutableDictionary<NSString *, NSString *> *bindings = [NSMutableDictionary new];
    for (NSString *raw in [text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        NSString *line = [raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        if (![line hasPrefix:@"pad."]) continue;
        NSRange separator = [line rangeOfString:@"="];
        if (separator.location == NSNotFound) separator = [line rangeOfCharacterFromSet:NSCharacterSet.whitespaceCharacterSet];
        if (separator.location == NSNotFound) return NO;
        NSString *key = [[line substringToIndex:separator.location] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        NSString *value = [[line substringFromIndex:NSMaxRange(separator)] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        if (!value.length) return NO;
        bindings[key] = value;
    }
    if (bindings[@"pad.coin"] && ![bindings[@"pad.coin"] isEqualToString:@"SELECT"]) return NO;
    for (NSString *key in bindings)
        if (![key isEqualToString:@"pad.coin"] && [bindings[key] isEqualToString:@"SELECT"]) return NO;
    return YES;
}
BOOL Port0rSelectCoinFallbackR3(void) {
    for (NSString *base in @[@"Documents/Port0r/srallyc", @"Library/Application Support/Port0r/srallyc"]) {
        NSString *path = [[NSHomeDirectory() stringByAppendingPathComponent:base] stringByAppendingPathComponent:@"tcvr-settings-v1.txt"];
        if (![NSFileManager.defaultManager fileExistsAtPath:path]) continue;
        NSString *text = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:NULL];
        return text && CoinOnlySelection(text);
    }
    return YES; // original defaults: only pad.coin uses SELECT
}
extern void Port0rReleaseSelectCoinR3(void);

static BOOL IsBackbone(GCController *controller) {
    NSString *identity = [NSString stringWithFormat:@"%@ %@", controller.vendorName, controller.productCategory];
    return [[identity lowercaseString] containsString:@"backbone"];
}
BOOL Port0rBackboneSelect(const char *name, int sdlDevices) {
    NSArray<GCController *> *controllers = GCController.controllers;
    BOOL named = name && [[[NSString stringWithUTF8String:name] lowercaseString] containsString:@"backbone"];
    // Bluetooth names need not contain the manufacturer. A single GC device
    // and a single SDL device identify the same pad without guessing its name.
    BOOL unique = sdlDevices == 1 && controllers.count == 1;
    GCController *matched = unique ? controllers.firstObject : nil;
    if (!named && !unique) return NO;
    for (GCController *controller in (!unique && named ? controllers : @[])) {
        if (!IsBackbone(controller)) continue;
        // Without a stable shared device ID, never leak one pad's input into another.
        if (matched) return NO;
        matched = controller;
    }
    if (!matched) return NO;
    GCControllerButtonInput *options = matched.extendedGamepad.buttonOptions;
    GCControllerButtonInput *share = matched.physicalInputProfile.buttons[@"Button Share"];
    options.preferredSystemGestureState = GCSystemGestureStateDisabled;
    share.preferredSystemGestureState = GCSystemGestureStateDisabled;
    return options.isPressed || share.isPressed;
}
static void ConfigureBackbones(void) {
    for (GCController *controller in GCController.controllers) {
        if (!IsBackbone(controller) && GCController.controllers.count != 1) continue;
        GCControllerButtonInput *button = controller.extendedGamepad.buttonOptions;
        button.preferredSystemGestureState = GCSystemGestureStateDisabled;
        controller.physicalInputProfile.buttons[@"Button Share"].preferredSystemGestureState = GCSystemGestureStateDisabled;
        NSLog(@"PORT0R R2 Select controller=%@ category=%@ options=%@ buttons=%@", controller.vendorName, controller.productCategory, button,
              controller.physicalInputProfile.buttons.allKeys);
    }
}
#ifndef PORT0R_BACKBONE_TEST
__attribute__((constructor)) static void BackboneInit(void) {
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *notification in @[GCControllerDidConnectNotification, UIApplicationDidBecomeActiveNotification])
        [nc addObserverForName:notification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { ConfigureBackbones(); }];
    for (NSString *notification in @[GCControllerDidDisconnectNotification, UIApplicationWillResignActiveNotification])
        [nc addObserverForName:notification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { Port0rReleaseSelectCoinR3(); }];
    dispatch_async(dispatch_get_main_queue(), ^{ ConfigureBackbones(); });
}
#endif
