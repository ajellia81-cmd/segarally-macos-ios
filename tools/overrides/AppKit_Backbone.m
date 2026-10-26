#import <UIKit/UIKit.h>
#import <GameController/GameController.h>
#import <objc/runtime.h>
#import <dlfcn.h>

extern void Port0rCoinKey(BOOL down);
static const char installedKey;
static const char fallbackKey;

static BOOL NeedsCoinFallback(void) {
    int (*count)(void) = dlsym(RTLD_DEFAULT, "SDL_NumJoysticks");
    int32_t (*instance)(int) = dlsym(RTLD_DEFAULT, "SDL_JoystickGetDeviceInstanceID");
    void *(*opened)(int32_t) = dlsym(RTLD_DEFAULT, "SDL_GameControllerFromInstanceID");
    const char *(*name)(int) = dlsym(RTLD_DEFAULT, "SDL_GameControllerNameForIndex");
    int (*has)(void *, int) = dlsym(RTLD_DEFAULT, "SDL_GameControllerHasButton");
    if (!count || !instance || !opened || !name || !has) return NO; // avoid double coins when unknown
    for (int i = 0; i < count(); ++i) {
        const char *n = name(i);
        if (!n || ![[@(n) lowercaseString] containsString:@"backbone"]) continue;
        void *controller = opened(instance(i));
        if (controller) return !has(controller, 4); // SDL_CONTROLLER_BUTTON_BACK
    }
    return NO;
}
static void ConfigureBackbones(void) {
    for (GCController *controller in GCController.controllers) {
        NSString *identity = [NSString stringWithFormat:@"%@ %@", controller.vendorName, controller.productCategory];
        if (![[identity lowercaseString] containsString:@"backbone"]) continue;
        GCPhysicalInputProfile *profile = controller.physicalInputProfile;
        NSMutableArray<GCControllerButtonInput *> *candidates = [NSMutableArray new];
        if (controller.extendedGamepad.buttonOptions) [candidates addObject:controller.extendedGamepad.buttonOptions];
        if (!candidates.count) {
            GCControllerButtonInput *share = profile.buttons[@"Button Share"];
            if (share) [candidates addObject:share];
        }
        if (!objc_getAssociatedObject(controller, &installedKey)) {
            NSLog(@"PORT0R Backbone %@ buttons=%@ options=%@ selectCandidates=%lu", identity,
                  profile.buttons.allKeys, controller.extendedGamepad.buttonOptions, (unsigned long)candidates.count);
            objc_setAssociatedObject(controller, &installedKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
        for (GCControllerButtonInput *button in candidates) {
            button.preferredSystemGestureState = GCSystemGestureStateDisabled;
            if (objc_getAssociatedObject(button, &installedKey)) continue;
            GCControllerButtonValueChangedHandler previous = button.pressedChangedHandler;
            button.pressedChangedHandler = ^(GCControllerButtonInput *input, float value, BOOL pressed) {
                if (previous) previous(input, value, pressed);
                BOOL fallback = pressed ? NeedsCoinFallback() : [objc_getAssociatedObject(input, &fallbackKey) boolValue];
                if (pressed) objc_setAssociatedObject(input, &fallbackKey, @(fallback), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                NSLog(@"PORT0R Backbone Select pressed=%d keyboardFallback=%d gesture=%ld", pressed, fallback,
                      (long)input.preferredSystemGestureState);
                if (fallback) dispatch_async(dispatch_get_main_queue(), ^{ Port0rCoinKey(pressed); });
                if (!pressed) objc_setAssociatedObject(input, &fallbackKey, @NO, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            };
            objc_setAssociatedObject(button, &installedKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
    }
}
__attribute__((constructor)) static void BackboneInit(void) {
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *notification in @[GCControllerDidConnectNotification, UIApplicationDidBecomeActiveNotification])
        [nc addObserverForName:notification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { ConfigureBackbones(); }];
    dispatch_async(dispatch_get_main_queue(), ^{ ConfigureBackbones(); });
}
