"""Validate the Mac SDL ABI policy without launching the guest game."""
from pathlib import Path
import subprocess

overrides = Path('compatibility/shim/overrides').resolve()
test = Path('build/sdl_policy_smoke.m')
test.write_text('#define PORT0R_POLICY_TEST 1\n#import "' + str(overrides / 'AppKit_SDLPolicy.m') + '"\n' + r'''
#include <assert.h>
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
    assert(ApplyPolicy(table, sizeof table) == 0);
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
