"""Exercise actual haptic warm-up with fake motors, and foreground recovery.

Uses native Apple SDK types but never starts a real haptic engine or controller.
Physical controller latency, gestures and delivery still require device tests.
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
static int playerCreations, starts, stops, originalCalls;
static float lastIntensity;
@interface TestPlayer : NSObject <CHHapticPatternPlayer> { float _intensity; }
@property float testIntensity;
@property int parameterUpdates;
@property int startCalls;
@property BOOL cancelled;
@end
@implementation TestPlayer
@synthesize testIntensity = _intensity;
- (BOOL)sendParameters:(NSArray<CHHapticDynamicParameter *> *)parameters atTime:(NSTimeInterval)time error:(NSError **)error {
    self.parameterUpdates++; self.testIntensity = parameters.firstObject.value; return YES;
}
- (BOOL)startAtTime:(NSTimeInterval)time error:(NSError **)error {
    assert(self.testIntensity == 0); self.startCalls++; starts++; return YES;
}
- (BOOL)stopAtTime:(NSTimeInterval)time error:(NSError **)error { stops++; return YES; }
- (BOOL)cancelAndReturnError:(NSError **)error { self.cancelled = YES; return YES; }
- (BOOL)scheduleParameterCurve:(CHHapticParameterCurve *)curve atTime:(NSTimeInterval)time error:(NSError **)error { return YES; }
@end
static int engineStarts;
@interface TestEngine : NSObject {
    void (^_stopped)(CHHapticEngineStoppedReason);
    void (^_reset)(void);
}
@property(nonatomic,copy) void (^stoppedHandler)(CHHapticEngineStoppedReason);
@property(nonatomic,copy) void (^resetHandler)(void);
@end
@implementation TestEngine
@synthesize stoppedHandler = _stopped;
@synthesize resetHandler = _reset;
- (BOOL)startAndReturnError:(NSError **)error { engineStarts++; return YES; }
- (id<CHHapticPatternPlayer>)createPlayerWithPattern:(CHHapticPattern *)pattern error:(NSError **)error {
    assert(pattern != nil); playerCreations++; return [TestPlayer new];
}
@end
@interface SDL_RumbleMotor : NSObject {
    TestEngine *_testEngine;
    id<CHHapticPatternPlayer> _testPlayer;
}
@property(nonatomic, strong) TestEngine *engine;
@property bool active;
@property(nonatomic, strong) id<CHHapticPatternPlayer> player;
- (int)setIntensity:(float)intensity;
- (void)cleanup;
@end
@implementation SDL_RumbleMotor
@synthesize engine = _testEngine;
@synthesize player = _testPlayer;
- (int)setIntensity:(float)intensity { originalCalls++; lastIntensity = intensity; return 0; }
- (void)cleanup { self.player = nil; self.engine = nil; }
@end
''' + '#import "' + str(overrides / 'AppKit_Haptics.m') + '"\n' + r'''
static SDL_RumbleMotor *motor;
static int Rumble(void *controller, uint16_t low, uint16_t high, uint32_t duration) {
    return [motor setIntensity:(float)low / 65535.0f];
}
static int Supported(void *controller) { return 1; }
static int Unsupported(void *controller) { return 0; }
static int realStarts;
static int SimulatedFirstStart(id object, SEL cmd, float intensity) {
    SDL_RumbleMotor *m = object;
    TestPlayer *p = (TestPlayer *)m.player;
    p.testIntensity = intensity;
    if (intensity > 0 && !m.active) {
        // Model a freshly started retained player resetting pre-start controls.
        p.testIntensity = 0;
        m.active = true; realStarts++;
    } else if (intensity == 0) m.active = false;
    return 0;
}
int main(void) { @autoreleasepool {
    assert(originalIntensity != NULL);
    motor = [SDL_RumbleMotor new]; motor.engine = [TestEngine new];
    Port0rWarmControllerHaptics((void *)0x1234, Rumble, Rumble, Supported, Supported);
    assert(playerCreations == 2 && starts == 1 && stops == 1);
    TestPlayer *fresh = (TestPlayer *)motor.player;
    assert(fresh.parameterUpdates == 0 && fresh.startCalls == 0 && !fresh.cancelled);
    assert(originalCalls == 4 && lastIntensity == 0 && motor.player != nil);
    Port0rWarmControllerHaptics((void *)0x1234, Rumble, Rumble, Supported, Supported);
    assert(playerCreations == 2 && starts == 1); // existing fresh output reused; no extra preparation
    [motor setIntensity:0.75f];
    assert(lastIntensity == 0.75f && !warmingMotors); // real vibration preserved
    int calls = originalCalls;
    Port0rWarmControllerHaptics((void *)0x1234, Rumble, Rumble, Unsupported, Unsupported);
    assert(originalCalls == calls);
    hapticsForeground = NO;
    TestEngine *sameEngine = motor.engine;
    motor.engine.stoppedHandler(CHHapticEngineStoppedReasonApplicationSuspended);
    assert(motor.engine == sameEngine && motor.player == nil);
    assert([objc_getAssociatedObject(motor, &needsRestartKey) boolValue]);
    [motor setIntensity:0.5f]; assert(lastIntensity == 0 && engineStarts == 0);
    ResumeMotors();
    assert(engineStarts == 1 && motor.engine == sameEngine && motor.player != nil);
    assert(playerCreations == 4 && starts == 2 && stops == 2);
    assert(((TestPlayer *)motor.player).parameterUpdates == 0 && ((TestPlayer *)motor.player).startCalls == 0);
    [motor setIntensity:0.5f]; assert(lastIntensity == 0.5f);
    motor.engine.resetHandler();
    assert(motor.player == nil);
    [motor setIntensity:0.25f];
    assert(engineStarts == 2 && playerCreations == 6 && lastIntensity == 0.25f);
    [motor cleanup];
    assert(motor.engine == nil && motor.player == nil && liveMotors.count == 0);
    sameEngine.stoppedHandler(CHHapticEngineStoppedReasonApplicationSuspended);
    sameEngine.resetHandler();
    assert(motor.engine == nil && motor.player == nil && liveMotors.count == 0);
    motor = [SDL_RumbleMotor new]; motor.engine = [TestEngine new];
    assert(PrepareSilentPlayer(motor));
    originalIntensity = (IMP)SimulatedFirstStart;
    assert([motor setIntensity:0.6f] == 0);
    assert(fabsf(((TestPlayer *)motor.player).testIntensity - 0.6f) < 0.00001f && realStarts == 1);
    assert([motor setIntensity:0.8f] == 0);
    assert(fabsf(((TestPlayer *)motor.player).testIntensity - 0.8f) < 0.00001f && realStarts == 1);
    assert([motor setIntensity:0] == 0);
    assert([motor setIntensity:0.4f] == 0);
    assert(fabsf(((TestPlayer *)motor.player).testIntensity - 0.4f) < 0.00001f && realStarts == 2);
    puts("PASS: first actual haptic request restores requested intensity after start, with no extra event; later bursts preserved");
    puts("PASS: stopped/reset engines retained, foreground engine/player recovery and normal vibration restored");
    puts("PASS: actual SDL motor warm-up is disposable; real output player has never started or received zero intensity; first request and recovery intensity preserved");
} return 0; }
''')
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fsanitize=address',
                '-framework', 'Foundation', '-framework', 'CoreHaptics', '-framework', 'GameController',
                str(test), '-o', 'build/controller_extras_smoke'], check=True)
subprocess.run(['build/controller_extras_smoke'], check=True, timeout=20)

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
