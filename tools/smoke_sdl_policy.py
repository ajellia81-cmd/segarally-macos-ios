"""Validate the Mac SDL ABI policy without launching the guest game."""
from pathlib import Path
import subprocess

overrides = Path('compatibility/shim/overrides').resolve()
test = Path('build/sdl_policy_smoke.m')
test.write_text('#define PORT0R_POLICY_TEST 1\n#import "' + str(overrides / 'AppKit_SDLPolicy.m') + '"\n' + r'''
#include <assert.h>
static BOOL allowCoinFallback;
static int coinDowns, coinUps;
BOOL Port0rSelectCoinFallbackR3(void) { return allowCoinFallback; }
void Port0rCoinKey(BOOL down) { if (down) coinDowns++; else coinUps++; }
static int deviceCount = 2;
static BOOL backPressed;
BOOL Port0rBackboneSelect(const char *name, int sdlDevices) { return backPressed && name && !strcmp(name, "Backbone Pro"); }
static int NativeDevices(void) { return deviceCount; }
static uint8_t nativeButton;
static uint8_t NativeButton(void *controller, int button) { return nativeButton; }
static const char *NativeName(void *controller) { return controller == (void *)1 ? "Backbone Pro" : "Other pad"; }
static int gateCalls, pollCalls, pumpCalls, waitCalls;
void Port0rWaitForForeground(void) { gateCalls++; }
static int NativePoll(void *event) { pollCalls++; return 7; }
static void NativePump(void) { pumpCalls++; }
static int NativeWait(void *event) { waitCalls++; return 8; }
static int NativeWaitTimeout(void *event, int timeout) { waitCalls++; return timeout; }
static uint32_t seenFlags;
static int forbiddenCalls;
static void Version(PolicyVersion *v) { *v = (PolicyVersion){2,30,3}; }
static void WrongVersion(PolicyVersion *v) { *v = (PolicyVersion){2,32,0}; }
static void *NativeCreate(const char *title, int x, int y, int w, int h, uint32_t flags) {
    seenFlags = flags; return (void *)0x1234;
}
static uint32_t NativeFlags(void *w) { return 0x1001 | 0x2000; }
static int Forbidden(void *w, uint32_t flags) { forbiddenCalls++; return -1; }
int main(void) { @autoreleasepool {
    void *table[PORT0R_SDL_SLOTCOUNT];
    for (int i = 0; i < PORT0R_SDL_SLOTCOUNT; ++i) table[i] = (void *)Forbidden;
    table[PORT0R_SLOT_SDL_GetVersion] = (void *)Version;
    table[PORT0R_SLOT_SDL_CreateWindow] = (void *)NativeCreate;
    table[PORT0R_SLOT_SDL_GetWindowFlags] = (void *)NativeFlags;
    table[PORT0R_SLOT_SDL_PollEvent] = (void *)NativePoll;
    table[PORT0R_SLOT_SDL_PumpEvents] = (void *)NativePump;
    table[PORT0R_SLOT_SDL_WaitEvent] = (void *)NativeWait;
    table[PORT0R_SLOT_SDL_WaitEventTimeout] = (void *)NativeWaitTimeout;
    table[PORT0R_SLOT_SDL_NumJoysticks] = (void *)NativeDevices;
    table[PORT0R_SLOT_SDL_GameControllerGetButton] = (void *)NativeButton;
    table[PORT0R_SLOT_SDL_GameControllerName] = (void *)NativeName;
    assert(ApplyPolicy(table, sizeof table) == 0);
    uint8_t (*readButton)(void *, int) = table[PORT0R_SLOT_SDL_GameControllerGetButton];
    assert(readButton((void *)1, 4) == 0);
    backPressed = YES;
    assert(readButton((void *)1, 4) == 1);
    assert(readButton((void *)1, 5) == 0); // Guide unaffected
    assert(readButton((void *)2, 4) == 0); // other pad unaffected
    backPressed = NO;
    assert(readButton((void *)1, 4) == 0); // release has no stale key
    nativeButton = 1;
    backPressed = YES;
    assert(readButton((void *)1, 4) == 1); // no second keyboard coin
    assert(readButton((void *)2, 5) == 1); // native inputs preserved
    nativeButton = 0; backPressed = NO;
    deviceCount = 1; allowCoinFallback = YES; backPressed = YES;
    assert(readButton((void *)1, 4) == 0 && coinDowns == 1 && coinUps == 0);
    assert(readButton((void *)1, 4) == 0 && coinDowns == 1); // held: no duplicate injection
    backPressed = NO;
    assert(readButton((void *)1, 4) == 0 && coinUps == 1);
    nativeButton = 1;
    assert(readButton((void *)1, 4) == 0 && coinDowns == 2); // native BACK masked to avoid duplicate Coin
    assert(readButton((void *)1, 5) == 1); // Guide untouched
    Port0rReleaseSelectCoinR3();
    assert(coinUps == 2);
    allowCoinFallback = NO;
    assert(readButton((void *)1, 4) == 1 && coinDowns == 2); // other assignments use native path
    nativeButton = 0; backPressed = NO; readButton((void *)1, 4);
    deviceCount = 2;
    puts("PASS: sole Select-Coin assignment produces one keyboard down/up, masks duplicate native BACK and releases on lifecycle change");
    puts("PASS: Select press/release merged into native SDL BACK; Guide/other pads preserved and no duplicate coin injection");
    assert(((int(*)(void *))table[PORT0R_SLOT_SDL_PollEvent])(NULL) == 7);
    ((void(*)(void))table[PORT0R_SLOT_SDL_PumpEvents])();
    assert(((int(*)(void *))table[PORT0R_SLOT_SDL_WaitEvent])(NULL) == 8);
    assert(((int(*)(void *,int))table[PORT0R_SLOT_SDL_WaitEventTimeout])(NULL, 23) == 23);
    assert(gateCalls == 4 && pollCalls == 1 && pumpCalls == 1 && waitCalls == 2);
    puts("PASS: every SDL event-loop entry gates on foreground and preserves native arguments/results");
    void *window = ((void *(*)(const char *,int,int,int,int,uint32_t))table[PORT0R_SLOT_SDL_CreateWindow])("test",0,0,1280,720,0x3001);
    assert(window == (void *)0x1234 && seenFlags == 0x2000);
    assert(((uint32_t(*)(void *))table[PORT0R_SLOT_SDL_GetWindowFlags])(window) == 0x2000);
    assert(((int(*)(void *,uint32_t))table[PORT0R_SLOT_SDL_SetWindowFullscreen])(window,0x1001) == 0);
    assert(((int(*)(void *,uint32_t))table[PORT0R_SLOT_SDL_SetWindowFullscreen])(window,0) == 0);
    assert(((int(*)(void *,const void *))table[PORT0R_SLOT_SDL_SetWindowDisplayMode])(window,NULL) == 0);
    ((void(*)(void *,int,int))table[PORT0R_SLOT_SDL_SetWindowSize])(window,640,360);
    assert(forbiddenCalls == 0);
    assert(table[0] == (void *)Forbidden); // non-window APIs unchanged
    assert(ApplyPolicy(table, sizeof(table)-8) == -1);
    table[PORT0R_SLOT_SDL_GetVersion] = (void *)WrongVersion;
    assert(ApplyPolicy(table, sizeof table) == -1);
    puts("PASS: Mac SDL ABI guard, fullscreen on/off blocked, window/display resize blocked, other APIs preserved");
} return 0; }
''')
subprocess.run(['xcrun','--sdk','macosx','clang','-fobjc-arc','-fsanitize=address',
                '-framework','Foundation',str(test),'-o','build/sdl_policy_smoke'],check=True)
result = subprocess.run(['build/sdl_policy_smoke'],capture_output=True,text=True)
print(result.stdout)
if result.returncode:
    print(result.stderr[-6000:])
    raise SystemExit(result.returncode)

background = (overrides / 'AppKit_Background.m').read_text()
state_code = background[background.index('static _Atomic bool gameActive'):background.index('static BOOL IsGameGPUCaller')]
wait_code = background[background.index('__attribute__((visibility("default"))) void Port0rWaitForForeground'):background.index('static void GameCommit')]
lifecycle_test = Path('build/lifecycle_smoke.m')
lifecycle_test.write_text('#import <Foundation/Foundation.h>\n#import <objc/runtime.h>\n#include <stdatomic.h>\n#include <stdbool.h>\n#include <assert.h>\n' + state_code + wait_code + r"""
int main(void) { @autoreleasepool {
    foregroundCondition = [NSCondition new];
    SetGameActive(NO);
    __block BOOL entered = NO, finished = NO;
    NSCondition *testCondition = [NSCondition new];
    NSThread *worker = [[NSThread alloc] initWithBlock:^{ @autoreleasepool {
        [testCondition lock]; entered = YES; [testCondition broadcast]; [testCondition unlock];
        Port0rWaitForForeground();
        [testCondition lock]; finished = YES; [testCondition broadcast]; [testCondition unlock];
    }}];
    [worker start];
    [testCondition lock];
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
    while (!entered) assert([testCondition waitUntilDate:deadline]);
    assert(!finished);
    [testCondition unlock];
    SetGameActive(YES);
    [testCondition lock];
    while (!finished) assert([testCondition waitUntilDate:deadline]);
    [testCondition unlock];
    SetGameActive(NO);
    CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
    CFRunLoopTimerRef timer = CFRunLoopTimerCreateWithHandler(NULL, start + 0.05, 0, 0, 0,
        ^(CFRunLoopTimerRef t) { SetGameActive(YES); });
    CFRunLoopAddTimer(CFRunLoopGetCurrent(), timer, kCFRunLoopDefaultMode);
    Port0rWaitForForeground();
    assert(atomic_load(&gameActive) && CFAbsoluteTimeGetCurrent() - start >= 0.04);
    CFRunLoopTimerInvalidate(timer); CFRelease(timer);
    puts("PASS: actual background gate blocks worker and main game loops, preserves lifecycle run-loop delivery and resumes");
} return 0; }
""")
subprocess.run(['xcrun','--sdk','macosx','clang','-fobjc-arc','-fsanitize=address',
                '-framework','Foundation',str(lifecycle_test),'-o','build/lifecycle_smoke'],check=True)
subprocess.run(['build/lifecycle_smoke'],check=True,timeout=15)
