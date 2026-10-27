// R10 comparison: prime playback at a perceptible 70% / 120ms; log engine stops/resets.
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
static const char primeDoneKey, primePlayerKey;
static BOOL PrimeMotorPlayback(id motor);
static void EndPrimePlayback(id motor);
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
        objc_setAssociatedObject(motor, &primePlayerKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
}
static void TrackMotor(id motor, CHHapticEngine *engine) {
    if (!engine || objc_getAssociatedObject(motor, &trackedEngineKey) == engine) return;
    objc_setAssociatedObject(motor, &trackedEngineKey, engine, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    @synchronized (liveMotors) { [liveMotors addObject:motor]; }
    __weak id weakMotor = motor;
    __weak CHHapticEngine *weakEngine = engine;
    engine.stoppedHandler = ^(CHHapticEngineStoppedReason reason) {
        NSLog(@"PORT0R R10 engine STOP motor=%@ engine=%@ reason=%ld foreground=%d", weakMotor, weakEngine, (long)reason, hapticsForeground);
        InvalidateMotor(weakMotor, weakEngine);
    };
    engine.resetHandler = ^{
        NSLog(@"PORT0R R10 engine RESET motor=%@ engine=%@ foreground=%d", weakMotor, weakEngine, hapticsForeground);
        InvalidateMotor(weakMotor, weakEngine);
    };
}
static BOOL RestartMotor(id motor, BOOL force) {
    @synchronized (motor) {
        CHHapticEngine *engine = MotorGet(motor, @"engine");
        if (!engine || !hapticsForeground) return NO;
        if (force || [objc_getAssociatedObject(motor, &needsRestartKey) boolValue]) {
            NSError *error = nil;
            if (![engine startAndReturnError:&error]) {
                NSLog(@"PORT0R R10 haptic restart failed: %@", error); return NO;
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
        if (ready) PrimeMotorPlayback(motor);
        NSLog(@"PORT0R R10 foreground engine ready=%d; priming only if not already completed", ready);
    }
}
static void CleanupMotor(id motor, SEL cmd) {
    @synchronized (motor) {
        EndPrimePlayback(motor);
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
    if (player && (stop <= 12 || !stopped || error)) NSLog(@"PORT0R R10 haptic STOP ok=%d error=%@ player=%@", stopped, error, player);
    return stopped && !error ? 0 : -1;
}
static void ReleasePrimePlayer(id motor, id player) {
    if (!motor) return;
    @synchronized (motor) {
        if (objc_getAssociatedObject(motor, &primePlayerKey) == player)
            objc_setAssociatedObject(motor, &primePlayerKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
}
static void EndPrimePlayback(id motor) {
    id<CHHapticPatternPlayer> player = objc_getAssociatedObject(motor, &primePlayerKey);
    if (player) {
        NSError *error = nil;
        BOOL stopped = [player stopAtTime:CHHapticTimeImmediate error:&error];
        if (!stopped || error) NSLog(@"PORT0R R10 priming stop ok=%d error=%@", stopped, error);
        ReleasePrimePlayer(motor, player);
    }
}
static BOOL PrimeMotorPlayback(id motor) {
    @synchronized (motor) {
        if ([objc_getAssociatedObject(motor, &primeDoneKey) boolValue]) return YES;
        if (!hapticsForeground) return NO;
        CHHapticEngine *engine = MotorGet(motor, @"engine");
        if (!engine) return NO;
        NSError *error = nil;
        CHHapticEventParameter *strength = [[CHHapticEventParameter alloc]
            initWithParameterID:CHHapticEventParameterIDHapticIntensity value:0.7f];
        // Finite pattern: it ends after 120ms even if the game event loop is busy.
        CHHapticEvent *event = [[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticContinuous
            parameters:@[strength] relativeTime:0 duration:0.120];
        CHHapticPattern *pattern = [[CHHapticPattern alloc] initWithEvents:@[event] parameters:@[] error:&error];
        id<CHHapticPatternPlayer> player = pattern && !error ? [engine createPlayerWithPattern:pattern error:&error] : nil;
        BOOL started = player && !error && [player startAtTime:CHHapticTimeImmediate error:&error];
        NSLog(@"PORT0R R10 real playback priming strength=0.70 duration=120ms ok=%d error=%@ player=%@",
            started, error, player);
        if (!started || error) { [player stopAtTime:CHHapticTimeImmediate error:nil]; return NO; }
        objc_setAssociatedObject(motor, &primeDoneKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        objc_setAssociatedObject(motor, &primePlayerKey, player, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        // This player never becomes SDL's game player. Its delayed release
        // cannot stop or change a later real pulse.
        __weak id weakMotor = motor;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 500 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
            ReleasePrimePlayer(weakMotor, player);
        });
        return YES;
    }
}
static int SetIntensity(id motor, SEL cmd, float intensity) {
    @synchronized (motor) {
        CHHapticEngine *engine = MotorGet(motor, @"engine");
        TrackMotor(motor, engine);
        // SDL's tiny initialization call constructs/starts the real engines.
        // Do not create a player, send parameters or start playback here.
        if (preparingEngines) { engine.autoShutdownEnabled = NO; return engine ? 0 : -1; }
        if (!hapticsForeground || intensity <= 0) return StopPlayer(motor);
        EndPrimePlayback(motor);
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
            NSLog(@"PORT0R R10 haptic START request=%llu strength=%.4f ok=%d error=%@ player=%@",
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
    NSArray *motors;
    @synchronized (liveMotors) { motors = liveMotors.allObjects; }
    for (id motor in motors) PrimeMotorPlayback(motor);
    NSLog(@"PORT0R R10 engine-only preparation status=%d clear=%d elapsed=%.2fms; separate finite playback priming checked",
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
    NSLog(@"PORT0R R10 haptic recovery installed=%d; engine preparation + finite real playback priming", originalIntensity != NULL);
}
