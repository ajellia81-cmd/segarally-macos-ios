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
static int playerCreations, starts, stops, originalCalls;
static float lastIntensity;
@interface TestPlayer : NSObject <CHHapticPatternPlayer> { float _intensity; }
@property float testIntensity;
@end
@implementation TestPlayer
@synthesize testIntensity = _intensity;
- (BOOL)sendParameters:(NSArray<CHHapticDynamicParameter *> *)parameters atTime:(NSTimeInterval)time error:(NSError **)error {
    self.testIntensity = parameters.firstObject.value; return YES;
}
- (BOOL)startAtTime:(NSTimeInterval)time error:(NSError **)error {
    assert(self.testIntensity == 0); starts++; return YES;
}
- (BOOL)stopAtTime:(NSTimeInterval)time error:(NSError **)error { stops++; return YES; }
- (BOOL)cancelAndReturnError:(NSError **)error { return YES; }
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
int main(void) { @autoreleasepool {
    assert(originalIntensity != NULL);
    motor = [SDL_RumbleMotor new]; motor.engine = [TestEngine new];
    Port0rWarmControllerHaptics((void *)0x1234, Rumble, Rumble, Supported, Supported);
    assert(playerCreations == 1 && starts == 1 && stops == 1);
    assert(originalCalls == 4 && lastIntensity == 0 && motor.player != nil);
    Port0rWarmControllerHaptics((void *)0x1234, Rumble, Rumble, Supported, Supported);
    assert(playerCreations == 1 && starts == 1); // same player reused
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
    assert(playerCreations == 2 && starts == 2 && stops == 2);
    [motor setIntensity:0.5f]; assert(lastIntensity == 0.5f);
    motor.engine.resetHandler();
    assert(motor.player == nil);
    [motor setIntensity:0.25f];
    assert(engineStarts == 2 && playerCreations == 3 && lastIntensity == 0.25f);
    [motor cleanup];
    assert(motor.engine == nil && motor.player == nil && liveMotors.count == 0);
    sameEngine.stoppedHandler(CHHapticEngineStoppedReasonApplicationSuspended);
    sameEngine.resetHandler();
    assert(motor.engine == nil && motor.player == nil && liveMotors.count == 0);
    puts("PASS: stopped/reset engines retained, foreground engine/player recovery and normal vibration restored");
    puts("PASS: actual SDL motor warm-up creates and retains a silent player, reuses it and preserves real intensity; unsupported motors skipped");
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
    testControllers = @[pad];
    assert(!Port0rBackboneSelect("Backbone Pro"));
    button.isPressed = YES;
    assert(Port0rBackboneSelect("Backbone Pro"));
    assert(button.preferredSystemGestureState == GCSystemGestureStateDisabled);
    assert(!Port0rBackboneSelect("Other pad") && !Port0rBackboneSelect(NULL));
    button.isPressed = NO; assert(!Port0rBackboneSelect("Backbone Pro"));
    profile.buttonOptions = nil; profile.buttons = @{@"Button Share":button};
    button.isPressed = YES; assert(Port0rBackboneSelect("Backbone Pro"));
    testControllers = @[pad,pad]; assert(!Port0rBackboneSelect("Backbone Pro"));
    testControllers = @[]; assert(!Port0rBackboneSelect("Backbone Pro"));
    method_setImplementation(method, original);
    puts("PASS: actual Backbone bridge polls press/release, handles Share fallback/disconnect and refuses ambiguous pads");
} return 0; }
''')
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fsanitize=address',
                '-framework', 'Foundation', '-framework', 'GameController',
                str(select_test), '-o', 'build/backbone_select_smoke'], check=True)
subprocess.run(['build/backbone_select_smoke'], check=True, timeout=20)
