// SDL 2.30.3 creates its actual MFi engines lazily on the first non-zero
// rumble. Initialize those same motors before gameplay, never a spare engine.
#import <Foundation/Foundation.h>
#import <CoreHaptics/CoreHaptics.h>
#import <GameController/GameController.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <stdint.h>
#include <stdbool.h>

static IMP originalIntensity;
static _Thread_local bool warmingMotors;
static BOOL PrepareSilentPlayer(id motor) {
    SEL engineSelector = NSSelectorFromString(@"engine");
    SEL playerSelector = NSSelectorFromString(@"player");
    SEL setPlayer = NSSelectorFromString(@"setPlayer:");
    if (![motor respondsToSelector:engineSelector] || ![motor respondsToSelector:playerSelector] ||
        ![motor respondsToSelector:setPlayer]) return NO;
    if (((id (*)(id,SEL))objc_msgSend)(motor, playerSelector)) return YES;
    CHHapticEngine *engine = ((id (*)(id,SEL))objc_msgSend)(motor, engineSelector);
    if (!engine) return NO;
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
    if (warmingMotors) {
        PrepareSilentPlayer(motor);
        intensity = 0; // never send the warm-up's non-zero request to hardware
    }
    return ((int (*)(id,SEL,float))originalIntensity)(motor, cmd, intensity);
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
    NSLog(@"PORT0R SDL silent haptic warm-up installed=%d", originalIntensity != NULL);
}
