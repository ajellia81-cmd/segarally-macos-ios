"""Check the SDL 2.30.3 Mac device-query contract against the iOS route bridge.

Runs metadata/ownership checks on macOS, without playing audio or capturing input.
Actual iOS session activation and audible output require a device test.
"""
from pathlib import Path
import subprocess

overrides = Path('compatibility/shim/overrides').resolve()
test = Path('build/audio_smoke.m')
test.write_text('#import "' + str(overrides / 'CoreAudio_Port0r.m') + '"\n' +
                '#import "' + str(overrides / 'AudioToolbox_Port0r.m') + '"\n' + r'''
#import <CoreAudio/AudioHardware.h>
#include <assert.h>
int main(void) { @autoreleasepool {
    Port0rAudioAddress address = {kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal, 0};
    uint32_t size = 0, device = 0;
    assert(Port0rAudioSize(1, &address, 0, NULL, &size) == noErr && size == sizeof(device));
    assert(Port0rAudioGet(1, &address, 0, NULL, &size, &device) == noErr && device == 2);
    address.selector = kAudioHardwarePropertyDefaultOutputDevice;
    size = sizeof device;
    assert(Port0rAudioGet(1, &address, 0, NULL, &size, &device) == noErr && device == 2);
    address.selector = kAudioDevicePropertyDeviceIsAlive;
    uint32_t alive = 0; size = sizeof alive;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &alive) == noErr && alive == 1);
    address.selector = kAudioDevicePropertyHogMode;
    int32_t hog = 0; size = sizeof hog;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &hog) == noErr && hog == -1);
    address.selector = kAudioDevicePropertyNominalSampleRate;
    double rate = 0; size = sizeof rate;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &rate) == noErr && rate > 0);
    address.selector = kAudioDevicePropertyStreamConfiguration;
    address.scope = kAudioDevicePropertyScopeOutput;
    AudioBufferList buffers; size = sizeof buffers;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &buffers) == noErr);
    assert(buffers.mNumberBuffers == 1 && buffers.mBuffers[0].mNumberChannels == 2);
    address.scope = kAudioDevicePropertyScopeInput; size = sizeof buffers;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &buffers) == noErr && buffers.mBuffers[0].mNumberChannels == 0);
    address.selector = kAudioDevicePropertyDeviceUID;
    CFStringRef uid = NULL; size = sizeof uid;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &uid) == noErr && uid);
    assert(AudioQueueSetProperty(NULL, kAudioQueueProperty_CurrentDevice, &uid, sizeof uid) == noErr);
    CFRelease(uid);
    address.selector = kAudioObjectPropertyName;
    CFStringRef name = NULL; size = sizeof name;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &name) == noErr && name);
    CFRelease(name);
    size = 1; uint32_t guard = 0x12345678;
    assert(Port0rAudioGet(device, &address, 0, NULL, &size, &guard) != noErr && guard == 0x12345678);
    address.selector = 0;
    assert(Port0rAudioSize(device, &address, 0, NULL, &size) != noErr);
    puts("PASS: SDL default audio device, liveness, sample rate, channel metadata, retained UID, native route selection and buffer bounds");
} return 0; }
''')
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-fobjc-arc', '-fsanitize=address',
                '-framework', 'Foundation', '-framework', 'AudioToolbox', '-framework', 'CoreAudio',
                str(test), '-o', 'build/audio_smoke'], check=True)
result = subprocess.run(['build/audio_smoke'], capture_output=True, text=True)
print(result.stdout)
if result.returncode:
    print(result.stderr[-6000:])
    raise SystemExit(result.returncode)
