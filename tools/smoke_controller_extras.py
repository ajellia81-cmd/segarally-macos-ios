"""Exercise actual haptic warm-up with fake motors, and Guide settings storage.

Uses native Apple SDK types but never starts a real haptic engine or controller.
Physical controller latency, gestures and delivery still require device tests.
"""
from pathlib import Path
import subprocess

overrides = Path('compatibility/shim/overrides').resolve()
test = Path('build/controller_extras_smoke.m')
guide = (overrides / 'AppKit_Guide.m').read_text()
guide_helpers = (
    guide[guide.index('static NSString *GuideSettingsPath'):guide.index('static void GuideEmit')] +
    guide[guide.index('static NSString *GuideTitle'):guide.index('static void ReleaseGuides')] +
    guide[guide.index('static BOOL SaveGuide'):guide.index('static void ConfigureGuides')]
)
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
@interface TestEngine : NSObject @end
@implementation TestEngine
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
@end
@implementation SDL_RumbleMotor
@synthesize engine = _testEngine;
@synthesize player = _testPlayer;
- (int)setIntensity:(float)intensity { originalCalls++; lastIntensity = intensity; return 0; }
@end
''' + '#import "' + str(overrides / 'AppKit_Haptics.m') + '"\n' + r'''
static SDL_RumbleMotor *motor;
static int Rumble(void *controller, uint16_t low, uint16_t high, uint32_t duration) {
    return [motor setIntensity:(float)low / 65535.0f];
}
static int Supported(void *controller) { return 1; }
static int Unsupported(void *controller) { return 0; }
static NSString *testHome;
static NSString *GuideTestHome(void) { return testHome; }
#define NSHomeDirectory GuideTestHome
''' + guide_helpers + r'''
#undef NSHomeDirectory
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
    puts("PASS: actual SDL motor warm-up creates and retains a silent player, reuses it and preserves real intensity; unsupported motors skipped");
    testHome = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    for (NSNumber *key in @[@(-1), @23, @36, @53, @9, @14, @12]) {
        assert(SaveGuide(key.integerValue));
        NSDictionary *saved = [NSDictionary dictionaryWithContentsOfFile:GuideSettingsPath()];
        assert([saved[@"guideKey"] isEqual:key]);
        assert(GuideTitle(key.integerValue).length > 0);
    }
    [NSFileManager.defaultManager removeItemAtPath:testHome error:nil];
    puts("PASS: all Guide choices persist in guest-specific settings and have labels");
} return 0; }
''')
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fsanitize=address',
                '-framework', 'Foundation', '-framework', 'CoreHaptics', '-framework', 'GameController',
                str(test), '-o', 'build/controller_extras_smoke'], check=True)
subprocess.run(['build/controller_extras_smoke'], check=True, timeout=20)
