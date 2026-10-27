// Keep the original SDL implementation and replace only desktop fullscreen /
// physical-window resizing APIs. Uses SDL's supported dynamic-API mechanism.
#import <Foundation/Foundation.h>
#import <dlfcn.h>
#import <mach-o/dyld.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "Port0rSDLSlots.h"

enum { DesktopFullscreen = 0x1001 };
typedef struct { uint8_t major, minor, patch; } PolicyVersion;
typedef int32_t (*Entry)(uint32_t, void *, uint32_t);
static void *(*createWindow)(const char *, int, int, int, int, uint32_t);
static uint32_t (*getWindowFlags)(void *);
static void *CreateWindow(const char *title, int x, int y, int w, int h, uint32_t flags) {
    return createWindow(title, x, y, w, h, flags & ~DesktopFullscreen);
}
static uint32_t WindowFlags(void *window) { return getWindowFlags(window) & ~DesktopFullscreen; }
static int Fullscreen(void *window, uint32_t flags) {
    NSLog(@"PORT0R iOS fixed fullscreen: ignored SDL fullscreen toggle %u", (unsigned)flags);
    return 0;
}
static int DisplayMode(void *window, const void *mode) { return 0; }
static void WindowSize(void *window, int width, int height) {
    NSLog(@"PORT0R iOS fixed window: ignored desktop resize %dx%d", width, height);
}
extern void Port0rWaitForForeground(void);
static int (*pollEvent)(void *);
static void (*pumpEvents)(void);
static int (*waitEvent)(void *);
static int (*waitEventTimeout)(void *, int);
static int PollEvent(void *event) { Port0rWaitForForeground(); return pollEvent(event); }
static void PumpEvents(void) { Port0rWaitForForeground(); pumpEvents(); }
static int WaitEvent(void *event) { Port0rWaitForForeground(); return waitEvent(event); }
static int WaitEventTimeout(void *event, int timeout) { Port0rWaitForForeground(); return waitEventTimeout(event, timeout); }
extern BOOL Port0rBackboneSelect(const char *name, int sdlDevices);
extern BOOL Port0rSelectCoinFallbackR3(void);
extern void Port0rCoinKey(BOOL down);
static NSObject *coinStateLock;
static BOOL coinHeld, physicalSelectHeld;
static void EnsureCoinState(void) {
    static dispatch_once_t once;
    dispatch_once(&once, ^{ coinStateLock = [NSObject new]; });
}
void Port0rReleaseSelectCoinR3(void) {
    EnsureCoinState();
    @synchronized (coinStateLock) {
        if (coinHeld) Port0rCoinKey(NO);
        coinHeld = physicalSelectHeld = NO;
    }
}
static BOOL RouteSelectCoin(BOOL pressed) {
    EnsureCoinState();
    @synchronized (coinStateLock) {
        if (pressed && !physicalSelectHeld) {
            coinHeld = Port0rSelectCoinFallbackR3();
            if (coinHeld) Port0rCoinKey(YES);
            NSLog(@"PORT0R R3 Select Coin keyboard route=%d", coinHeld);
        } else if (!pressed && physicalSelectHeld) {
            if (coinHeld) Port0rCoinKey(NO);
            coinHeld = NO;
        }
        physicalSelectHeld = pressed;
        return coinHeld;
    }
}

static int (*numJoysticks)(void);
static uint8_t (*getControllerButton)(void *, int);
static const char *(*controllerName)(void *);
static uint8_t ControllerButton(void *controller, int button) {
    uint8_t native = getControllerButton(controller, button);
    // Merge into SDL BACK itself: native settings/rebinding and edge detection remain intact.
    if (button != 4 || !controller) return native;
    const char *name = controllerName(controller);
    BOOL bridge = Port0rBackboneSelect(name, numJoysticks());
    if (numJoysticks() == 1) {
        // Suppress native BACK only while delivering its sole Coin assignment
        // via keyboard 5. This prevents two Coin paths from firing together.
        if (RouteSelectCoin(native || bridge)) return 0;
    } else Port0rReleaseSelectCoinR3();
    return native || bridge ? 1 : 0;
}
static int (*nativeRumble)(void *, uint16_t, uint16_t, uint32_t);
extern void Port0rPrepareControllerEnginesR7(void *, int (*)(void *, uint16_t, uint16_t, uint32_t));
static void *(*nativeControllerOpen)(int);
static void *ControllerOpen(int index) {
    void *controller = nativeControllerOpen(index);
    Port0rPrepareControllerEnginesR7(controller, nativeRumble);
    return controller;
}
static int ApplyPolicy(void *raw, uint32_t bytes) {
    if (!raw || bytes != PORT0R_SDL_SLOTCOUNT * sizeof(void *)) return -1;
    void **table = raw;
    PolicyVersion version = {0};
    if (!table[PORT0R_SLOT_SDL_GetVersion]) return -1;
    ((void (*)(PolicyVersion *))table[PORT0R_SLOT_SDL_GetVersion])(&version);
    if (version.major != 2 || version.minor != 30 || version.patch != 3) return -1;
    nativeRumble = table[PORT0R_SLOT_SDL_GameControllerRumble];
    nativeControllerOpen = table[PORT0R_SLOT_SDL_GameControllerOpen];
    if (!nativeRumble || !nativeControllerOpen) return -1;
    table[PORT0R_SLOT_SDL_GameControllerOpen] = (void *)ControllerOpen;

    numJoysticks = table[PORT0R_SLOT_SDL_NumJoysticks];
    getControllerButton = table[PORT0R_SLOT_SDL_GameControllerGetButton];
    controllerName = table[PORT0R_SLOT_SDL_GameControllerName];
    if (!getControllerButton || !controllerName || !numJoysticks) return -1;
    table[PORT0R_SLOT_SDL_GameControllerGetButton] = (void *)ControllerButton;
    pollEvent = table[PORT0R_SLOT_SDL_PollEvent];
    pumpEvents = table[PORT0R_SLOT_SDL_PumpEvents];
    waitEvent = table[PORT0R_SLOT_SDL_WaitEvent];
    waitEventTimeout = table[PORT0R_SLOT_SDL_WaitEventTimeout];
    createWindow = table[PORT0R_SLOT_SDL_CreateWindow];
    getWindowFlags = table[PORT0R_SLOT_SDL_GetWindowFlags];
    if (!createWindow || !getWindowFlags) return -1;
    table[PORT0R_SLOT_SDL_PollEvent] = (void *)PollEvent;
    table[PORT0R_SLOT_SDL_PumpEvents] = (void *)PumpEvents;
    table[PORT0R_SLOT_SDL_WaitEvent] = (void *)WaitEvent;
    table[PORT0R_SLOT_SDL_WaitEventTimeout] = (void *)WaitEventTimeout;
    table[PORT0R_SLOT_SDL_CreateWindow] = (void *)CreateWindow;
    table[PORT0R_SLOT_SDL_GetWindowFlags] = (void *)WindowFlags;
    table[PORT0R_SLOT_SDL_SetWindowFullscreen] = (void *)Fullscreen;
    table[PORT0R_SLOT_SDL_SetWindowDisplayMode] = (void *)DisplayMode;
    table[PORT0R_SLOT_SDL_SetWindowSize] = (void *)WindowSize;
    NSLog(@"PORT0R SDL 2.30.3 policy enabled: iOS window always fills screen; desktop fullscreen changes blocked");
    return 0;
}

#ifndef PORT0R_POLICY_TEST
__attribute__((visibility("default")))
int32_t SDL_DYNAPI_entry(uint32_t version, void *table, uint32_t size) {
    if (version != 1 || size != PORT0R_SDL_SLOTCOUNT * sizeof(void *)) return -1;
    Entry original = NULL;
    for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
        const char *path = _dyld_get_image_name(i);
        if (!path || strcmp(strrchr(path, '/') ?: path, "/port0r")) continue;
        void *image = dlopen(path, RTLD_NOLOAD | RTLD_LAZY);
        if (image) original = (Entry)dlsym(image, "SDL_DYNAPI_entry");
        if (original) break;
    }
    if (!original || original == SDL_DYNAPI_entry) {
        NSLog(@"PORT0R fullscreen policy: original SDL entry not found");
        return -1;
    }
    int32_t result = original(version, table, size);
    return result < 0 ? result : ApplyPolicy(table, size);
}

__attribute__((constructor)) static void SDLPolicyInit(void) {
    Dl_info info = {0};
    if (dladdr((void *)SDLPolicyInit, &info) && info.dli_fname)
        setenv("SDL_DYNAMIC_API", info.dli_fname, 1);
    // Restore only the desktop fullscreen preference; preserve every other key.
    for (NSString *base in @[@"Documents/Port0r/srallyc", @"Library/Application Support/Port0r/srallyc"]) {
        NSString *path = [[NSHomeDirectory() stringByAppendingPathComponent:base] stringByAppendingPathComponent:@"tcvr-settings-v1.txt"];
        NSString *text = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];
        if (!text) continue;
        NSRegularExpression *rx = [NSRegularExpression regularExpressionWithPattern:@"(?m)^(flat\\.fullscreen[ \\t]*=[ \\t]*)([^\\r\\n]*)" options:0 error:nil];
        NSTextCheckingResult *m = [rx firstMatchInString:text options:0 range:NSMakeRange(0, text.length)];
        if (!m || [[text substringWithRange:[m rangeAtIndex:2]] isEqualToString:@"0"]) continue;
        NSString *backup = [path stringByAppendingString:@".before-ios-fullscreen"];
        if (![NSFileManager.defaultManager fileExistsAtPath:backup])
            [NSFileManager.defaultManager copyItemAtPath:path toPath:backup error:nil];
        NSString *updated = [text stringByReplacingCharactersInRange:[m rangeAtIndex:2] withString:@"0"];
        NSError *error = nil;
        BOOL saved = [updated writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:&error];
        NSLog(@"PORT0R fullscreen setting reset saved=%d error=%@", saved, error);
    }
}
#endif
