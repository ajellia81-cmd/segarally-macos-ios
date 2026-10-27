"""R10: finite real playback priming, exact game strength and checked playback.
Mock CoreHaptics hardware; keep the actual pattern construction and SDL hooks.
"""
from pathlib import Path
import subprocess
overrides = Path('compatibility/shim/overrides').resolve()
test = Path('build/controller_extras_smoke.m')
test.write_text(r'''
#import <Foundation/Foundation.h>
#import <CoreHaptics/CoreHaptics.h>
#import <GameController/GameController.h>
#include <assert.h>
#include <math.h>
static int originalCalls, playerCreations, starts, stops, engineStarts;
static BOOL failCreate, failStart, failStop, failEngine;
static float firstStartedIntensity = -1, createdIntensity;
static double createdDuration;
static NSError *Failure(void) { return [NSError errorWithDomain:@"TestHaptics" code:7 userInfo:nil]; }
static void FindIntensity(id value) {
    if ([value isKindOfClass:NSDictionary.class]) {
        if (value[@"EventDuration"]) createdDuration = [value[@"EventDuration"] doubleValue];
        if ([value[@"ParameterID"] isEqual:@"HapticIntensity"]) createdIntensity = [value[@"ParameterValue"] floatValue];
        for (id child in [value allValues]) FindIntensity(child);
    } else if ([value isKindOfClass:NSArray.class]) {
        for (id child in value) FindIntensity(child);
    }
}
@interface TestPlayer : NSObject
@property float intensity;
@property double duration;
@end
@implementation TestPlayer
- (BOOL)startAtTime:(NSTimeInterval)time error:(NSError **)error {
    starts++;
    if (failStart) { if (error) *error = Failure(); return NO; }
    if (firstStartedIntensity < 0) firstStartedIntensity = self.intensity;
    return YES;
}
- (BOOL)stopAtTime:(NSTimeInterval)time error:(NSError **)error {
    stops++;
    if (failStop) { if (error) *error = Failure(); return NO; }
    return YES;
}
- (BOOL)sendParameters:(NSArray *)parameters atTime:(NSTimeInterval)time error:(NSError **)error {
    assert(!"R10 must not send dynamic zero/intensity parameters"); return NO;
}
@end
@interface TestEngine : NSObject
@property(nonatomic,copy) void (^stoppedHandler)(CHHapticEngineStoppedReason);
@property(nonatomic,copy) void (^resetHandler)(void);
@property BOOL autoShutdownEnabled;
@end
@implementation TestEngine
- (BOOL)startAndReturnError:(NSError **)error {
    engineStarts++;
    if (failEngine) { if (error) *error = Failure(); return NO; }
    return YES;
}
- (id)createPlayerWithPattern:(CHHapticPattern *)pattern error:(NSError **)error {
    if (failCreate) { if (error) *error = Failure(); return nil; }
    playerCreations++; createdIntensity = -1; createdDuration = -1;
    NSError *exportError = nil;
    FindIntensity([pattern exportDictionaryAndReturnError:&exportError]);
    assert(!exportError);
    assert(createdIntensity >= 0 && createdIntensity <= 1);
    TestPlayer *player = [TestPlayer new]; player.intensity = createdIntensity; player.duration = createdDuration; return player;
}
@end
@interface SDL_RumbleMotor : NSObject
@property(nonatomic,strong) TestEngine *engine;
@property(nonatomic,strong) TestPlayer *player;
@property bool active;
- (int)setIntensity:(float)value;
- (void)cleanup;
@end
@implementation SDL_RumbleMotor
- (int)setIntensity:(float)value { originalCalls++; return -99; }
- (void)cleanup { self.player = nil; self.engine = nil; }
@end
''' + '#import "' + str(overrides / 'AppKit_Haptics.m') + '"\n' + r'''
static SDL_RumbleMotor *preparedMotor;
static int primeCalls;
static int Prime(void *controller, uint16_t low, uint16_t high, uint32_t duration) {
    primeCalls++;
    assert(controller == (void *)1);
    assert((primeCalls == 1 && low == 1 && high == 1 && duration == 1) ||
           (primeCalls == 2 && low == 0 && high == 0 && duration == 0));
    return [preparedMotor setIntensity:(float)low / 65535];
}
int main(void) { @autoreleasepool {
    assert(originalIntensity != NULL && originalCalls == 0 && playerCreations == 0);
    SDL_RumbleMotor *motor = [SDL_RumbleMotor new]; motor.engine = [TestEngine new];
    preparedMotor = motor;
    Port0rPrepareControllerEnginesR7((void *)1, Prime);
    assert(primeCalls == 2 && playerCreations == 1 && starts == 1 && stops == 0 && originalCalls == 0);
    TestPlayer *warm = objc_getAssociatedObject(motor, &primePlayerKey);
    assert(warm && fabs(warm.intensity - 0.7f) < 0.0001 && fabs(warm.duration - 0.120) < 0.0001);
    assert(PrimeMotorPlayback(motor) && playerCreations == 1 && starts == 1); // once per motor
    playerCreations = starts = stops = 0; firstStartedIntensity = -1;
    assert(!motor.engine.autoShutdownEnabled && motor.player == nil);
    assert([motor setIntensity:0.75f] == 0);
    assert(firstStartedIntensity == 0.75f && playerCreations == 1 && starts == 1 && motor.active);
    assert(stops == 1 && objc_getAssociatedObject(motor, &primePlayerKey) == nil); // game cancels only warm player
    TestPlayer *game = motor.player;
    ReleasePrimePlayer(motor, warm); // stale warm completion cannot touch game playback
    assert(motor.player == game && motor.active && stops == 1);
    stops = 0;
    assert([motor setIntensity:0.75f] == 0 && starts == 1); // same active strength: no restart
    assert([motor setIntensity:0.5f] == 0);
    assert(starts == 2 && stops == 1 && motor.player.intensity == 0.5f);
    assert([motor setIntensity:0] == 0 && motor.player == nil && !motor.active && stops == 2);
    TestEngine *same = motor.engine;
    hapticsForeground = NO;
    same.stoppedHandler(CHHapticEngineStoppedReasonApplicationSuspended);
    assert(motor.engine == same && motor.player == nil);
    assert([motor setIntensity:0.6f] == 0 && playerCreations == 2);
    ResumeMotors();
    assert(engineStarts == 1 && motor.player == nil && playerCreations == 2);
    assert([motor setIntensity:0.6f] == 0 && playerCreations == 3 && starts == 3);
    same.resetHandler();
    assert(motor.player == nil);
    assert([motor setIntensity:0.25f] == 0 && engineStarts == 2 && playerCreations == 4);
    [motor setIntensity:0];
    failStart = YES;
    assert([motor setIntensity:0.42f] == -1 && motor.player == nil && !motor.active);
    failStart = NO; failCreate = YES;
    assert([motor setIntensity:0.42f] == -1 && motor.player == nil);
    failCreate = NO;
    assert([motor setIntensity:0.42f] == 0);
    failStop = YES;
    assert([motor setIntensity:0] == -1 && !motor.active);
    failStop = NO; same.resetHandler(); failEngine = YES;
    assert([motor setIntensity:0.42f] == -1 && motor.player == nil);
    failEngine = NO;
    [motor cleanup];
    assert(motor.engine == nil && motor.player == nil && liveMotors.count == 0);
    same.stoppedHandler(CHHapticEngineStoppedReasonApplicationSuspended);
    same.resetHandler();
    assert(motor.engine == nil && motor.player == nil && originalCalls == 0);
    SDL_RumbleMotor *failed = [SDL_RumbleMotor new]; failed.engine = [TestEngine new];
    failStart = YES;
    assert(!PrimeMotorPlayback(failed) && ![objc_getAssociatedObject(failed, &primeDoneKey) boolValue]);
    failStart = NO;
    assert(PrimeMotorPlayback(failed) && [objc_getAssociatedObject(failed, &primeDoneKey) boolValue]);
    assert(failed.player == nil && !failed.active);
    [failed cleanup];
    puts("PASS: startup priming uses a separate finite 70% / 120ms player once; first game cancels only warm playback, stale completion cannot affect game, failed priming can be retried");
    puts("PASS: changed strength replaces player, zero stops, background/reset recover engines without playback; create/start/stop/restart failures propagate");
} return 0; }
''')
subprocess.run(['xcrun','--sdk','macosx','clang','-fobjc-arc','-fsanitize=address',
                '-framework','Foundation','-framework','CoreHaptics','-framework','GameController',
                str(test),'-o','build/controller_extras_smoke'],check=True)
subprocess.run(['build/controller_extras_smoke'],check=True,timeout=20)

# Exercise the real polling bridge with controlled GameController snapshots.
select_test = Path('build/backbone_select_smoke.m')
select_test.write_text('#define PORT0R_BACKBONE_TEST 1\n#import "' + str(overrides / 'AppKit_Backbone.m') + '"\n' + r'''
#include <assert.h>
#import <objc/runtime.h>
static NSArray *testControllers;
@interface SelectButton : NSObject
@property BOOL isPressed;
@property GCSystemGestureState preferredSystemGestureState;
@end
@implementation SelectButton
@end
@interface SelectProfile : NSObject
@property(strong) id buttonOptions;
@property(strong) NSDictionary *buttons;
@end
@implementation SelectProfile
@end
@interface SelectController : NSObject
@property(copy) NSString *vendorName;
@property(copy) NSString *productCategory;
@property(strong) SelectProfile *extendedGamepad;
@property(strong) SelectProfile *physicalInputProfile;
@end
@implementation SelectController
@end
static NSArray *Controllers(id self, SEL cmd) { return testControllers; }
int main(void) { @autoreleasepool {
    Method method = class_getClassMethod(GCController.class, @selector(controllers));
    IMP original = method_setImplementation(method, (IMP)Controllers);
    SelectButton *button = [SelectButton new];
    SelectProfile *profile = [SelectProfile new]; profile.buttonOptions = button;
    SelectController *pad = [SelectController new];
    pad.vendorName = @"Backbone"; pad.productCategory = @"Pro";
    pad.extendedGamepad = profile; pad.physicalInputProfile = profile;
    assert(CoinOnlySelection(nil) && CoinOnlySelection(@"# empty defaults"));
    assert(CoinOnlySelection(@"pad.coin=SELECT\npad.menu=START"));
    assert(CoinOnlySelection(@"pad.coin SELECT\npad.menu START"));
    assert(!CoinOnlySelection(@"pad.coin=GUIDE"));
    assert(!CoinOnlySelection(@"pad.coin=SELECT\npad.start=SELECT"));
    assert(!CoinOnlySelection(@"pad.coin"));
    testControllers = @[pad];
    assert(!Port0rBackboneSelect("Backbone Pro", 2));
    button.isPressed = YES;
    assert(Port0rBackboneSelect("Backbone Pro", 2));
    assert(button.preferredSystemGestureState == GCSystemGestureStateDisabled);
    assert(!Port0rBackboneSelect("Other pad", 2) && !Port0rBackboneSelect(NULL, 2));
    pad.vendorName = @"Generic Controller";
    assert(Port0rBackboneSelect("Generic Controller", 1));
    assert(Port0rBackboneSelect("Backbone Pro", 1)); // SDL and GC can report different names
    assert(!Port0rBackboneSelect("Generic Controller", 2));
    pad.vendorName = @"Backbone";
    button.isPressed = NO; assert(!Port0rBackboneSelect("Backbone Pro", 2));
    SelectButton *share = [SelectButton new]; share.isPressed = YES;
    profile.buttons = @{@"Button Share":share};
    assert(Port0rBackboneSelect("Backbone Pro", 2)); // Options exists but Share is the pressed physical input
    assert(share.preferredSystemGestureState == GCSystemGestureStateDisabled);
    share.isPressed = NO;
    profile.buttonOptions = nil; profile.buttons = @{@"Button Share":button};
    button.isPressed = YES; assert(Port0rBackboneSelect("Backbone Pro", 2));
    testControllers = @[pad,pad]; assert(!Port0rBackboneSelect("Backbone Pro", 2));
    testControllers = @[]; assert(!Port0rBackboneSelect("Backbone Pro", 2));
    method_setImplementation(method, original);
    puts("PASS: actual Select bridge polls press/release, handles generic single-pad names and simultaneous Options/Share objects, refuses ambiguous pads");
} return 0; }
''')
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fsanitize=address',
                '-framework', 'Foundation', '-framework', 'GameController',
                str(select_test), '-o', 'build/backbone_select_smoke'], check=True)
subprocess.run(['build/backbone_select_smoke'], check=True, timeout=20)
