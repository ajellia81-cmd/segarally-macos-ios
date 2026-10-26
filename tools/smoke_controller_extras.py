"""R6: verify real requests are not primed, suppressed or rewritten.

Mock the original SDL motor, without starting physical CoreHaptics hardware.
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
static int nativeStatus;
static float lastIntensity, firstStartedIntensity = -1;
@interface TestPlayer : NSObject
@property float intensity;
@end
@implementation TestPlayer
@end
@interface TestEngine : NSObject
@property(nonatomic,copy) void (^stoppedHandler)(CHHapticEngineStoppedReason);
@property(nonatomic,copy) void (^resetHandler)(void);
@end
@implementation TestEngine
- (BOOL)startAndReturnError:(NSError **)error { engineStarts++; return YES; }
@end
@interface SDL_RumbleMotor : NSObject
@property(nonatomic,strong) TestEngine *engine;
@property(nonatomic,strong) TestPlayer *player;
@property bool active;
- (int)setIntensity:(float)value;
- (void)cleanup;
@end
@implementation SDL_RumbleMotor
- (int)setIntensity:(float)value {
    originalCalls++; lastIntensity = value;
    if (nativeStatus) return nativeStatus;
    if (value == 0) {
        if (self.player && self.active) stops++;
        self.active = false;
        return 0;
    }
    // Model original SDL's lazy player creation on a real nonzero request.
    if (!self.player) { self.player = [TestPlayer new]; playerCreations++; self.active = false; }
    self.player.intensity = value;
    if (!self.active) {
        self.active = true;
        if (starts++ == 0) firstStartedIntensity = value;
    }
    return 0;
}
- (void)cleanup { self.player = nil; self.engine = nil; }
@end
''' + '#import "' + str(overrides / 'AppKit_Haptics.m') + '"\n' + r'''
int main(void) { @autoreleasepool {
    assert(originalIntensity != NULL && originalCalls == 0 && playerCreations == 0);
    SDL_RumbleMotor *motor = [SDL_RumbleMotor new]; motor.engine = [TestEngine new];
    assert(motor.player == nil && engineStarts == 0 && starts == 0);
    assert([motor setIntensity:0.75f] == 0);
    assert(originalCalls == 1 && lastIntensity == 0.75f && firstStartedIntensity == 0.75f);
    assert(playerCreations == 1 && starts == 1 && motor.player.intensity == 0.75f);
    [motor setIntensity:0];
    assert(originalCalls == 2 && !motor.active && stops == 1);
    [motor setIntensity:0.5f];
    assert(originalCalls == 3 && starts == 2 && motor.player.intensity == 0.5f);
    TestEngine *same = motor.engine;
    hapticsForeground = NO;
    same.stoppedHandler(CHHapticEngineStoppedReasonApplicationSuspended);
    assert(motor.engine == same && motor.player == nil);
    [motor setIntensity:0.6f];
    assert(lastIntensity == 0 && playerCreations == 1 && engineStarts == 0);
    ResumeMotors();
    assert(engineStarts == 1 && motor.player == nil && playerCreations == 1);
    [motor setIntensity:0.6f];
    assert(lastIntensity == 0.6f && playerCreations == 2 && starts == 3);
    same.resetHandler();
    assert(motor.player == nil);
    [motor setIntensity:0.25f];
    assert(engineStarts == 2 && playerCreations == 3 && lastIntensity == 0.25f);
    nativeStatus = -7;
    assert([motor setIntensity:0.42f] == -7 && lastIntensity == 0.42f);
    nativeStatus = 0;
    [motor cleanup];
    assert(motor.engine == nil && motor.player == nil && liveMotors.count == 0);
    same.stoppedHandler(CHHapticEngineStoppedReasonApplicationSuspended);
    same.resetHandler();
    assert(motor.engine == nil && motor.player == nil && liveMotors.count == 0);
    puts("PASS: no synthetic startup request/player; first real intensity reaches original SDL unchanged, zero stops preserved and native errors forwarded");
    puts("PASS: engine retained after suspension, foreground restart creates no player; real requests restore output and reset/cleanup remain safe");
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
