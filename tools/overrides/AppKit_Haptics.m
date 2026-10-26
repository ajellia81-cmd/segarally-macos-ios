// R6 comparison: no synthetic rumble, silent player or foreground prewarming.
// Forward real intensity unchanged while preserving lifecycle engine recovery.
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

static IMP originalIntensity, originalCleanup;
static NSHashTable *liveMotors;
static const char trackedEngineKey, needsRestartKey;
static _Atomic bool hapticsForeground = true;
static _Atomic uint64_t hapticRequestsR2;
uint64_t Port0rHapticCallsR2(void) { return atomic_load(&hapticRequestsR2); }
static id MotorGet(id motor, NSString *name) {
    return ((id (*)(id,SEL))objc_msgSend)(motor, NSSelectorFromString(name));
}
static void InvalidateMotor(id motor, CHHapticEngine *engine) {
    if (!motor || !engine) return;
    @synchronized (motor) {
        if (MotorGet(motor, @"engine") != engine) return;
        ((void (*)(id,SEL,id))objc_msgSend)(motor, NSSelectorFromString(@"setPlayer:"), nil);
        if ([motor respondsToSelector:NSSelectorFromString(@"setActive:")])
            ((void (*)(id,SEL,bool))objc_msgSend)(motor, NSSelectorFromString(@"setActive:"), false);
        objc_setAssociatedObject(motor, &needsRestartKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
}
static void TrackMotor(id motor, CHHapticEngine *engine) {
    if (!engine || objc_getAssociatedObject(motor, &trackedEngineKey) == engine) return;
    objc_setAssociatedObject(motor, &trackedEngineKey, engine, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    @synchronized (liveMotors) { [liveMotors addObject:motor]; }
    __weak id weakMotor = motor;
    __weak CHHapticEngine *weakEngine = engine;
    engine.stoppedHandler = ^(CHHapticEngineStoppedReason reason) { InvalidateMotor(weakMotor, weakEngine); };
    engine.resetHandler = ^{ InvalidateMotor(weakMotor, weakEngine); };
}
static BOOL RestartMotor(id motor, BOOL force) {
    @synchronized (motor) {
        CHHapticEngine *engine = MotorGet(motor, @"engine");
        if (!engine || !hapticsForeground) return NO;
        if (force || [objc_getAssociatedObject(motor, &needsRestartKey) boolValue]) {
            NSError *error = nil;
            if (![engine startAndReturnError:&error]) {
                NSLog(@"PORT0R R6 haptic restart failed: %@", error); return NO;
            }
            objc_setAssociatedObject(motor, &needsRestartKey, @NO, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
        return YES; // let original SDL create the player for a real request
    }
}
static void ResumeMotors(void) {
    hapticsForeground = YES;
    NSArray *motors;
    @synchronized (liveMotors) { motors = liveMotors.allObjects; }
    for (id motor in motors) {
        BOOL ready = RestartMotor(motor, YES);
        NSLog(@"PORT0R R6 foreground engine ready=%d; no player priming", ready);
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
static int SetIntensity(id motor, SEL cmd, float intensity) {
    @synchronized (motor) {
        TrackMotor(motor, MotorGet(motor, @"engine"));
        uint64_t event = 0;
        if (intensity > 0) event = atomic_fetch_add(&hapticRequestsR2, 1) + 1;
        if (intensity > 0 && hapticsForeground &&
            [objc_getAssociatedObject(motor, &needsRestartKey) boolValue] &&
            !RestartMotor(motor, NO)) return -1;
        float forwarded = hapticsForeground ? intensity : 0;
        int result = ((int (*)(id,SEL,float))originalIntensity)(motor, cmd, forwarded);
        if (event && event <= 8) NSLog(@"PORT0R R6 real haptic request=%llu requested=%.4f forwarded=%.4f status=%d player=%@",
            (unsigned long long)event, intensity, forwarded, result, MotorGet(motor, @"player"));
        return result;
    }
}
__attribute__((constructor)) static void InstallMotorRecovery(void) {
    liveMotors = [NSHashTable weakObjectsHashTable];
    Class motor = NSClassFromString(@"SDL_RumbleMotor");
    Method method = motor ? class_getInstanceMethod(motor, NSSelectorFromString(@"setIntensity:")) : NULL;
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
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { hapticsForeground = NO; }];
    for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UISceneDidActivateNotification])
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) { ResumeMotors(); }];
#endif
    NSLog(@"PORT0R R6 haptic recovery installed=%d; synthetic warm-up DISABLED", originalIntensity != NULL);
}
