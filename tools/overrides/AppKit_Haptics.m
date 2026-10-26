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
static _Atomic uint64_t hapticRequestsR2;
uint64_t Port0rHapticCallsR2(void) { return atomic_load(&hapticRequestsR2); }
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
        engine.stoppedHandler = ^(CHHapticEngineStoppedReason reason) {};
        engine.resetHandler = ^{};
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
    // Warm the actual engine and pattern, but never reuse the zero-intensity
    // started/stopped player for real output. Prepare a fresh player now, before
    // gameplay, so the first real request does not create a player or inherit silence.
    if (![player sendParameters:@[silent] atTime:0 error:&error] ||
        ![player startAtTime:0 error:&error] || ![player stopAtTime:0 error:&error]) {
        [player cancelAndReturnError:nil];
        NSLog(@"PORT0R silent haptic prepare failed: %@", error); return NO;
    }
    [player cancelAndReturnError:NULL];
    id<CHHapticPatternPlayer> output = [engine createPlayerWithPattern:pattern error:&error];
    if (!output || error) { NSLog(@"PORT0R R5 fresh haptic player failed: %@", error); return NO; }
    ((void (*)(id,SEL,id))objc_msgSend)(motor, setPlayer, output);
    NSLog(@"PORT0R R5 haptic prepared fresh output=%@ after disposable silent warm-up", output);
    return YES;
}
static int SetIntensity(id motor, SEL cmd, float intensity) {
    @synchronized (motor) {
        if (!warmingMotors && intensity > 0) {
            uint64_t event = atomic_fetch_add(&hapticRequestsR2, 1);
            if (event < 4) NSLog(@"PORT0R R5 haptic request=%llu intensity=%.4f foreground=%d engine=%@ player=%@",
                (unsigned long long)event + 1, intensity, hapticsForeground, MotorGet(motor, @"engine"), MotorGet(motor, @"player"));
        }
        if (warmingMotors) {
            PrepareSilentPlayer(motor);
            intensity = 0; // never send the warm-up's non-zero request to hardware
        } else if (intensity > 0 && hapticsForeground &&
                   [objc_getAssociatedObject(motor, &needsRestartKey) boolValue]) {
            if (!RestartMotor(motor, NO)) return -1;
        }
        if (!hapticsForeground) intensity = 0;
        BOOL wasActive = [motor respondsToSelector:NSSelectorFromString(@"active")] &&
            ((bool (*)(id,SEL))objc_msgSend)(motor, NSSelectorFromString(@"active"));
        int status = ((int (*)(id,SEL,float))originalIntensity)(motor, cmd, intensity);
        if (!warmingMotors && hapticsForeground && intensity > 0 && !wasActive && status == 0) {
            // SDL updates parameters before starting a retained silent player.
            // Reapply the real intensity AFTER start so its first event cannot
            // inherit the warm-up's zero intensity. Do not start a second event.
            id<CHHapticPatternPlayer> player = MotorGet(motor, @"player");
            CHHapticDynamicParameter *value = [[CHHapticDynamicParameter alloc]
                initWithParameterID:CHHapticDynamicParameterIDHapticIntensityControl value:intensity relativeTime:0];
            NSError *error = nil;
            if (player && ![player sendParameters:@[value] atTime:0 error:&error]) {
                NSLog(@"PORT0R first haptic intensity restore failed: %@", error);
                InvalidateMotor(motor, MotorGet(motor, @"engine"));
                return -1;
            }
        }
        return status;
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
