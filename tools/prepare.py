"""Apply narrowly scoped, reproducible adaptations to the pinned converter."""
from pathlib import Path
import shutil
import re
import subprocess
from native_guide import patch as add_native_guide
from native_first_haptic import patch as fix_first_haptic

root = Path('compatibility')
src = Path('extracted/Port0r Rally.app/Contents')
executable = src / 'MacOS/port0r'
executable.write_bytes(fix_first_haptic(add_native_guide(executable.read_bytes())))
print("Fixed native first-knock discard: preserve all other haptic gates")
print('Extended original Gamepad menu to 13 choices, including Guide; native key 110')
# Optional cockpit packs are game assets, not needed to build the engine.
shutil.rmtree(src / 'Resources/srallyc', ignore_errors=True)
allowed = {'Info.plist', 'MacOS/port0r', 'Frameworks/libMoltenVK.dylib',
           'Frameworks/libtcvr_mame.dylib', 'Resources/README.txt', 'Resources/AppIcon.icns',
           '_CodeSignature/CodeResources'}
unexpected = [str(p.relative_to(src)) for p in src.rglob('*')
              if p.is_file() and str(p.relative_to(src)) not in allowed]
if unexpected:
    raise SystemExit(f'Unreviewed release contents: {unexpected}')

# The generic converter pretends every iPhone GPU supports the desktop Mac2
# family. Port0r uses MoltenVK, which consumes that answer when selecting Vulkan
# capabilities. Report the native device's answer instead; retain all other
# compatibility hooks and the original renderer for a controlled comparison.
p = root / 'shim/overrides/AppKit_RuntimeHooks.m'
s = p.read_text()
old = '    if (family == MTLGPUFamilyMac2) return YES;'
if s.count(old) != 1:
    raise SystemExit('Pinned converter GPU-family hook changed; review required')
s = s.replace(old, '    // Port0r: never invent desktop GPU capabilities on iOS.')
s = s.replace('// Mac games pick shader sets by Mac GPU family; on iPadOS an Apple-silicon GPU reports only\n'
              '// Apple/Common/Metal families. Same hardware, so also claim MTLGPUFamilyMac2.',
              '// Port0r/MoltenVK must receive the actual GPU family capabilities.')
marker = '    gSupportsFamily = method_setImplementation(class_getInstanceMethod(dc, @selector(supportsFamily:)), (IMP)ShimSupportsFamily);'
if s.count(marker) != 1:
    raise SystemExit('Pinned converter GPU hook installation changed')
s = s.replace(marker, marker + '\n    NSLog(@"PORT0R native Metal capabilities Mac2=%d Apple9=%d; desktop family spoof disabled",'
              '\n          [device supportsFamily:MTLGPUFamilyMac2], [device supportsFamily:MTLGPUFamilyApple9]);')
p.write_text(s)

# The Mac menu expresses resolution as percentages. Preserve those code paths;
# make their base size and backing scale match the actual iPhone/iPad screen.
p = root / 'shim/overrides/CoreGraphics.m'
s = p.read_text().replace('static double gHz = 120;', 'static double gHz = 60;\nstatic CGFloat gScale = 1;')
s = s.replace('CGSize s = UIScreen.mainScreen.nativeBounds.size;',
              'gScale = UIScreen.mainScreen.nativeScale;\n    CGSize s = UIScreen.mainScreen.nativeBounds.size;')
s = s.replace('ScreenPixels().width / 2', 'ScreenPixels().width / gScale')
s = s.replace('ScreenPixels().height / 2', 'ScreenPixels().height / gScale')
s = s.replace('p.width / 2, p.height / 2', 'p.width / gScale, p.height / gScale')
# SDL stores modes in a CFArray with kCFTypeArrayCallBacks. A pointer to a
# static C struct is not a CF object and crashes when that array retains it.
s = s.replace('static struct ShimDisplayMode gMode;', '''static CGDisplayModeRef NativeMode(void) {
    static CFDictionaryRef mode;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        mode = CFDictionaryCreate(NULL, NULL, NULL, 0,
                                  &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    });
    return (CGDisplayModeRef)mode;
}''')
s = s.replace('return &gMode;', 'return (CGDisplayModeRef)CFRetain(NativeMode());')
s = s.replace('{ &gMode }', '{ NativeMode() }')
s = s.replace('modes, 1, NULL)', 'modes, 1, &kCFTypeArrayCallBacks)')
s = s.replace('void CGDisplayModeRelease(CGDisplayModeRef m) {}',
              'void CGDisplayModeRelease(CGDisplayModeRef m) { if (m) CFRelease(m); }')
s = s.replace('CGDisplayModeRetain(CGDisplayModeRef m) { return m; }',
              'CGDisplayModeRetain(CGDisplayModeRef m) { return m ? (CGDisplayModeRef)CFRetain(m) : NULL; }')
p.write_text(s)
for override in (Path(__file__).parent / 'overrides').glob('*'):
    if override.suffix in {'.m', '.h'}:
        shutil.copyfile(override, root / 'shim/overrides' / override.name)
# The bundled SDL is Mac SDL 2.30.3. Generate its Mac API-table slots rather
# than using iOS slot numbering (the platform-specific entries differ).
procs = Path(__file__).parent / 'vendor/SDL_dynapi_procs.h'
expanded = subprocess.check_output(['xcrun', '--sdk', 'macosx', 'clang', '-E', '-P', '-x', 'c',
    '-undef', '-D__MACOSX__', '-DSDL_DYNAPI_PROC(rc,fn,params,args,ret)=fn', str(procs)], text=True)
slots = re.findall(r'^SDL_\w+$', expanded, re.M)
assert len(slots) > 800 and len(slots) == len(set(slots))
names = ['SDL_GetVersion', 'SDL_CreateWindow', 'SDL_GetWindowFlags', 'SDL_SetWindowFullscreen',
         'SDL_SetWindowDisplayMode', 'SDL_SetWindowSize', 'SDL_PollEvent', 'SDL_PumpEvents',
         'SDL_WaitEvent', 'SDL_WaitEventTimeout', 'SDL_GameControllerOpen', 'SDL_GameControllerGetButton', 'SDL_GameControllerName', 'SDL_NumJoysticks',
         'SDL_GameControllerRumble', 'SDL_GameControllerRumbleTriggers',
         'SDL_GameControllerHasRumble', 'SDL_GameControllerHasRumbleTriggers']
(root / 'shim/overrides/Port0rSDLSlots.h').write_text(
    '// Generated from Mac SDL 2.30.3 dynapi ABI, zlib-licensed source in tools/vendor.\n'
    + '#define PORT0R_SDL_SLOTCOUNT ' + str(len(slots)) + '\n'
    + ''.join('#define PORT0R_SLOT_' + n + ' ' + str(slots.index(n)) + '\n' for n in names))
p = root / 'shim/overrides/AppKit.m'
s = p.read_text().replace('return @"iPad";', 'return @"iPhone / iPad Native";')
s = s.replace('CGRectMake(0, 0, 1376, 1032)',
              'CGRectMake(0, 0, MAX(UIScreen.mainScreen.bounds.size.width, UIScreen.mainScreen.bounds.size.height), MIN(UIScreen.mainScreen.bounds.size.width, UIScreen.mainScreen.bounds.size.height))')
s = s.replace(': 2.0;', ': UIScreen.mainScreen.nativeScale;')
# A keyboard fallback is used only if SDL has no Select/Back binding for a
# connected Backbone; the original game's 5 key inserts a coin.
s += '''
__attribute__((visibility("default"))) void Port0rCoinKey(BOOL down) {
    NSEvent *e = [NSEvent new];
    e.type = down ? NSEventTypeKeyDown : NSEventTypeKeyUp;
    e.keyCode = 23; e.characters = @"5"; e.charactersIgnoringModifiers = @"5";
    e.timestamp = NSProcessInfo.processInfo.systemUptime;
    ShimDispatch(e);
}
__attribute__((visibility("default"))) void Port0rTouchKey(unsigned short code, BOOL down) {
    NSEvent *e = [NSEvent new];
    e.type = down ? NSEventTypeKeyDown : NSEventTypeKeyUp;
    e.keyCode = code;
    switch (code) {
        case 23: e.characters = @"5"; break;
        case 36: e.characters = @"\\r"; break;
        case 53: e.characters = @"\\x1b"; break;
        case 14: e.characters = @"e"; break;
        case 12: e.characters = @"q"; break;
        case 9: e.characters = @"v"; break;
        default: e.characters = @""; break;
    }
    e.charactersIgnoringModifiers = e.characters;
    e.timestamp = NSProcessInfo.processInfo.systemUptime;
    ShimDispatch(e);
}
'''
p.write_text(s)
# AVAudioSession is used only to activate the native output route. Queue PCM
# conversion/playback stays in Apple's AudioToolbox.
converter = root / 'tools/convert_app.py'
converter.write_text(converter.read_text().replace('"-framework", "GameController"]',
    '"-framework", "GameController", "-framework", "AVFAudio", "-framework", "CoreHaptics"]'))
# Native GameController backend and existing user-data locations.
target = root / 'shim/overrides/AppKit_Port0r.m'
target.write_text('''#import <Foundation/Foundation.h>
#include <stdlib.h>
extern void Port0rPreparePaths(void);
extern void Port0rCleanOldFiles(NSString *home);

__attribute__((constructor)) static void Port0rContainerSetup(void) {
    setenv("SDL_JOYSTICK_IOKIT", "0", 1);
    setenv("SDL_JOYSTICK_HIDAPI", "0", 1);
    setenv("SDL_JOYSTICK_MFI", "1", 1);
    Port0rCleanOldFiles(NSHomeDirectory());
    [NSFileManager.defaultManager createDirectoryAtPath:
        [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/Downloads"]
        withIntermediateDirectories:YES attributes:nil error:nil];
    Port0rPreparePaths();
}
''')
from release_cleanup import prepare_release
prepare_release(root)
print('Prepared release: native refresh preserved; FPS, statistics, tracing, dumps and log capture removed')
