"""Check that R2 instrumentation is linked into the IPA's actual runtime paths."""
from pathlib import Path
import subprocess
app = Path('build/SegaRally.app')
for library, symbols in {
    'AudioToolbox': ['_Port0rAudioCallsR2', '_AudioQueueEnqueueBuffer', '_AudioQueueNewOutput'],
    'AppKit': ['_Port0rInputCallsR2', '_Port0rHapticCallsR2', '_SDL_DYNAPI_entry'],
}.items():
    binary = app / 'Frameworks' / ('libShim_' + library + '.dylib')
    exported = set(subprocess.check_output(['xcrun','nm','-gUj',str(binary)], text=True).split())
    assert set(symbols) <= exported, (library, set(symbols) - exported)
imports = subprocess.check_output(['xcrun','dyld_info','-imports',str(app / 'port0r')], text=True)
enqueue = [line for line in imports.splitlines() if '_AudioQueueEnqueueBuffer' in line]
assert enqueue and all('libShim_AudioToolbox' in line for line in enqueue), enqueue
fps = Path('compatibility/shim/overrides/AppKit_FPS.m').read_text()
assert 'R11 | A %llu | S %llu | H %llu' in fps and 'Port0rAudioCallsR2' in fps
appkit_exports = set(subprocess.check_output(['xcrun','nm','-gUj',str(app / 'Frameworks/libShim_AppKit.dylib')], text=True).split())
assert '_Port0rWarmControllerHaptics' not in appkit_exports
assert 'Port0rWarmControllerHaptics' not in Path('compatibility/shim/overrides/AppKit_SDLPolicy.m').read_text()
assert '_Port0rPrepareControllerEnginesR7' in appkit_exports
print('PASS: old playback warm-up entry absent; engine-only preparation linked')
print('PASS: actual runtime shims export R2 counters, guest enqueue import binds to audio shim, R11 HUD compiled')
