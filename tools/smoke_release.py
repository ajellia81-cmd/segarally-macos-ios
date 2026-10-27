"""Check release hygiene and legacy diagnostic cleanup outside the shipped IPA."""
from pathlib import Path
import subprocess
from release_cleanup import quiet_nslogs

overrides = Path('compatibility/shim/overrides').resolve()
app = Path('build/SegaRally.app')
for name in ['AppKit_FPS.m','AppKit_Stats.m','Port0rLog.h']:
    assert not (overrides / name).exists(), name
refresh = (overrides / 'AppKit_Refresh.m').read_text()
assert 'CADisplayLink' in refresh and 'CAFrameRateRangeMake(30, maximum, maximum)' in refresh
assert 'UILabel' not in refresh and 'MTLDrawable' not in refresh and 'atomic_' not in refresh
runtime = (overrides / 'AppKit_RuntimeHooks.m').read_text()
for token in ['Documents/shimdump','ShimTraceInit','ShimPacingLogInit','HookGCHandlers']:
    assert token not in runtime, token
setup = (overrides / 'AppKit_Port0r.m').read_text()
assert 'Port0rCleanOldFiles(NSHomeDirectory())' in setup and 'Documents/Downloads' in setup
for token in ['dup2(', 'NSSetUncaughtExceptionHandler', 'launch.log', 'Port0rLaunchDiagnostics']:
    assert token not in setup, token
sample = '// NSLog(comment)\nif (x) NSLog(@"(%@)", f(1,g(2))); else keep();\nconst char *s="NSLog(literal)";'
assert quiet_nslogs(sample) == '// NSLog(comment)\nif (x) ((void)0); else keep();\nconst char *s="NSLog(literal)";'

required = {
    'AppKit': {'_SDL_DYNAPI_entry','_Port0rPrepareControllerEnginesR7','_Port0rCoinKey','_Port0rCleanOldFiles','_Port0rWaitForForeground'},
    'AudioToolbox': {'_AudioQueueNewOutput','_AudioQueueEnqueueBuffer'},
}
for library,symbols in required.items():
    binary = app / 'Frameworks' / ('libShim_' + library + '.dylib')
    exports = set(subprocess.check_output(['xcrun','nm','-gUj',str(binary)],text=True).split())
    assert symbols <= exports, symbols - exports
for binary in (app / 'Frameworks').glob('libShim_*.dylib'):
    data = binary.read_bytes()
    for token in [b'_Port0rAudioCallsR2', b'_Port0rInputCallsR2', b'_Port0rHapticCallsR2',
                  b'Port0rPresentationFPS', b'Port0rLaunchDiagnostics', b'Port0rDiagnosticLog',
                  b'ShimStatsInit', b'ShimPacingLogInit', b'HookGCHandlers', b'ShimFault', b'_NSLog\0']:
        assert token not in data, (binary.name, token)
imports = subprocess.check_output(['xcrun','dyld_info','-imports',str(app/'port0r')],text=True)
enqueue = [line for line in imports.splitlines() if '_AudioQueueEnqueueBuffer' in line]
assert enqueue and all('libShim_AudioToolbox' in line for line in enqueue)

test = Path('build/release_cleanup_smoke.m')
test.write_text('#import "' + str(overrides / 'AppKit_Cleanup.m') + '"\n' + r'''
#include <assert.h>
static void Put(NSString *path) {
    NSFileManager *fm = NSFileManager.defaultManager;
    assert([fm createDirectoryAtPath:path.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil]);
    assert([@"user-data-sentinel" writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:nil]);
}
int main(void) { @autoreleasepool {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSString *home = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NSString *diag = [home stringByAppendingPathComponent:@"Documents/Port0r-diagnostics"];
    NSString *dump = [home stringByAppendingPathComponent:@"Documents/shimdump"];
    NSString *rom = [home stringByAppendingPathComponent:@"Documents/Downloads/srallyc.zip"];
    NSString *settings = [home stringByAppendingPathComponent:@"Documents/Port0r/srallyc/tcvr-settings-v1.txt"];
    NSString *save = [home stringByAppendingPathComponent:@"Documents/Port0r/srallyc/nvram/save"];
    for (NSString *name in @[@"launch.log",@"launch.previous.log"]) Put([diag stringByAppendingPathComponent:name]);
    for (NSString *name in @[@"lib1.bin",@"lib2.bin",@"lib3.bin"]) Put([dump stringByAppendingPathComponent:name]);
    Put(rom); Put(settings); Put(save);
    Port0rCleanOldFiles(home);
    assert(![fm fileExistsAtPath:diag] && ![fm fileExistsAtPath:dump]);
    for (NSString *path in @[rom,settings,save]) assert([[NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil] isEqual:@"user-data-sentinel"]);
    Port0rCleanOldFiles(home); // idempotent and never recreates diagnostics
    NSString *unknown = [diag stringByAppendingPathComponent:@"keep.txt"];
    Put(unknown); Put([diag stringByAppendingPathComponent:@"launch.log"]);
    Port0rCleanOldFiles(home);
    assert([fm fileExistsAtPath:unknown] && ![fm fileExistsAtPath:[diag stringByAppendingPathComponent:@"launch.log"]]);
    [fm removeItemAtPath:diag error:nil];
    assert([fm createSymbolicLinkAtPath:diag withDestinationPath:settings.stringByDeletingLastPathComponent error:nil]);
    Port0rCleanOldFiles(home);
    assert([fm destinationOfSymbolicLinkAtPath:diag error:nil] == nil && [fm fileExistsAtPath:settings]);
    Put([diag stringByAppendingPathComponent:@"launch.log/keep.txt"]);
    Port0rCleanOldFiles(home);
    assert([fm fileExistsAtPath:[diag stringByAppendingPathComponent:@"launch.log/keep.txt"]]);
    [fm removeItemAtPath:home error:nil];
    puts("PASS: legacy diagnostic files and empty folders removed idempotently; ROM/settings/saves, foreign content and symlink targets preserved");
} return 0; }
''')
subprocess.run(['xcrun','--sdk','macosx','clang','-fobjc-arc','-fsanitize=address',
                '-framework','Foundation',str(test),'-o','build/release_cleanup_smoke'],check=True)
subprocess.run(['build/release_cleanup_smoke'],check=True,timeout=20)
print('PASS: release has no FPS/HUD, diagnostic counters, capture/dump/statistics/tracing hooks or shim NSLog imports; refresh/input/audio runtime hooks retained')
