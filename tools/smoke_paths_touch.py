"""Exercise C++ import paths and the actual touch input state machine on Actions.

Uses placeholder text only, never ROM data. UI/physical controller tests still
require an iPhone.
"""
from pathlib import Path
import subprocess

overrides = Path('compatibility/shim/overrides').resolve()
test = Path('build/paths_touch_smoke.mm')
test.write_text('#import "' + str(overrides / 'AppKit_Paths.m') + '"\n' +
                '#include "' + str(overrides / 'Port0rTouchState.h') + '"\n' + r'''
#include <filesystem>
#include <fstream>
#include <cassert>
static int downCount, upCount;
static void Emit(unsigned short key, bool down) { if (down) downCount++; else upCount++; }
int main(void) { @autoreleasepool {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSString *home = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NSString *downloads = [home stringByAppendingPathComponent:@"Documents/Downloads"];
    NSString *nativeDownloads = [home stringByAppendingPathComponent:@"Downloads"];
    NSString *data = [home stringByAppendingPathComponent:@"Documents/Port0r"];
    NSString *nativeData = [home stringByAppendingPathComponent:@"Library/Application Support/Port0r"];
    [fm createDirectoryAtPath:nativeDownloads withIntermediateDirectories:YES attributes:nil error:nil];
    [@"old download" writeToFile:[nativeDownloads stringByAppendingPathComponent:@"keep.txt"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
    [fm createDirectoryAtPath:data withIntermediateDirectories:YES attributes:nil error:nil];
    [fm createDirectoryAtPath:nativeData withIntermediateDirectories:YES attributes:nil error:nil];
    [@"canonical settings" writeToFile:[data stringByAppendingPathComponent:@"settings.txt"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
    [@"old conflicting settings" writeToFile:[nativeData stringByAppendingPathComponent:@"settings.txt"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
    assert(PreparePathPair(nativeDownloads, downloads));
    assert(PreparePathPair(nativeData, data));
    assert([fm fileExistsAtPath:[downloads stringByAppendingPathComponent:@"keep.txt"]]);
    assert([fm fileExistsAtPath:[[nativeData stringByAppendingString:@".before-ios-paths"] stringByAppendingPathComponent:@"settings.txt"]]);
    assert([[NSString stringWithContentsOfFile:[data stringByAppendingPathComponent:@"settings.txt"] encoding:NSUTF8StringEncoding error:nil] isEqualToString:@"canonical settings"]);
    // Reproduce the mixed native C++ importer / canonical game file-reader path.
    std::filesystem::path root(home.fileSystemRepresentation);
    std::filesystem::path input = root / "Downloads/fixture.zip";
    { std::ofstream file(input); file << "test placeholder, not a ROM"; }
    auto imported = root / "Library/Application Support/Port0r/srallyc/roms/fixture.zip";
    std::filesystem::create_directories(imported.parent_path());
    assert(std::filesystem::copy_file(input, imported));
    auto visible = root / "Documents/Port0r/srallyc/roms/fixture.zip";
    assert(std::filesystem::file_size(visible) == std::filesystem::file_size(input));
    assert(std::filesystem::equivalent(imported, visible));
    assert(PreparePathPair(nativeDownloads, downloads)); // idempotent, no new backup
    assert(PreparePathPair(nativeData, data));
    [fm removeItemAtPath:home error:nil];
    puts("PASS: C++ Downloads import and canonical game reader share files; existing data/conflicts backed up; aliases idempotent");
    Port0rTouchState state = {0};
    Port0rTouchSetEnabled(&state, true, Emit);
    Port0rTouchChange(&state, 126, true, Emit); // gas
    Port0rTouchChange(&state, 126, true, Emit); // second control holding same key
    Port0rTouchChange(&state, 123, true, Emit); // steer simultaneously
    assert(downCount == 2);
    Port0rTouchChange(&state, 126, false, Emit);
    assert(upCount == 0 && state.held[126] == 1);
    Port0rTouchSetEnabled(&state, false, Emit); // controller connected / app inactive
    assert(upCount == 2 && !state.held[126] && !state.held[123]);
    Port0rTouchChange(&state, 126, true, Emit); // hidden controls cannot press
    Port0rTouchChange(&state, 126, false, Emit); // late cancellation cannot underflow
    assert(downCount == 2 && upCount == 2);
    Port0rTouchSetEnabled(&state, true, Emit); // controller disconnected
    Port0rTouchChange(&state, 23, true, Emit);
    Port0rTouchChange(&state, 23, false, Emit);
    assert(downCount == 3 && upCount == 3);
    puts("PASS: multitouch chords, shared-key holds, cancellation, controller connect/disconnect and no stuck keys");
} return 0; }
''')
subprocess.run(['xcrun','--sdk','macosx','clang++','-std=c++17','-fobjc-arc','-fsanitize=address',
                '-framework','Foundation',str(test),'-o','build/paths_touch_smoke'],check=True)
result = subprocess.run(['build/paths_touch_smoke'],capture_output=True,text=True)
print(result.stdout)
if result.returncode:
    print(result.stderr[-6000:])
    raise SystemExit(result.returncode)

# Compile the actual button implementation with a minimal Foundation-backed
# UIButton stand-in. This checks Objective-C accessors and press/release methods,
# which the C-only key-state tests cannot exercise.
source = (overrides / 'AppKit_Touch.m').read_text()
button = source[source.index('@interface Port0rTouchButton'):source.index('@interface Port0rTouchOverlay')]
button_test = Path('build/touch_button_smoke.m')
button_test.write_text('#import <Foundation/Foundation.h>\n#include <assert.h>\n' +
    '#include "' + str(overrides / 'Port0rTouchState.h') + '"\n' + r"""
@interface UIButton : NSObject
@property double alpha;
@end
@implementation UIButton @end
static Port0rTouchState touchState;
static int downs, ups;
static void EmitTouch(unsigned short key, bool down) {
    assert(key == 126); if (down) downs++; else ups++;
}
""" + button + r"""
int main(void) { @autoreleasepool {
    Port0rTouchButton *button = [Port0rTouchButton new];
    assert([button respondsToSelector:@selector(port0rKeyHeld)]);
    assert([button respondsToSelector:@selector(setPort0rKeyHeld:)]);
    button.macKey = 126;
    assert(button.macKey == 126 && !button.port0rKeyHeld);
    [button releaseKey]; // startup with a controller connected
    assert(ups == 0);
    Port0rTouchSetEnabled(&touchState, true, EmitTouch);
    [button pressKey]; [button pressKey];
    assert(button.port0rKeyHeld && downs == 1);
    [button releaseKey]; [button releaseKey];
    assert(!button.port0rKeyHeld && ups == 1);
    puts("PASS: actual Objective-C button accessors, initial release, repeated press/release");
} return 0; }
""")
subprocess.run(['xcrun','--sdk','macosx','clang','-fobjc-arc','-fsanitize=address',
                '-framework','Foundation',str(button_test),'-o','build/touch_button_smoke'],check=True)
subprocess.run(['build/touch_button_smoke'],check=True)
