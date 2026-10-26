#import <Foundation/Foundation.h>
#ifndef PORT0R_BACKBONE_TEST
#import <UIKit/UIKit.h>
#endif
#import <GameController/GameController.h>

// Never own pressedChangedHandler: SDL installs/replaces these during device open.
// Read GameController's current state at the native SDL_GetButton polling boundary.
static BOOL IsBackbone(GCController *controller) {
    NSString *identity = [NSString stringWithFormat:@"%@ %@", controller.vendorName, controller.productCategory];
    return [[identity lowercaseString] containsString:@"backbone"];
}
BOOL Port0rBackboneSelect(const char *name) {
    if (!name || ![[[NSString stringWithUTF8String:name] lowercaseString] containsString:@"backbone"]) return NO;
    GCController *matched = nil;
    for (GCController *controller in GCController.controllers) {
        if (!IsBackbone(controller)) continue;
        // Without a stable shared device ID, never leak one pad's input into another.
        if (matched) return NO;
        matched = controller;
    }
    if (!matched) return NO;
    GCControllerButtonInput *button = matched.extendedGamepad.buttonOptions;
    if (!button) button = matched.physicalInputProfile.buttons[@"Button Share"];
    if (!button) return NO;
    button.preferredSystemGestureState = GCSystemGestureStateDisabled;
    return button.isPressed;
}
static void ConfigureBackbones(void) {
    for (GCController *controller in GCController.controllers) {
        if (!IsBackbone(controller)) continue;
        GCControllerButtonInput *button = controller.extendedGamepad.buttonOptions;
        if (!button) button = controller.physicalInputProfile.buttons[@"Button Share"];
        button.preferredSystemGestureState = GCSystemGestureStateDisabled;
        NSLog(@"PORT0R Backbone Select polling bridge options=%@ buttons=%@", button,
              controller.physicalInputProfile.buttons.allKeys);
    }
}
#ifndef PORT0R_BACKBONE_TEST
__attribute__((constructor)) static void BackboneInit(void) {
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *notification in @[GCControllerDidConnectNotification, UIApplicationDidBecomeActiveNotification])
        [nc addObserverForName:notification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { ConfigureBackbones(); }];
    dispatch_async(dispatch_get_main_queue(), ^{ ConfigureBackbones(); });
}
#endif
