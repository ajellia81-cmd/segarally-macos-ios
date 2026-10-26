"""Check the SDL 2.30.3 Mac device-query contract against the iOS route bridge.

Runs metadata/ownership checks on macOS, without playing audio or capturing input.
Actual iOS session activation and audible output require a device test.
"""
from pathlib import Path
import subprocess

overrides = Path('compatibility/shim/overrides').resolve()
test = Path('build/audio_smoke.m')
test.write_text('#define PORT0R_AUDIO_TEST 1\n#import "' + str(overrides / 'CoreAudio_Port0r.m') + '"\n' +
                '#import "' + str(overrides / 'AudioToolbox_Port0r.m') + '"\n' + r'''
#import <CoreAudio/AudioHardware.h>
#include <assert.h>
#include <string.h>
static int starts, pauses, stops, disposals, enqueues;
static OSStatus TestNewOutput(const AudioStreamBasicDescription *format, AudioQueueOutputCallback cb,
 void *context, CFRunLoopRef loop, CFStringRef mode, UInt32 flags, AudioQueueRef *queue) {
    assert(format && queue); *queue = (AudioQueueRef)(uintptr_t)0x1234; return noErr;
}
static OSStatus TestEnqueue(AudioQueueRef q, AudioQueueBufferRef buffer, UInt32 count,
 const AudioStreamPacketDescription *packets) { assert(q && buffer && count == 0 && !packets); enqueues++; return noErr; }
static OSStatus TestStart(AudioQueueRef q, const AudioTimeStamp *t) { starts++; return noErr; }
static OSStatus TestPause(AudioQueueRef q) { pauses++; return noErr; }
static OSStatus TestStop(AudioQueueRef q, Boolean immediate) { stops++; return noErr; }
static OSStatus TestDispose(AudioQueueRef q, Boolean immediate) { disposals++; return noErr; }
void *AudioFunction(const char *name) {
    if (!strcmp(name, "AudioQueueNewOutput")) return (void *)TestNewOutput;
    if (!strcmp(name, "AudioQueueEnqueueBuffer")) return (void *)TestEnqueue;
    if (!strcmp(name, "AudioQueueStart")) return (void *)TestStart;
    if (!strcmp(name, "AudioQueuePause")) return (void *)TestPause;
    if (!strcmp(name, "AudioQueueStop")) return (void *)TestStop;
    if (!strcmp(name, "AudioQueueDispose")) return (void *)TestDispose;
    return NULL;
}
int main(void) { @autoreleasepool {
    AudioStreamBasicDescription pcm = {0};
    pcm.mFormatID = kAudioFormatLinearPCM;
    pcm.mFormatFlags = kAudioFormatFlagIsPacked | kAudioFormatFlagIsSignedInteger;
    pcm.mBitsPerChannel = 16;
    int16_t samples[] = {0, 1000, -1000, 32767, -32768};
    // AudioQueueBuffer's capacity is const in the Apple SDK: use an initialized fixture below.
    AudioQueueBuffer fixture = {sizeof samples, samples, sizeof samples, NULL, 0, NULL, 0};
    BoostPCM(&fixture, pcm);
    assert(samples[0] == 0 && samples[1] == 2000 && samples[2] == -2000);
    assert(samples[3] > 32000 && samples[4] < -32000);
    float floats[] = {0, 0.1f, -0.1f, 1, -1, NAN};
    AudioQueueBuffer floatFixture = {sizeof floats, floats, sizeof floats, NULL, 0, NULL, 0};
    pcm.mBitsPerChannel = 32; pcm.mFormatFlags = kAudioFormatFlagIsPacked | kAudioFormatFlagIsFloat;
    BoostPCM(&floatFixture, pcm);
    assert(fabsf(floats[1] - 0.2f) < 0.00001 && fabsf(floats[2] + 0.2f) < 0.00001);
    assert(floats[3] <= 1 && floats[4] >= -1 && floats[5] == 0);
    puts("PASS: audio gain doubles quiet PCM, preserves silence and bounds amplified integer/float peaks");
    AudioQueueRef testQueue = NULL;
    pcm.mBitsPerChannel = 16; pcm.mFormatFlags = kAudioFormatFlagIsPacked | kAudioFormatFlagIsSignedInteger;
    assert(AudioQueueNewOutput(&pcm, NULL, NULL, NULL, NULL, 0, &testQueue) == noErr);
    int16_t routeSamples[] = {1000,-1000};
    AudioQueueBuffer routeFixture = {sizeof routeSamples, routeSamples, sizeof routeSamples, NULL, 0, NULL, 0};
    assert(AudioQueueEnqueueBuffer(testQueue, &routeFixture, 0, NULL) == noErr);
    assert(enqueues == 1 && Port0rAudioCallsR2() == 1 && routeSamples[0] == 2000 && routeSamples[1] == -2000);
    puts("PASS: actual NewOutput format registration and EnqueueBuffer path doubles PCM and forwards to native queue");
    assert(AudioQueueStart(testQueue, NULL) == noErr && starts == 1);
    OutputLifecycle(NO); OutputLifecycle(NO);
    assert(pauses == 1 && starts == 1);
    OutputLifecycle(YES); OutputLifecycle(YES);
    assert(starts == 2);
    assert(AudioQueuePause(testQueue) == noErr && pauses == 2);
    OutputLifecycle(NO); OutputLifecycle(YES);
    assert(starts == 2); // a user-paused queue must stay paused
    OutputLifecycle(NO);
    assert(AudioQueueStart(testQueue, NULL) == noErr && starts == 2);
    OutputLifecycle(YES);
    assert(starts == 3); // deferred start while backgrounded
    assert(AudioQueueStop(testQueue, true) == noErr && stops == 1);
    OutputLifecycle(NO); OutputLifecycle(YES);
    assert(starts == 3);
    assert(AudioQueueDispose(testQueue, true) == noErr && disposals == 1);
    assert(queueIntent.count == 0 && queueFormats.count == 0);
    puts("PASS: audio background pause, foreground resume, deferred start, user pause/stop intent and disposal");
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
