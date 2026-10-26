// R7: prepare engines only during controller open; never play a silent pattern.
// Real pulses start with their requested strength encoded in a fresh pattern.
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
static _Thread_local BOOL preparingEngines;
static const char currentStrengthKey;
static _Atomic uint64_t stopCalls;
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
                NSLog(@"PORT0R R7 haptic restart failed: %@", error); return NO;
            }
            objc_setAssociatedObject(motor, &needsRestartKey, @NO, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
        engine.autoShutdownEnabled = NO;
        return YES;
    }
}
static void ResumeMotors(void) {
    hapticsForeground = YES;
    NSArray *motors;
    @synchronized (liveMotors) { motors = liveMotors.allObjects; }
    for (id motor in motors) {
        BOOL ready = RestartMotor(motor, YES);
        NSLog(@"PORT0R R6 foreground engine ready=%d; engine only, no playback", ready);
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
static void SetMotorPlayer(id motor, id player, BOOL active) {
    ((void (*)(id,SEL,id))objc_msgSend)(motor, NSSelectorFromString(@"setPlayer:"), player);
    ((void (*)(id,SEL,bool))objc_msgSend)(motor, NSSelectorFromString(@"setActive:"), active);
}
static int StopPlayer(id motor) {
    id<CHHapticPatternPlayer> player = MotorGet(motor, @"player");
    NSError *error = nil;
    BOOL stopped = !player || [player stopAtTime:CHHapticTimeImmediate error:&error];
    SetMotorPlayer(motor, nil, NO);
    objc_setAssociatedObject(motor, &currentStrengthKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    uint64_t stop = atomic_fetch_add(&stopCalls, 1) + 1;
    if (player && (stop <= 12 || !stopped || error)) NSLog(@"PORT0R R7 haptic STOP ok=%d error=%@ player=%@", stopped, error, player);
    return stopped && !error ? 0 : -1;
}
static int SetIntensity(id motor, SEL cmd, float intensity) {
    @synchronized (motor) {
        CHHapticEngine *engine = MotorGet(motor, @"engine");
        TrackMotor(motor, engine);
        // SDL's tiny initialization call constructs/starts the real engines.
        // Do not create a player, send parameters or start playback here.
        if (preparingEngines) { engine.autoShutdownEnabled = NO; return engine ? 0 : -1; }
        if (!hapticsForeground || intensity <= 0) return StopPlayer(motor);
        uint64_t event = atomic_fetch_add(&hapticRequestsR2, 1) + 1;
        if (!RestartMotor(motor, NO)) return -1;
        NSNumber *previous = objc_getAssociatedObject(motor, &currentStrengthKey);
        if (MotorGet(motor, @"player") && previous && previous.floatValue == intensity) return 0;
        if (StopPlayer(motor) < 0) return -1;
        // Encode the requested strength in the event itself. No zero/intensity
        // parameter is sent before start, and no stopped warm-up player is reused.
        NSError *error = nil;
        CHHapticEventParameter *strength = [[CHHapticEventParameter alloc]
            initWithParameterID:CHHapticEventParameterIDHapticIntensity value:intensity];
        CHHapticEvent *pulse = [[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticContinuous
            parameters:@[strength] relativeTime:0 duration:GCHapticDurationInfinite];
        CHHapticPattern *pattern = [[CHHapticPattern alloc] initWithEvents:@[pulse] parameters:@[] error:&error];
        id<CHHapticPatternPlayer> player = pattern && !error ? [engine createPlayerWithPattern:pattern error:&error] : nil;
        BOOL started = player && !error && [player startAtTime:CHHapticTimeImmediate error:&error];
        if (started && !error) {
            SetMotorPlayer(motor, player, YES);
            objc_setAssociatedObject(motor, &currentStrengthKey, @(intensity), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        } else {
            [player stopAtTime:CHHapticTimeImmediate error:nil];
        }
        if (event <= 12 || !started || error)
            NSLog(@"PORT0R R7 haptic START request=%llu strength=%.4f ok=%d error=%@ player=%@",
                (unsigned long long)event, intensity, started, error, player);
        return started && !error ? 0 : -1;
    }
}
void Port0rPrepareControllerEnginesR7(void *controller,
    int (*rumble)(void *, uint16_t, uint16_t, uint32_t)) {
    if (!controller || !originalIntensity || !rumble) return;
    CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
    preparingEngines = YES;
    int initialized = rumble(controller, 1, 1, 1);
    int cleared = rumble(controller, 0, 0, 0);
    preparingEngines = NO;
    NSLog(@"PORT0R R7 engine-only preparation status=%d clear=%d elapsed=%.2fms; NO player/playback",
        initialized, cleared, (CFAbsoluteTimeGetCurrent() - start) * 1000);
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
    NSLog(@"PORT0R R6 haptic recovery installed=%d; engine-only preparation; real playback checked", originalIntensity != NULL);
}
