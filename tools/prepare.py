"""Apply narrowly scoped, reproducible adaptations to the pinned converter."""
from pathlib import Path
import shutil
import re
import subprocess

root = Path('compatibility')
src = Path('extracted/Port0r Rally.app/Contents')
# Optional cockpit packs are game assets, not needed to build the engine.
shutil.rmtree(src / 'Resources/srallyc', ignore_errors=True)
allowed = {'Info.plist', 'MacOS/port0r', 'Frameworks/libMoltenVK.dylib',
           'Frameworks/libtcvr_mame.dylib', 'Resources/README.txt', 'Resources/AppIcon.icns',
           '_CodeSignature/CodeResources'}
unexpected = [str(p.relative_to(src)) for p in src.rglob('*')
              if p.is_file() and str(p.relative_to(src)) not in allowed]
if unexpected:
    raise SystemExit(f'Unreviewed release contents: {unexpected}')

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
         'SDL_WaitEvent', 'SDL_WaitEventTimeout', 'SDL_GameControllerOpen',
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
# Native GCController is available on iOS. Avoid the unavailable Mac HID backend.
target = root / 'shim/overrides/AppKit_Port0r.m'
target.write_text('''#import <UIKit/UIKit.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#import <mach-o/dyld.h>
extern void Port0rPreparePaths(void);

static NSUncaughtExceptionHandler *previousExceptionHandler;
static void Port0rException(NSException *exception) {
    NSLog(@"PORT0R UNCAUGHT %@: %@\\n%@", exception.name, exception.reason,
          [exception.callStackSymbols componentsJoinedByString:@"\\n"]);
    fsync(STDERR_FILENO);
    if (previousExceptionHandler) previousExceptionHandler(exception);
}

// Objective-C +load runs before the shim's C constructors. This records the
// earliest reachable app startup, including shim preload failures and faults.
@interface Port0rLaunchDiagnostics : NSObject @end
@implementation Port0rLaunchDiagnostics
+ (void)load {
    @autoreleasepool {
        NSString *dir = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/Port0r-diagnostics"];
        NSFileManager *fm = NSFileManager.defaultManager;
        NSError *error = nil;
        if (![fm createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:&error]) {
            NSLog(@"PORT0R cannot create diagnostic directory: %@", error);
            return;
        }
        NSString *path = [dir stringByAppendingPathComponent:@"launch.log"];
        struct stat st;
        if (stat(path.fileSystemRepresentation, &st) == 0 && st.st_size > 2 * 1024 * 1024) {
            NSString *previous = [dir stringByAppendingPathComponent:@"launch.previous.log"];
            [fm removeItemAtPath:previous error:nil];
            [fm moveItemAtPath:path toPath:previous error:nil];
        }
        int fd = open(path.fileSystemRepresentation, O_WRONLY | O_CREAT | O_APPEND, 0600);
        if (fd < 0) return;
        dup2(fd, STDOUT_FILENO);
        dup2(fd, STDERR_FILENO);
        if (fd > STDERR_FILENO) close(fd);
        setvbuf(stdout, NULL, _IONBF, 0);
        setvbuf(stderr, NULL, _IONBF, 0);
        NSLog(@"PORT0R DIAGNOSTIC START %@ home=%@ bundle=%@ thread=%@",
              NSDate.date, NSHomeDirectory(), NSBundle.mainBundle.bundlePath, NSThread.currentThread);
        for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
            fprintf(stderr, "IMAGE %p %s\\n", (void *)_dyld_get_image_header(i), _dyld_get_image_name(i));
        }
        previousExceptionHandler = NSGetUncaughtExceptionHandler();
        NSSetUncaughtExceptionHandler(Port0rException);
        fsync(STDERR_FILENO);
    }
}
@end

__attribute__((constructor)) static void Port0rContainerSetup(void) {
    NSLog(@"PORT0R container setup constructor reached");
    setenv("SDL_JOYSTICK_IOKIT", "0", 1);
    setenv("SDL_JOYSTICK_HIDAPI", "0", 1);
    setenv("SDL_JOYSTICK_MFI", "1", 1);
    NSFileManager *fm = NSFileManager.defaultManager;
    for (NSString *sub in @[@"Documents/Downloads"]) {
        [fm createDirectoryAtPath:[NSHomeDirectory() stringByAppendingPathComponent:sub]
            withIntermediateDirectories:YES attributes:nil error:nil];
    }
    Port0rPreparePaths();
}
''')
# NSLog normally goes to the device's unified log, which Cloud cannot read.
# Mirror shim diagnostics to stderr after redirecting it to the guest log file.
header = root / 'shim/overrides/Port0rLog.h'
header.write_text('''#pragma once
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
static inline void Port0rDiagnosticLog(NSString *format, ...) NS_FORMAT_FUNCTION(1,2);
static inline void Port0rDiagnosticLog(NSString *format, ...) {
    va_list args;
    va_start(args, format);
    NSString *message = [[NSString alloc] initWithFormat:format arguments:args];
    va_end(args);
    NSLog(@"%@", message);
    const char *text = message.UTF8String;
    if (text) { write(STDERR_FILENO, text, strlen(text)); write(STDERR_FILENO, "\\n", 1); }
}
#define NSLog(...) Port0rDiagnosticLog(__VA_ARGS__)
''')
for source in (root / 'shim/overrides').glob('*.m'):
    source.write_text('#import "Port0rLog.h"\n' + source.read_text())
print('Prepared native display sizing, GameController backend and ROM-free input bundle')
