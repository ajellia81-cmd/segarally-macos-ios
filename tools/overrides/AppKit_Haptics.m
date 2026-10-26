// SDL 2.30.3 creates its actual MFi engines lazily on the first non-zero
// rumble. Initialize those same motors before gameplay, never a spare engine.
#import <Foundation/Foundation.h>
#import <CoreHaptics/CoreHaptics.h>
#import <GameController/GameController.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdatomic.h>
#import <TargetConditionals.h>
#if TARGET_OS_IOS
#import <UIKit/UIKit.h>
#endif

static IMP originalIntensity;
static _Thread_local bool warmingMotors;
static IMP originalCleanup;
static NSHashTable *liveMotors;
static const char trackedEngineKey, needsRestartKey;
static _Atomic bool hapticsForeground = true;
static BOOL PrepareSilentPlayer(id motor);
static id MotorGet(id motor, NSString *name) {
    return ((id (*)(id,SEL))objc_msgSend)(motor, NSSelectorFromString(name));
}
static void InvalidateMotor(id motor, CHHapticEngine *engine) {
    if (!motor || !engine) return;
    @synchronized (motor) {
        if (MotorGet(motor, @"engine") != engine) return;
        ((void (*)(id,SEL,id))objc_msgSend)(motor, NSSelectorFromString(@"setPlayer:"), nil);
        if ([motor respondsToSelector:NSSelectorFromString(@"setActive:")])
            ((void (*)(id,SEL,BOOL))objc_msgSend)(motor, NSSelectorFromString(@"setActive:"), NO);
        objc_setAssociatedObject(motor, &needsRestartKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
}
static void TrackMotor(id motor, CHHapticEngine *engine) {
    if (objc_getAssociatedObject(motor, &trackedEngineKey) == engine) return;
    objc_setAssociatedObject(motor, &trackedEngineKey, engine, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    @synchronized (liveMotors) { [liveMotors addObject:motor]; }
    __weak id weakMotor = motor;
    __weak CHHapticEngine *weakEngine = engine;
    // SDL's original stoppedHandler sets motor.engine=nil while its rumble
    // context remains cached forever. Retain that engine, invalidate the player,
    // and restart it on foreground instead of leaving a permanently dead motor.
    engine.stoppedHandler = ^(CHHapticEngineStoppedReason reason) {
        InvalidateMotor(weakMotor, weakEngine);
    };
    engine.resetHandler = ^{ InvalidateMotor(weakMotor, weakEngine); };
}
static BOOL RestartMotor(id motor, BOOL force) {
    @synchronized (motor) {
        CHHapticEngine *engine = MotorGet(motor, @"engine");
        if (!engine || !hapticsForeground) return NO;
        if (force || [objc_getAssociatedObject(motor, &needsRestartKey) boolValue]) {
            NSError *error = nil;
            if (![engine startAndReturnError:&error]) {
                NSLog(@"PORT0R haptic restart failed: %@", error); return NO;
            }
            objc_setAssociatedObject(motor, &needsRestartKey, @NO, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
        return PrepareSilentPlayer(motor);
    }
}
static void ResumeMotors(void) {
    hapticsForeground = YES;
    NSArray *motors;
    @synchronized (liveMotors) { motors = liveMotors.allObjects; }
    for (id motor in motors) {
        BOOL ready = RestartMotor(motor, YES);
        NSLog(@"PORT0R foreground haptic motor ready=%d", ready);
    }
}
static void CleanupMotor(id motor, SEL cmd) {
    @synchronized (motor) {
        CHHapticEngine *engine = MotorGet(motor, @"engine");
        engine.stoppedHandler = nil; engine.resetHandler = nil;
        @synchronized (liveMotors) { [liveMotors removeObject:motor]; }
        objc_setAssociatedObject(motor, &trackedEngineKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        ((void (*)(id,SEL))originalCleanup)(motor, cmd);
    }
}
static BOOL PrepareSilentPlayer(id motor) {
    SEL engineSelector = NSSelectorFromString(@"engine");
    SEL playerSelector = NSSelectorFromString(@"player");
    SEL setPlayer = NSSelectorFromString(@"setPlayer:");
    if (![motor respondsToSelector:engineSelector] || ![motor respondsToSelector:playerSelector] ||
        ![motor respondsToSelector:setPlayer]) return NO;
    if (((id (*)(id,SEL))objc_msgSend)(motor, playerSelector)) return YES;
    CHHapticEngine *engine = ((id (*)(id,SEL))objc_msgSend)(motor, engineSelector);
    if (!engine) return NO;
    TrackMotor(motor, engine);
    NSError *error = nil;
    CHHapticEventParameter *intensity = [[CHHapticEventParameter alloc]
        initWithParameterID:CHHapticEventParameterIDHapticIntensity value:1];
    CHHapticEvent *event = [[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticContinuous
        parameters:@[intensity] relativeTime:0 duration:GCHapticDurationInfinite];
    CHHapticPattern *pattern = [[CHHapticPattern alloc] initWithEvents:@[event] parameters:@[] error:&error];
    id<CHHapticPatternPlayer> player = pattern ? [engine createPlayerWithPattern:pattern error:&error] : nil;
    if (!player || error) { NSLog(@"PORT0R haptic prepare failed: %@", error); return NO; }
    CHHapticDynamicParameter *silent = [[CHHapticDynamicParameter alloc]
        initWithParameterID:CHHapticDynamicParameterIDHapticIntensityControl value:0 relativeTime:0];
    // Set intensity to zero before starting, then retain the stopped player for
    // SDL. Its next real request sets its own requested intensity before start.
    if (![player sendParameters:@[silent] atTime:0 error:&error] ||
        ![player startAtTime:0 error:&error] || ![player stopAtTime:0 error:&error]) {
        [player cancelAndReturnError:nil];
        NSLog(@"PORT0R silent haptic prepare failed: %@", error); return NO;
    }
    ((void (*)(id,SEL,id))objc_msgSend)(motor, setPlayer, player);
    return YES;
}
static int SetIntensity(id motor, SEL cmd, float intensity) {
    @synchronized (motor) {
        if (warmingMotors) {
            PrepareSilentPlayer(motor);
            intensity = 0; // never send the warm-up's non-zero request to hardware
        } else if (intensity > 0 && hapticsForeground &&
                   [objc_getAssociatedObject(motor, &needsRestartKey) boolValue]) {
            if (!RestartMotor(motor, NO)) return -1;
        }
        if (!hapticsForeground) intensity = 0;
        return ((int (*)(id,SEL,float))originalIntensity)(motor, cmd, intensity);
    }
}
__attribute__((visibility("default")))
void Port0rWarmControllerHaptics(void *controller,
    int (*rumble)(void *, uint16_t, uint16_t, uint32_t),
    int (*triggers)(void *, uint16_t, uint16_t, uint32_t),
    int (*hasRumble)(void *), int (*hasTriggers)(void *)) {
    if (!originalIntensity || !controller || warmingMotors) return;
    CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
    warmingMotors = true;
    int handles = -1, trigger = -1;
    @try {
        if (rumble && hasRumble && hasRumble(controller)) {
            // Zero alone is optimized away by SDL_JoystickRumble. The motor
            // hook suppresses this non-zero request while building its cache.
            handles = rumble(controller, 1, 1, 1);
            rumble(controller, 0, 0, 0);
        }
        if (triggers && hasTriggers && hasTriggers(controller)) {
            trigger = triggers(controller, 1, 1, 1);
            triggers(controller, 0, 0, 0);
        }
    } @finally { warmingMotors = false; }
    NSLog(@"PORT0R SDL motor warm-up handles=%d triggers=%d elapsed=%.1fms", handles, trigger,
          (CFAbsoluteTimeGetCurrent() - start) * 1000);
}
__attribute__((constructor)) static void InstallMotorWarmup(void) {
    liveMotors = [NSHashTable weakObjectsHashTable];
    Class motor = NSClassFromString(@"SDL_RumbleMotor");
    Method method = motor ? class_getInstanceMethod(motor, NSSelectorFromString(@"setIntensity:")) : NULL;
    // Only the verified SDL signature is supported; skip unknown classes.
    if (method && method_getNumberOfArguments(method) == 3) {
        char result[8] = {0}, argument[8] = {0};
        method_getReturnType(method, result, sizeof result);
        method_getArgumentType(method, 2, argument, sizeof argument);
        if (result[0] == 'i' && argument[0] == 'f')
            originalIntensity = method_setImplementation(method, (IMP)SetIntensity);
    }
    Method cleanup = motor ? class_getInstanceMethod(motor, NSSelectorFromString(@"cleanup")) : NULL;
    if (originalIntensity && cleanup) originalCleanup = method_setImplementation(cleanup, (IMP)CleanupMotor);
#if TARGET_OS_IOS
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    for (NSString *name in @[UIApplicationWillResignActiveNotification, UIApplicationDidEnterBackgroundNotification,
                            UISceneWillDeactivateNotification, UISceneDidEnterBackgroundNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {
            hapticsForeground = NO;
        }];
    for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UISceneDidActivateNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { ResumeMotors(); }];
#endif
    NSLog(@"PORT0R SDL silent haptic warm-up installed=%d", originalIntensity != NULL);
}
